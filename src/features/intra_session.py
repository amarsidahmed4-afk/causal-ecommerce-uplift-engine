"""
Intra-Session Real-Time Feature Pipeline.
Transforms raw clickstream telemetry into engineered velocity and intensity features
in C-contiguous NumPy array format (<1ms execution time).
"""
import numpy as np
from src.api.schemas import LiveEventInput


class IntraSessionFeatureExtractor:
    """
    Sub-millisecond feature engineering pipeline for real-time inference.
    Bypasses Pandas DataFrame creation to maintain ultra-low P99 endpoint latency.
    """

    @staticmethod
    def extract_feature_vector(event: LiveEventInput) -> np.ndarray:
        """
        Transforms LiveEventInput Pydantic schema directly into a 2D NumPy float32 matrix.

        Vector Order (7 features expected by Causal T-Learner):
          0: visitor_type_encoded
          1: traffic_type
          2: session_duration_sec
          3: product_views_count
          4: cart_add_count
          5: price_sum_viewed
          6: time_since_last_action

        Returns:
            np.ndarray of shape (1, 7) in float32 C-contiguous memory layout.
        """
        return np.array([[
            float(event.visitor_type_encoded),
            float(event.traffic_type),
            float(event.session_duration_sec),
            float(event.product_views_count),
            float(event.cart_add_count),
            float(event.price_sum_viewed),
            float(event.time_since_last_action)
        ]], dtype=np.float32)

    @staticmethod
    def compute_derived_session_metrics(event: LiveEventInput) -> dict:
        """
        Calculates derived session intensity and velocity metrics for logging and observability.

        Metrics:
          • action_velocity_per_min: Interaction rate per minute of browsing time
          • avg_price_per_view: Average dollar value of items browsed
          • cart_intent_ratio: Cart conversion density relative to product pageviews
        """
        duration_min = max(event.session_duration_sec / 60.0, 0.01) # Avoid ZeroDivisionError

        # Interaction Velocity (Clicks/Views per minute)
        total_actions = event.product_views_count + event.cart_add_count
        action_velocity = total_actions / duration_min

        # Average Item Price Viewed ($)
        avg_price_per_view = (
            event.price_sum_viewed / event.product_views_count
            if event.product_views_count > 0 else 0.0
        )

        # Cart Conversion Intensity
        cart_intent_ratio = (
            event.cart_add_count / event.product_views_count
            if event.product_views_count > 0 else 0.0
        )

        return {
            "action_velocity_per_min": round(action_velocity, 2),
            "avg_price_per_view": round(avg_price_per_view, 2),
            "cart_intent_ratio": round(cart_intent_ratio, 2)
        }