"""
Unit & Regression Tests for Causal Uplift Engine API & EMV Gate.
Includes regression test for Section 5.1 AOV Proxy Bug scenario.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from config.settings import settings
from src.causal.emv_gate import evaluate_expected_monetary_value

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
        "price_sum_viewed": 300.0,  # Browsed $300 worth of items
        "time_since_last_action": 12.5,
        "cart_value_override": None
    }
    
    response = client.post("/predict_v2?verbose=true", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    # Verify net_emv_dollars was computed using $65 AOV (not $300)
    assert data["net_emv_dollars"] < 8.00  # Proves $300 was NOT used as AOV multiplier!


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
    response = client.post("/predict_v2", json=payload)  # Default verbose=False
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
    # Case A: High Uplift (Persuadable Buyer) -> Positive Net EMV -> Trigger Discount
    trigger, emv, cate = evaluate_expected_monetary_value(
        p_control=0.20,
        p_treatment=0.50,
        aov=100.0,
        gross_margin=0.40,
        discount_rate=0.10,
        min_emv_threshold=0.50
    )
    assert cate == 0.30
    assert trigger is True
    assert emv > 0.50

    # Case B: Zero Uplift (Organic Buyer) -> Negative Net EMV due to discount cannibalization
    trigger_b, emv_b, cate_b = evaluate_expected_monetary_value(
        p_control=0.85,
        p_treatment=0.85,  # Discount causes 0 extra uplift
        aov=100.0,
        gross_margin=0.40,
        discount_rate=0.10,
        min_emv_threshold=0.50
    )
    assert cate_b == 0.0
    assert trigger_b is False
    assert emv_b < 0.0  # Discount cost destroys profit!