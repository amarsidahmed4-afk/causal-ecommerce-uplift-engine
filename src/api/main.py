"""
FastAPI High-Throughput Microservice.
Supports dual Client-Side and Server-Side tracking with zero-Pandas NumPy inference.
"""
import json
from datetime import datetime, timezone
from typing import Optional
import numpy as np
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.schemas import LiveEventInput, PredictionResponse
from src.causal.t_learner import CausalTLearner
from src.features.intra_session import IntraSessionFeatureExtractor
from src.telemetry.publisher import publish_telemetry_async

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Low-Latency Causal Uplift & EMV Decision Microservice (Dual Client & Server-Side Tracking)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

causal_engine = CausalTLearner()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint for Cloud Run container probes."""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "gcp_project_id": settings.GCP_PROJECT_ID
    }


@app.post("/predict_v2", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
async def predict_causal_intent(
    event: LiveEventInput,
    x_tracking_mode: Optional[str] = Header(None, alias="X-Tracking-Mode")
):
    """
    Real-Time Causal Intent & EMV Decision Endpoint.
    Accepts telemetry from browser JavaScript or Server-Side (GTM Server / Shopify app) proxies.
    """
    try:
        # Determine tracking mode (Header takes priority over payload body)
        resolved_tracking_mode = x_tracking_mode or event.tracking_mode or "client_side"

        # 1. Feature Extraction: Construct 2D NumPy array in C-contiguous memory
        input_vector = IntraSessionFeatureExtractor.extract_feature_vector(event)
        
        # 2. Compute Derived Session Metrics
        derived_metrics = IntraSessionFeatureExtractor.compute_derived_session_metrics(event)

        # 3. Execute Causal Uplift Estimation & Financial EMV Gate
        custom_aov = event.cart_value_override if event.cart_value_override is not None else event.price_sum_viewed
        result = causal_engine.predict_uplift_and_emv(
            input_vector=input_vector,
            aov=custom_aov if custom_aov > 0 else None
        )

        # 4. Construct Telemetry Payload for Async Logging
        telemetry_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_inputs": json.dumps(event.model_dump()),
            "derived_metrics": json.dumps(derived_metrics),
            "p_control": result["p_control"],
            "p_treatment": result["p_treatment"],
            "cate_uplift": result["cate_uplift"],
            "net_emv_dollars": result["net_emv_dollars"],
            "trigger_discount": result["trigger_discount"],
            "tracking_mode": resolved_tracking_mode,
            "session_id": event.session_id,
            "version": settings.VERSION
        }

        # 5. Stream to Cloud Pub/Sub asynchronously (Non-blocking)
        publish_telemetry_async(telemetry_payload)

        # 6. Return synchronous JSON response payload
        return PredictionResponse(
            trigger_discount=result["trigger_discount"],
            net_emv_dollars=result["net_emv_dollars"],
            cate_uplift=result["cate_uplift"],
            p_control=result["p_control"],
            p_treatment=result["p_treatment"],
            version=settings.VERSION,
            tracking_mode=resolved_tracking_mode
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference execution failed: {str(e)}"
        )