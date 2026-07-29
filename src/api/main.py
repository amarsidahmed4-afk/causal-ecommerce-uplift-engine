"""
FastAPI High-Throughput Microservice.
Executes zero-Pandas NumPy inference, Causal EMV Gate, and Async Pub/Sub Logging.
"""
import json
from datetime import datetime, timezone
import numpy as np
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.schemas import LiveEventInput, PredictionResponse
from src.causal.t_learner import CausalTLearner
from src.features.intra_session import IntraSessionFeatureExtractor
from src.telemetry.publisher import publish_telemetry_async

# Initialize FastAPI Application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Low-Latency Causal Uplift & EMV Decision Microservice"
)

# Enable CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Causal Engine Singleton on startup
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
async def predict_causal_intent(event: LiveEventInput):
    """
    Real-Time Causal Intent & EMV Decision Endpoint.
    Uses IntraSessionFeatureExtractor for zero-Pandas NumPy vector construction (<1ms).
    """
    try:
        # 1. Feature Extraction: Construct 2D NumPy array in C-contiguous memory
        input_vector = IntraSessionFeatureExtractor.extract_feature_vector(event)
        
        # 2. Compute Derived Session Metrics for Telemetry Logging
        derived_metrics = IntraSessionFeatureExtractor.compute_derived_session_metrics(event)

        # 3. Execute Causal Uplift Estimation & Financial EMV Gate
        custom_aov = event.cart_value_override if event.cart_value_override is not None else event.price_sum_viewed
        result = causal_engine.predict_uplift_and_emv(
            input_vector=input_vector,
            aov=custom_aov if custom_aov > 0 else None
        )

        # 4. Construct Rich Telemetry Payload with Stringified JSON for BigQuery Pub/Sub
        telemetry_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_inputs": json.dumps(event.model_dump()),        # Stringified JSON
            "derived_metrics": json.dumps(derived_metrics),          # Stringified JSON
            "p_control": result["p_control"],
            "p_treatment": result["p_treatment"],
            "cate_uplift": result["cate_uplift"],
            "net_emv_dollars": result["net_emv_dollars"],
            "trigger_discount": result["trigger_discount"],
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
            version=settings.VERSION
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference execution failed: {str(e)}"
        )