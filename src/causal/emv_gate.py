"""
Expected Monetary Value (EMV) Decision Gate.
Evaluates whether giving a discount generates net positive expected dollar margin.
"""
from config.settings import settings


def evaluate_expected_monetary_value(
    p_control: float,
    p_treatment: float,
    aov: float = None,
    gross_margin: float = None,
    discount_rate: float = None,
    min_emv_threshold: float = None
) -> tuple[bool, float, float]:
    """
    Calculates Expected Monetary Value (EMV) and decides whether to trigger an incentive.

    Args:
        p_control: Conversion probability WITHOUT discount P(Y=1 | Treatment=0)
        p_treatment: Conversion probability WITH discount P(Y=1 | Treatment=1)
        aov: Average Order Value ($). Defaults to settings.DEFAULT_AOV.
        gross_margin: Profit margin ratio (0.0 to 1.0). Defaults to settings.DEFAULT_GROSS_MARGIN.
        discount_rate: Offered discount ratio (0.0 to 1.0). Defaults to settings.DEFAULT_DISCOUNT_RATE.
        min_emv_threshold: Minimum net $ gain to trigger intervention.

    Returns:
        tuple[trigger_action (bool), net_emv_dollars (float), cate_uplift (float)]
    """
    # Use defaults from config/settings.py if parameters are not overridden
    aov = aov if aov is not None else settings.DEFAULT_AOV
    gross_margin = gross_margin if gross_margin is not None else settings.DEFAULT_GROSS_MARGIN
    discount_rate = discount_rate if discount_rate is not None else settings.DEFAULT_DISCOUNT_RATE
    min_emv_threshold = min_emv_threshold if min_emv_threshold is not None else settings.MIN_EMV_THRESHOLD

    # Financial Math
    margin_dollars = aov * gross_margin          # Profit per organic sale
    discount_cost = aov * discount_rate          # Cost of the incentive

    # Expected Dollar Value Calculations
    emv_control = p_control * margin_dollars                       # Value without discount
    emv_treatment = p_treatment * (margin_dollars - discount_cost) # Value with discount

    # Net Financial Uplift ($)
    net_emv = emv_treatment - emv_control
    cate_uplift = p_treatment - p_control

    # Decision Logic: Trigger ONLY if expected net dollar gain exceeds threshold
    trigger_action = bool(net_emv >= min_emv_threshold)

    return trigger_action, float(net_emv), float(cate_uplift)