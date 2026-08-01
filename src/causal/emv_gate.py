"""
Risk-Adjusted Expected Monetary Value (EMV) Decision Gate.
Evaluates whether giving a discount generates net positive expected profit,
accounting for CATE prediction variance and risk-aversion penalty.
"""
import numpy as np
from config.settings import settings


def evaluate_expected_monetary_value(
    p_control: float,
    p_treatment: float,
    cate_std_err: float = 0.05,
    aov: float = None,
    gross_margin: float = None,
    discount_rate: float = None,
    min_emv_threshold: float = None,
    risk_lambda: float = None
) -> tuple[bool, float, float, float]:
    """
    Calculates Risk-Adjusted Expected Monetary Value (EMV) and decides whether to trigger an incentive.

    Formula:
      EMV_mean = P(Y^1) * (AOV * Margin - Discount) - P(Y^0) * (AOV * Margin)
      EMV_risk_adjusted = EMV_mean - lambda * (sigma_CATE * AOV * Margin)

    Returns:
        tuple[trigger_action (bool), risk_adjusted_emv (float), net_emv_mean (float), cate_uplift (float)]
    """
    aov = aov if aov is not None else settings.DEFAULT_AOV
    gross_margin = gross_margin if gross_margin is not None else settings.DEFAULT_GROSS_MARGIN
    discount_rate = discount_rate if discount_rate is not None else settings.DEFAULT_DISCOUNT_RATE
    min_emv_threshold = min_emv_threshold if min_emv_threshold is not None else settings.MIN_EMV_THRESHOLD
    risk_lambda = risk_lambda if risk_lambda is not None else settings.RISK_AVERSION_LAMBDA

    # Financial Math
    margin_dollars = aov * gross_margin          # Profit per organic sale
    discount_cost = aov * discount_rate          # Cost of incentive

    # Expected Dollar Value
    emv_control = p_control * margin_dollars                       
    emv_treatment = p_treatment * (margin_dollars - discount_cost) 

    net_emv_mean = emv_treatment - emv_control
    cate_uplift = p_treatment - p_control

    # Risk Adjustment Penalty (Subtracts risk_lambda * standard_error_dollars)
    emv_uncertainty_dollars = cate_std_err * margin_dollars
    net_emv_risk_adjusted = net_emv_mean - (risk_lambda * emv_uncertainty_dollars)

    # Decision Logic: Trigger ONLY if Risk-Adjusted EMV meets minimum threshold
    trigger_action = bool(net_emv_risk_adjusted >= min_emv_threshold)

    return trigger_action, float(net_emv_risk_adjusted), float(net_emv_mean), float(cate_uplift)