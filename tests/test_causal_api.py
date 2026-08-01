"""
Unit & Regression Tests for Causal Uplift Engine API & EMV Gate.
Includes regression tests for Section 5.1 AOV Proxy Bug and Section 4.1 Adversarial Cart Clamping.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from config.settings import settings
from src.causal.emv_gate import evaluate_expected_monetary_value

# Instantiate FastAPI TestClient
client = TestClient(app)


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
    
    response = client.post("/predict_v2?verbose=true", json=payload)
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
    response = client.post("/predict_v2", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    assert "trigger_discount" in data
    assert data["cate_uplift"] is None
    assert data["p_control"] is None
    assert data["p_treatment"] is None


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
    response = client.post("/predict_v2", json=invalid_payload)
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
        min_emv_threshold=0.50,
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
        min_emv_threshold=0.50,
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
    
    response = client.post("/predict_v2?verbose=true", json=adversarial_payload)
    assert response.status_code == 200
    data = response.json()
    
    # Verifies cart_value_override was clamped to sane cap ($195.00), suppressing fake $160.00 EMV inflation
    assert data["net_emv_dollars"] < 10.00
    assert data["trigger_discount"] is False  # Correctly suppressed!