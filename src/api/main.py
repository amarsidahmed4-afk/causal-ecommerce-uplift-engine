"""
FastAPI High-Throughput Microservice.
Executes zero-Pandas NumPy inference, Causal EMV Gate, and Async Pub/Sub Logging.
"""
from datetime import datetime, timezone
import numpy as np
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.schemas import LiveEventInput, PredictionResponse
from src.causal.t_learner import CausalTLearner
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
    allow_origins=["*"], # Configure for specific storefront domain in production
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
    Converts input directly into a 2D NumPy array for ultra-low latency execution.
    """
    try:
        # 1. Zero-Pandas Allocation: Construct 2D NumPy array directly in C-contiguous memory
        input_vector = np.array([[
            event.visitor_type_encoded,
            event.traffic_type,
            event.session_duration_sec,
            event.product_views_count,
            event.cart_add_count,
            event.price_sum_viewed,
            event.time_since_last_action
        ]], dtype=np.float32)

        # 2. Execute Causal Uplift Estimation & Financial EMV Gate
        custom_aov = event.cart_value_override if event.cart_value_override is not None else event.price_sum_viewed
        result = causal_engine.predict_uplift_and_emv(
            input_vector=input_vector,
            aov=custom_aov if custom_aov > 0 else None
        )

        # 3. Construct Telemetry Payload for Async Logging
        telemetry_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_inputs": event.model_dump(),
            "p_control": result["p_control"],
            "p_treatment": result["p_treatment"],
            "cate_uplift": result["cate_uplift"],
            "net_emv_dollars": result["net_emv_dollars"],
            "trigger_discount": result["trigger_discount"],
            "version": settings.VERSION
        }

        # 4. Stream to Cloud Pub/Sub asynchronously (Non-blocking)
        publish_telemetry_async(telemetry_payload)

        # 5. Return synchronous JSON response payload
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