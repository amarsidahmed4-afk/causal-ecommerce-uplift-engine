"""
FastAPI Microservice (Hardened v2.2).
Includes adversarial cart value clamping, API key authentication, and risk-adjusted EMV gating.
"""
import json
from datetime import datetime, timezone
from typing import Optional
import numpy as np
from fastapi import FastAPI, Header, HTTPException, Security, Depends, status
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.schemas import LiveEventInput, PredictionResponse
from src.causal.t_learner import CausalTLearner
from src.features.intra_session import IntraSessionFeatureExtractor
from src.telemetry.publisher import publish_telemetry_async

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Hardened Causal Uplift & Risk-Adjusted EMV Decision Microservice"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    """Enforces API Key verification if settings.API_KEY is configured."""
    if settings.API_KEY:
        if not api_key or api_key != settings.API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid or missing API Key"
            )
    return api_key

causal_engine = CausalTLearner()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check probe. Exposes model artifact loading status."""
    return {
        "status": "healthy" if not causal_engine.is_fallback_mode else "degraded",
        "model_loaded": not causal_engine.is_fallback_mode,
        "control_model": causal_engine.control_loaded,
        "treatment_model": causal_engine.treatment_loaded,
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "gcp_project_id": settings.GCP_PROJECT_ID
    }


@app.post("/predict_v2", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
async def predict_causal_intent(
    event: LiveEventInput,
    verbose: bool = False,
    x_tracking_mode: Optional[str] = Header(None, alias="X-Tracking-Mode"),
    api_key: Optional[str] = Depends(verify_api_key)
):
    """
    Real-Time Causal Intent & Risk-Adjusted EMV Decision Endpoint.
    Clamps adversarial cart_value_override inputs to prevent spoofed discount triggers.
    """
    try:
        resolved_tracking_mode = x_tracking_mode or event.tracking_mode or "client_side"

        input_vector = IntraSessionFeatureExtractor.extract_feature_vector(event)
        derived_metrics = IntraSessionFeatureExtractor.compute_derived_session_metrics(event)

        # ---------------------------------------------------------------------
        # ADVERSARIAL CART OVERRIDE CLAMPING (Section 4.1 Fix)
        # Prevents caller from passing cart_value_override=9999.99 to force a discount.
        # Cart override cannot exceed MAX_CART_OVERRIDE_MULTIPLIER * max(AOV, price_sum_viewed).
        # ---------------------------------------------------------------------
        if event.cart_value_override is not None and event.cart_value_override > 0:
            max_sane_cart_cap = max(
                settings.DEFAULT_AOV * settings.MAX_CART_OVERRIDE_MULTIPLIER,
                event.price_sum_viewed * settings.MAX_CART_OVERRIDE_MULTIPLIER
            )
            effective_aov = min(event.cart_value_override, max_sane_cart_cap)
        else:
            effective_aov = settings.DEFAULT_AOV

        # Execute Causal Uplift & Risk-Adjusted EMV Gate
        result = causal_engine.predict_uplift_and_emv(
            input_vector=input_vector,
            aov=effective_aov
        )

        telemetry_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_inputs": json.dumps(event.model_dump()),
            "derived_metrics": json.dumps(derived_metrics),
            "effective_aov": effective_aov,
            "p_control": result["p_control"],
            "p_treatment": result["p_treatment"],
            "cate_uplift": result["cate_uplift"],
            "net_emv_dollars": result["net_emv_dollars"],
            "trigger_discount": result["trigger_discount"],
            "model_source": result["model_source"],
            "is_holdout": result["is_holdout"],
            "tracking_mode": resolved_tracking_mode,
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
            tracking_mode=resolved_tracking_mode
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Internal Inference Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference execution failed. Please check server logs."
        )