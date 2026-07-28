"""
Unit and Integration Tests for Causal Uplift Engine API & EMV Gate.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.causal.emv_gate import evaluate_expected_monetary_value

client = TestClient(app)


def test_health_check():
    """Tests /health endpoint status and metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_predict_v2_valid_payload():
    """Tests /predict_v2 endpoint with valid live event input."""
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
    assert "net_emv_dollars" in data
    assert "cate_uplift" in data
    assert isinstance(data["trigger_discount"], bool)


def test_predict_v2_invalid_payload():
    """Tests Pydantic validation error on negative session duration."""
    invalid_payload = {
        "visitor_type_encoded": 1,
        "traffic_type": 2,
        "session_duration_sec": -10.0,  # Invalid negative duration
        "product_views_count": 5,
        "cart_add_count": 1,
        "price_sum_viewed": 150.0,
        "time_since_last_action": 12.5
    }
    response = client.post("/predict_v2", json=invalid_payload)
    assert response.status_code == 422  # Unprocessable Entity


def test_emv_gate_math_cases():
    """Tests Expected Monetary Value calculation logic directly."""
    # Case A: High Uplift (Persuadable Buyer) -> Positive Net EMV -> Trigger Discount
    trigger, emv, cate = evaluate_expected_monetary_value(
        p_control=0.20,
        p_treatment=0.50,
        aov=100.0,
        gross_margin=0.40,      # $40 margin
        discount_rate=0.10,     # $10 discount cost
        min_emv_threshold=0.50
    )
    assert cate == 0.30
    assert trigger is True
    assert emv > 0.50

    # Case B: Zero Uplift (Organic Buyer) -> Negative Net EMV due to discount cannibalization
    trigger_b, emv_b, cate_b = evaluate_expected_monetary_value(
        p_control=0.85,
        p_treatment=0.85,      # Discount causes 0 extra uplift
        aov=100.0,
        gross_margin=0.40,
        discount_rate=0.10,
        min_emv_threshold=0.50
    )
    assert cate_b == 0.0
    assert trigger_b is False
    assert emv_b < 0.0  # Discount cost destroys profit!