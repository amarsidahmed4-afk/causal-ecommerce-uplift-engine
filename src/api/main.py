"""
FastAPI Microservice (Hardened).
Fixes AOV proxy bug, secures endpoints, sanitizes exceptions, and exposes model loading health.
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
    description="Hardened Low-Latency Causal Uplift & EMV Decision Microservice"
)

# CORS Configuration from Settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Authentication Setup
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    """Verifies API key if settings.API_KEY is configured."""
    if settings.API_KEY:
        if not api_key or api_key != settings.API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid or missing API Key"
            )
    return api_key

# Singleton Causal Engine
causal_engine = CausalTLearner()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check probe. Exposes explicit model artifact loading status."""
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
    Real-Time Causal Intent & EMV Decision Endpoint.
    FIXED: Resolves AOV proxy bug by using settings.DEFAULT_AOV when cart_value_override is missing.
    """
    try:
        resolved_tracking_mode = x_tracking_mode or event.tracking_mode or "client_side"

        # 1. Feature Vector Extraction (NumPy C-Contiguous Memory)
        input_vector = IntraSessionFeatureExtractor.extract_feature_vector(event)
        derived_metrics = IntraSessionFeatureExtractor.compute_derived_session_metrics(event)

        # 2. CRITICAL FIX: NEVER default AOV to price_sum_viewed!
        # Use explicit cart_value_override if provided (>0), otherwise default to settings.DEFAULT_AOV
        effective_aov = (
            event.cart_value_override 
            if (event.cart_value_override is not None and event.cart_value_override > 0) 
            else settings.DEFAULT_AOV
        )

        # 3. Execute Causal Uplift & Financial EMV Gate
        result = causal_engine.predict_uplift_and_emv(
            input_vector=input_vector,
            aov=effective_aov
        )

        # 4. Telemetry Payload for Pub/Sub Streaming
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

        # 5. Async Pub/Sub Streaming
        publish_telemetry_async(telemetry_payload)

        # 6. Response Payload (Sanitized: Raw probabilities only exposed if verbose=True)
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
        # Sanitized error message (does not leak stack traces to unauthenticated callers)
        print(f"❌ Internal Inference Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference execution failed. Please check server logs."
        )