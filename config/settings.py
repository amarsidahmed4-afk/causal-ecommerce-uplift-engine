import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized Application Configuration.
    Reads automatically from environment variables or .env file.
    """
    # -------------------------------------------------------------------------
    # 1. Application Metadata
    # -------------------------------------------------------------------------
    PROJECT_NAME: str = "Causal Ecommerce Uplift Engine"
    VERSION: str = "2.0.0"
    DEBUG: bool = False

    # -------------------------------------------------------------------------
    # 2. Google Cloud Platform Infrastructure
    # -------------------------------------------------------------------------
    GCP_PROJECT_ID: str = "gtm-m4299zzd-nti4m"
    GCP_REGION: str = "europe-west1"
    PUBSUB_TOPIC_ID: str = "intent-telemetry-stream"
    BQ_DATASET_ID: str = "ml_logs"
    BQ_TABLE_ID: str = "intent_predictions_log"

    # -------------------------------------------------------------------------
    # 3. Financial & Expected Monetary Value (EMV) Parameters
    # -------------------------------------------------------------------------
    DEFAULT_AOV: float = 65.00            # Average Order Value ($)
    DEFAULT_GROSS_MARGIN: float = 0.40    # 40% Gross Profit Margin
    DEFAULT_DISCOUNT_RATE: float = 0.10   # 10% Discount Rate ($6.50 cost)
    MIN_EMV_THRESHOLD: float = 0.50      # Minimum net $ gain to trigger intervention

    # -------------------------------------------------------------------------
    # 4. Model Artifact Paths
    # -------------------------------------------------------------------------
    MODEL_CONTROL_PATH: str = "models/t_learner_control.joblib"
    MODEL_TREATMENT_PATH: str = "models/t_learner_treatment.joblib"

    # Configuration for .env file loading
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate global settings singleton
settings = Settings()