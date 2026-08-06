"""
FastAPI Microservice (Hardened v2.3).
Includes adversarial cart value clamping, two-tier API key authentication
(authoritative vs advisory), and relative risk-adjusted EMV gating.
"""
import json
from datetime import datetime, timezone
from typing import Optional
import numpy as np
from fastapi import FastAPI, Header, HTTPException, Security, Depends, status
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.schemas import LiveEventInput, PredictionResponse, ConfirmDiscountInput, ConfirmDiscountResponse
from src.causal.t_learner import CausalTLearner
from src.features.intra_session import IntraSessionFeatureExtractor
from src.telemetry.publisher import publish_telemetry_async

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Hardened Causal Uplift & Risk-Adjusted EMV Decision Microservice"
)

# CORS Configuration read safely from settings property
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Two-tier authentication. Returns a trust level, not just pass/fail:

      - "authoritative": caller used API_KEY (server-to-server only — GTM
        Server-Side, your backend, a checkout webhook). Safe to wire directly
        to a real action.
      - "advisory": caller used PUBLIC_API_KEY (client-side/browser). This key
        is assumed public — anything shipped to a browser is, by definition,
        extractable via devtools. Responses under this tier are informational
        only; see predict_causal_intent() and GTM_INTEGRATION_V2.md.

    Neither tier means "unauthenticated" — both still require a matching key,
    which keeps out casual scanning/replay traffic and gives the advisory
    tier a distinct key to rate-limit/quota at the infra layer (Cloud Armor /
    API Gateway) independently of the authoritative one. It does NOT mean the
    advisory tier's input is trustworthy — it isn't, and the code never
    treats it as such.

    Raises:
        HTTPException: 401 if the provided key matches neither configured tier.
    """
    if api_key and settings.API_KEY and api_key == settings.API_KEY:
        return "authoritative"
    if api_key and settings.PUBLIC_API_KEY and api_key == settings.PUBLIC_API_KEY:
        return "advisory"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Invalid or missing API Key"
    )

causal_engine = CausalTLearner()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check probe. Exposes model artifact loading status."""
    return {
        "status": "healthy" if not causal_engine.is_fallback_mode else "degraded",
        "environment": settings.ENVIRONMENT,
        "model_loaded": not causal_engine.is_fallback_mode,
        "control_model": causal_engine.control_loaded,
        "treatment_model": causal_engine.treatment_loaded,
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "gcp_project_id": settings.GCP_PROJECT_ID
    }


def _clamp_event_inputs(event: LiveEventInput) -> LiveEventInput:
    """Clamps adversarial inputs to reasonable maximums based on training data distribution."""
    event.session_duration_sec = min(event.session_duration_sec, 1000)
    event.product_views_count = min(event.product_views_count, 50)
    event.cart_add_count = min(event.cart_add_count, 20)
    event.price_sum_viewed = min(event.price_sum_viewed, 8000)
    event.time_since_last_action = min(event.time_since_last_action, 300)
    return event


@app.post("/predict_v2", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
async def predict_causal_intent(
    event: LiveEventInput,
    verbose: bool = False,
    x_tracking_mode: Optional[str] = Header(None, alias="X-Tracking-Mode"),
    trust_level: str = Depends(verify_api_key)
):
    """
    Real-Time Causal Intent & Risk-Adjusted EMV Decision Endpoint.
    Clamps adversarial cart_value_override inputs to prevent spoofed discount triggers.

    IMPORTANT — advisory tier: when trust_level == "advisory" (client-side/
    public key), the response is UI-hint-only. `trigger_discount` still
    reflects the model's best estimate (so a storefront can show a banner/
    modal), but nothing calling this endpoint with the public key should
    ever apply a real coupon/checkout discount off of it directly — that
    decision must come from a follow-up authoritative call using server-
    known state. See GTM_INTEGRATION_V2.md.
    """
    try:
        event = _clamp_event_inputs(event)

        resolved_tracking_mode = x_tracking_mode or event.tracking_mode or "client_side"

        input_vector = IntraSessionFeatureExtractor.extract_feature_vector(event)
        derived_metrics = IntraSessionFeatureExtractor.compute_derived_session_metrics(event)

        if event.cart_value_override is not None and event.cart_value_override > 0:
            max_sane_cart_cap = max(
                settings.DEFAULT_AOV * settings.MAX_CART_OVERRIDE_MULTIPLIER,
                event.price_sum_viewed * settings.MAX_CART_OVERRIDE_MULTIPLIER
            )
            effective_aov = min(event.cart_value_override, max_sane_cart_cap)
        else:
            effective_aov = settings.DEFAULT_AOV

        result = causal_engine.predict_uplift_and_emv(
            input_vector=input_vector,
            aov=effective_aov
        )

        telemetry_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_inputs": event.model_dump(),
            "derived_metrics": derived_metrics,
            "effective_aov": effective_aov,
            "p_control": result["p_control"],
            "p_treatment": result["p_treatment"],
            "cate_uplift": result["cate_uplift"],
            "net_emv_dollars": result["net_emv_dollars"],
            "trigger_discount": result["trigger_discount"],
            "model_source": result["model_source"],
            "is_holdout": result["is_holdout"],
            "tracking_mode": resolved_tracking_mode,
            "trust_level": trust_level,
            "session_id": event.session_id,
            "version": settings.VERSION
        }

        publish_telemetry_async(telemetry_payload)

        return PredictionResponse(
            trigger_discount=result["trigger_discount"],
            net_emv_dollars=result["net_emv_dollars"] if verbose else None,
            cate_uplift=result["cate_uplift"] if verbose else None,
            p_control=result["p_control"] if verbose else None,
            p_treatment=result["p_treatment"] if verbose else None,
            model_source=result["model_source"],
            is_holdout=result["is_holdout"],
            version=settings.VERSION,
            tracking_mode=resolved_tracking_mode,
            trust_level=trust_level
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Internal Inference Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference execution failed. Please check server logs."
        )


@app.post("/confirm_discount", response_model=ConfirmDiscountResponse, status_code=status.HTTP_200_OK)
async def confirm_discount_server_side(
    payload: ConfirmDiscountInput,
    trust_level: str = Depends(verify_api_key)
):
    """
    Authoritative Step 4b: Checkout / Discount Application Gate.
    Requires server-to-server authoritative API_KEY and definitive cart value.
    """
    if trust_level != "authoritative":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: /confirm_discount requires the authoritative API_KEY."
        )

    try:
        event = _clamp_event_inputs(payload.event)
        input_vector = IntraSessionFeatureExtractor.extract_feature_vector(event)
        
        result = causal_engine.predict_uplift_and_emv(
            input_vector=input_vector,
            aov=payload.server_cart_value
        )
        
        return ConfirmDiscountResponse(
            apply_discount=result["trigger_discount"],
            net_emv_dollars=result["net_emv_dollars"],
            session_id=event.session_id
        )
    except Exception as e:
        print(f"❌ Internal Confirmation Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discount confirmation failed. Please check server logs."
        )

