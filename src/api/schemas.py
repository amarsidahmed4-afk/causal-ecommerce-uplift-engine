"""
Pydantic V2 Schemas for Real-Time Intra-Session Event Payload Validation.
"""
from typing import Optional
from pydantic import BaseModel, Field


class LiveEventInput(BaseModel):
    """Real-time event payload captured from storefront dataLayer."""
    visitor_type_encoded: int = Field(..., ge=0, le=2, description="0: New_Visitor, 1: Returning_Visitor, 2: Other")
    traffic_type: int = Field(..., ge=1, le=20, description="Traffic source category ID (1-20)")
    session_duration_sec: float = Field(..., ge=0.0, description="Total active session duration in seconds")
    product_views_count: int = Field(..., ge=0, description="Count of product pages viewed in current session")
    cart_add_count: int = Field(..., ge=0, description="Count of items currently added to shopping cart")
    price_sum_viewed: float = Field(..., ge=0.0, description="Cumulative sum of item prices viewed ($)")
    time_since_last_action: float = Field(..., ge=0.0, description="Seconds elapsed since last user click/action")
    
    # Optional override for custom shopping cart dollar value
    cart_value_override: Optional[float] = Field(None, ge=0.0, description="Current shopping cart value ($) if available")


class PredictionResponse(BaseModel):
    """Synchronous JSON response returned to Google Tag Manager / Storefront."""
    trigger_discount: bool = Field(..., description="Whether Expected Monetary Value is positive")
    net_emv_dollars: float = Field(..., description="Net expected profit gain in dollars ($)")
    cate_uplift: float = Field(..., description="Conditional Average Treatment Effect probability uplift")
    p_control: float = Field(..., description="Conversion probability without discount")
    p_treatment: float = Field(..., description="Conversion probability with discount")
    version: str = Field(..., description="API Version")