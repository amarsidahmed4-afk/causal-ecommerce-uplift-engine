"""
Centralized Application Configuration.
Reads automatically from environment variables or .env file.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Metadata
    PROJECT_NAME: str = "Causal Ecommerce Uplift Engine"
    VERSION: str = "2.2.0"
    DEBUG: bool = False

    # Security & Access Control
    API_KEY: Optional[str] = os.getenv("API_KEY", None) # If configured, enforces X-API-Key header verification
    CORS_ORIGINS: list[str] = ["*"]                     # Set to specific storefront domain in production

    # Infrastructure Config
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "gtm-m4299zzd-nti4m")
    GCP_REGION: str = os.getenv("GCP_REGION", "europe-west1")
    PUBSUB_TOPIC_ID: str = os.getenv("PUBSUB_TOPIC_ID", "intent-telemetry-stream")
    BQ_DATASET_ID: str = os.getenv("BQ_DATASET_ID", "ml_logs")
    BQ_TABLE_ID: str = os.getenv("BQ_TABLE_ID", "causal_predictions_log")

    # Financial & EMV Decision Parameters
    DEFAULT_AOV: float = 65.00                       # Default Average Order Value ($)
    DEFAULT_GROSS_MARGIN: float = 0.40               # 40% Gross Profit Margin ($26.00 profit)
    DEFAULT_DISCOUNT_RATE: float = 0.10              # 10% Discount Rate ($6.50 cost)
    MIN_EMV_THRESHOLD: float = 3.50                 # Requires at least $3.50 net EMV gain
    MAX_CART_OVERRIDE_MULTIPLIER: float = 3.0       # Clamps cart_value_override to max 3x price_sum_viewed or AOV
    RISK_AVERSION_LAMBDA: float = 0.5               # Risk penalty coefficient for CATE variance

    # Production Exploration Policy (Holdout Arm)
    EXPLORATION_RATE: float = 0.05                  # 5% randomized holdout for online CATE re-estimation

    # Model Artifact Paths
    MODEL_CONTROL_PATH: str = "models/t_learner_control.joblib"
    MODEL_TREATMENT_PATH: str = "models/t_learner_treatment.joblib"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()