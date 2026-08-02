
"""
Unit & Regression Tests for Causal Uplift Engine API & EMV Gate.
Includes regression tests for Section 5.1 AOV Proxy Bug and Section 4.1 Adversarial Cart Clamping.
"""
import os
import subprocess
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import importlib

from src.api.main import app
from config.settings import settings
from src.causal.emv_gate import evaluate_expected_monetary_value

# Instantiate FastAPI TestClient
client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[1]

# Authoritative (server-to-server) vs advisory (client-side/public) headers.
auth_headers = {"X-API-Key": settings.API_KEY}
public_headers = {"X-API-Key": settings.PUBLIC_API_KEY}


def _run_settings_validation(env_overrides: dict) -> subprocess.CompletedProcess:
    """Spawns a fresh process to exercise config/settings.py's module-level
    fail-fast check in isolation — it runs at import time, so it can't be
    triggered a second time within this already-running test process."""
    env = {"PATH": os.environ.get("PATH", "")}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def test_health_check_reports_model_status():
    """1. Tests /health probe reports model artifact loading status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "model_loaded" in data
    assert "control_model" in data
    assert "treatment_model" in data


def test_aov_proxy_bug_regression():
    """
    2. REGRESSION TEST (Section 5.1 worked numbers):
    Verifies price_sum_viewed ($300) is NOT used as AOV when cart_value_override is missing.
    Ensures decision uses settings.DEFAULT_AOV ($65) instead of window-shopping total ($300).
    """
    payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 120.0,
        "product_views_count": 6,
        "cart_add_count": 0,
        "price_sum_viewed": 300.0,
        "time_since_last_action": 12.5,
        "cart_value_override": None
    }
    
    response = client.post("/predict_v2?verbose=true", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    assert data["net_emv_dollars"] < 8.00


def test_predict_v2_sanitized_non_verbose_response():
    """3. Tests that default public response hides raw internal model probabilities."""
    payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 120.0,
        "product_views_count": 5,
        "cart_add_count": 1,
        "price_sum_viewed": 150.0,
        "time_since_last_action": 12.5
    }
    response = client.post("/predict_v2", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    assert "trigger_discount" in data
    assert data["cate_uplift"] is None
    assert data["p_control"] is None
    assert data["p_treatment"] is None
    assert data["trust_level"] == "authoritative"


def test_input_bounds_validation():
    """4. Tests that out-of-bounds inputs fail Pydantic validation (422)."""
    invalid_payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 999999.0,  # Exceeds max 86400s (24h) bound
        "product_views_count": 5,
        "cart_add_count": 1,
        "price_sum_viewed": 150.0,
        "time_since_last_action": 12.5
    }
    response = client.post("/predict_v2", json=invalid_payload, headers=auth_headers)
    assert response.status_code == 422  # Unprocessable Entity


def test_emv_gate_math_cases():
    """5. Tests Expected Monetary Value ($) calculation logic directly."""
    trigger, emv_risk, net_emv_mean, cate = evaluate_expected_monetary_value(
        p_control=0.20,
        p_treatment=0.50,
        cate_std_err=0.05,
        aov=100.0,
        gross_margin=0.40,
        discount_rate=0.10,
        min_emv_aov_percent_threshold=0.005,
        risk_lambda=0.5
    )
    assert cate == 0.30
    assert trigger is True
    assert emv_risk > 0.50

    trigger_b, emv_b, net_emv_b, cate_b = evaluate_expected_monetary_value(
        p_control=0.85,
        p_treatment=0.85,
        cate_std_err=0.05,
        aov=100.0,
        gross_margin=0.40,
        discount_rate=0.10,
        min_emv_aov_percent_threshold=0.005,
        risk_lambda=0.5
    )
    assert cate_b == 0.0
    assert trigger_b is False
    assert emv_b < 0.0


def test_adversarial_cart_override_clamping_regression():
    """
    6. REGRESSION TEST (Section 4.1 worked numbers):
    Verifies an adversarial caller CANNOT pass cart_value_override=$9,999.99
    on a small browsing session to artificially inflate EMV and force a discount.
    """
    adversarial_payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 120.0,
        "product_views_count": 2,
        "cart_add_count": 0,
        "price_sum_viewed": 50.0,
        "time_since_last_action": 12.5,
        "cart_value_override": 9999.99  # Malicious attempt to force EMV trigger
    }
    
    response = client.post("/predict_v2?verbose=true", json=adversarial_payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verifies cart_value_override was clamped to sane cap ($195.00), suppressing fake $160.00 EMV inflation
    assert data["net_emv_dollars"] < 10.00
    assert data["trigger_discount"] is False  # Correctly suppressed!


def test_unauthenticated_request_is_rejected():
    """
    7. VULNERABILITY FIX VERIFICATION (Audit §4.2):
    Confirms that requests without a valid API key are rejected with 401 Unauthorized.
    """
    payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 120.0,
        "product_views_count": 5,
        "cart_add_count": 1,
        "price_sum_viewed": 150.0,
        "time_since_last_action": 12.5
    }
    response = client.post("/predict_v2", json=payload, headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401

    response_no_key = client.post("/predict_v2", json=payload)
    assert response_no_key.status_code == 401


def test_fallback_mode_fails_closed(monkeypatch):
    """
    8. VULNERABILITY FIX VERIFICATION (Audit §5.2):
    Confirms that if model artifacts fail to load, the system 'fails closed'
    by suppressing the discount.
    """
    # Patch the model loader to simulate a failure
    monkeypatch.setattr(
        "src.causal.t_learner.CausalTLearner._load_model_artifact",
        lambda self, filepath, model_name: (None, False),
    )

    # Force a reload of the main module to re-instantiate CausalTLearner with the patch
    from src.api import main as main_module
    importlib.reload(main_module)
    patched_client = TestClient(main_module.app)

    # Payload with a high AOV that previously triggered a discount
    payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 300,
        "product_views_count": 10,
        "cart_add_count": 2,
        "price_sum_viewed": 600.0,
        "time_since_last_action": 30,
        "cart_value_override": 600.0,
    }

    patched_auth_headers = {"X-API-Key": settings.API_KEY}
    response = patched_client.post(
        "/predict_v2?verbose=true", json=payload, headers=patched_auth_headers
    )

    assert response.status_code == 200
    data = response.json()

    # This verifies the fix: no discount is triggered in fallback mode
    assert data["model_source"] == "fallback_fail_closed"
    assert data["trigger_discount"] is False

    # Reload the original module to clean up the patched state for other tests
    importlib.reload(main_module)

def test_relative_emv_threshold_is_not_gameable():
    """
    9. VULNERABILITY FIX VERIFICATION (Audit §5.3):
    Confirms the new relative EMV threshold is NOT gameable by inflating AOV.
    A small CATE should be suppressed regardless of AOV.
    """
    # A small CATE that should not be sufficient for a discount
    p_control = 0.10
    p_treatment = 0.18  # CATE = +8.0%

    # 1. At a low, default AOV, the discount is correctly suppressed.
    trigger_low_aov, _, _, _ = evaluate_expected_monetary_value(
        p_control=p_control,
        p_treatment=p_treatment,
        aov=settings.DEFAULT_AOV,  # $65
        min_emv_aov_percent_threshold=0.10 # Use a higher threshold for the test
    )
    assert trigger_low_aov is False

    # 2. At a high, inflated AOV, the discount is now also correctly suppressed.
    trigger_high_aov, _, _, _ = evaluate_expected_monetary_value(
        p_control=p_control,
        p_treatment=p_treatment,
        aov=1000.0,  # Inflated AOV
        min_emv_aov_percent_threshold=0.10 # Use a higher threshold for the test
    )
    assert trigger_high_aov is False

def test_adversarial_feature_injection_is_clamped():
    """
    10. VULNERABILITY FIX VERIFICATION (Audit §5.1):
    Confirms that the system now clamps adversarial feature values,
    preventing an attacker from forcing a discount trigger.
    """
    # This payload uses exaggerated values that are within the schema's wide bounds
    # but should be caught by the tighter clamping logic in the endpoint.
    adversarial_payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": 1500,  # Above clamp (1000), below schema (86400)
        "product_views_count": 60,     # Above clamp (50), below schema (500)
        "cart_add_count": 25,          # Above clamp (20), below schema (100)
        "price_sum_viewed": 9000,      # Above clamp (8000), below schema (10000)
        "time_since_last_action": 400, # Above clamp (300), below schema (7200)
        "cart_value_override": 9000
    }

    response = client.post("/predict_v2?verbose=true", json=adversarial_payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # This verifies the fix: the clamped, less extreme feature values should
    # no longer be sufficient to trigger a discount.
    assert data["trigger_discount"] is False


# ---------------------------------------------------------------------------
# Two-tier trust model (client-side "advisory" vs server-to-server
# "authoritative") — see src/api/main.py:verify_api_key and
# GTM_INTEGRATION_V2.md "Trust Model".
# ---------------------------------------------------------------------------

def test_public_key_is_labeled_advisory():
    """The client-side/public key must always come back marked advisory,
    regardless of what trigger_discount says, so callers can't accidentally
    wire it to a real action."""
    payload = {
        "visitor_type_encoded": 1, "traffic_type": 2,
        "session_duration_sec": 120.0, "product_views_count": 5,
        "cart_add_count": 1, "price_sum_viewed": 150.0,
        "time_since_last_action": 12.5,
    }
    response = client.post("/predict_v2?verbose=true", json=payload, headers=public_headers)
    assert response.status_code == 200
    assert response.json()["trust_level"] == "advisory"


def test_authoritative_key_is_labeled_authoritative():
    """The server-to-server key must come back marked authoritative, so a
    checkout-side integration can positively confirm it's safe to act on."""
    payload = {
        "visitor_type_encoded": 1, "traffic_type": 2,
        "session_duration_sec": 120.0, "product_views_count": 5,
        "cart_add_count": 1, "price_sum_viewed": 150.0,
        "time_since_last_action": 12.5,
    }
    response = client.post("/predict_v2?verbose=true", json=payload, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["trust_level"] == "authoritative"


def test_public_key_does_not_authenticate_as_authoritative():
    """The public key must never be accepted where the authoritative key is
    expected — i.e. the two tiers are not interchangeable."""
    assert settings.PUBLIC_API_KEY != settings.API_KEY
    payload = {
        "visitor_type_encoded": 1, "traffic_type": 2,
        "session_duration_sec": 120.0, "product_views_count": 5,
        "cart_add_count": 1, "price_sum_viewed": 150.0,
        "time_since_last_action": 12.5,
    }
    response = client.post("/predict_v2?verbose=true", json=payload, headers=public_headers)
    assert response.json()["trust_level"] != "authoritative"


# ---------------------------------------------------------------------------
# Fail-fast production config validation (config/settings.py:_validate_security)
# Each case spawns a fresh interpreter since the check runs once, at import.
# ---------------------------------------------------------------------------

def test_production_without_api_key_fails_fast():
    result = _run_settings_validation({"ENVIRONMENT": "production"})
    assert result.returncode != 0
    assert "API_KEY is not set" in result.stderr


def test_production_rejects_leaked_default_key():
    result = _run_settings_validation({
        "ENVIRONMENT": "production",
        "API_KEY": "local-dev-key-not-for-prod",
    })
    assert result.returncode != 0
    assert "previously-published placeholder" in result.stderr


def test_production_rejects_matching_public_and_authoritative_keys():
    result = _run_settings_validation({
        "ENVIRONMENT": "production",
        "API_KEY": "same-value-abc123",
        "PUBLIC_API_KEY": "same-value-abc123",
    })
    assert result.returncode != 0
    assert "must not equal API_KEY" in result.stderr


def test_production_with_proper_distinct_keys_boots_cleanly():
    result = _run_settings_validation({
        "ENVIRONMENT": "production",
        "API_KEY": "real-authoritative-secret",
        "PUBLIC_API_KEY": "real-public-secret",
    })
    assert result.returncode == 0, result.stderr


def test_development_mode_does_not_require_any_key():
    """Local dev ergonomics: no key required unless ENVIRONMENT=production."""
    result = _run_settings_validation({"ENVIRONMENT": "development"})
    assert result.returncode == 0, result.stderr
