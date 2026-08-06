"""
Centralized Application Configuration.
Reads automatically from environment variables or .env file.
"""
import os
import json
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Metadata
    PROJECT_NAME: str = "Causal Ecommerce Uplift Engine"
    VERSION: str = "2.3.0"
    DEBUG: bool = False

    # "development" (default, safe local ergonomics) or "production" (strict, fail-fast).
    # Deploy pipelines MUST set ENVIRONMENT=production explicitly (see deploy.yml).
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Security & Access Control — two-tier trust model.
    #
    # API_KEY (authoritative): server-to-server only. Anything authenticated with
    # this key may be safely wired to a real action (coupon minting, checkout
    # discounts). NEVER embed this in browser-executed code — see
    # GTM_INTEGRATION_V2.md "Trust Model".
    #
    # PUBLIC_API_KEY (advisory): assume this is public the moment it ships to a
    # browser, because it is. Requests authenticated with it are rate-limit
    # candidates and always get an advisory-only response — see verify_api_key()
    # in src/api/main.py. It exists so client-side callers aren't fully
    # unauthenticated (basic bot/scanner friction + per-key quota in front
    # of Cloud Armor/API Gateway), not to gate real decisions.
    #
    # Neither has an insecure default. An unset key means "this tier is
    # disabled" (see _validate_security below), not "accept anything."
    API_KEY: str = os.getenv("API_KEY", "dev-authoritative" if os.getenv("ENVIRONMENT", "development") == "development" else "")
    PUBLIC_API_KEY: str = os.getenv("PUBLIC_API_KEY", "dev-public" if os.getenv("ENVIRONMENT", "development") == "development" else "")

    # Typed as str so pydantic_settings never attempts json.loads("") on empty env vars
    CORS_ORIGINS: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        """Safely parses empty strings, CSVs, or JSON lists into a Python list."""
        raw = self.CORS_ORIGINS.strip() if self.CORS_ORIGINS else ""
        if not raw or raw == "*":
            return ["*"]
        if raw.startswith("[") and raw.endswith("]"):
            try:
                return json.loads(raw)
            except Exception:
                pass
        return [i.strip() for i in raw.split(",") if i.strip()]

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
    MIN_EMV_AOV_PERCENT_THRESHOLD: float = 0.02  # Requires net EMV gain of at least 2% of AOV
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


# Known-bad values from earlier revisions of this project. If any of these are
# still set, treat it as a live incident, not a warning: a public repo/commit
# history has already published these exact strings.
_LEAKED_DEFAULT_KEYS = {"local-dev-key-not-for-prod"}


def _validate_security(cfg: "Settings") -> None:
    """
    Fail fast and loud rather than silently serving an unauthenticated or
    trivially-guessable endpoint. Runs at import time so a misconfigured
    container crash-loops on boot (visible in Cloud Run deploy logs) instead
    of serving traffic in a degraded, silently-open state.

    Kept as a standalone function (not inline at module scope) so it can be
    exercised directly in tests without needing a subprocess per case.
    """
    if cfg.ENVIRONMENT not in ("development", "production"):
        raise RuntimeError(
            f"FATAL: ENVIRONMENT='{cfg.ENVIRONMENT}' is not valid. "
            "Set ENVIRONMENT to 'development' or 'production'."
        )

    if cfg.ENVIRONMENT != "production":
        return  # Local/dev ergonomics: no key required to just run the app.

    if not cfg.API_KEY:
        raise RuntimeError(
            "FATAL: ENVIRONMENT=production but API_KEY is not set. "
            "This service refuses to start without authentication configured. "
            "Generate one with `openssl rand -hex 32` and inject it via your "
            "deployment platform's secret store (see .github/workflows/deploy.yml)."
        )
    if cfg.API_KEY in _LEAKED_DEFAULT_KEYS:
        raise RuntimeError(
            "FATAL: API_KEY is a previously-published placeholder value. "
            "Rotate it immediately and set a real secret."
        )
    if cfg.PUBLIC_API_KEY and cfg.PUBLIC_API_KEY == cfg.API_KEY:
        raise RuntimeError(
            "FATAL: PUBLIC_API_KEY must not equal API_KEY. The public key is "
            "assumed leaked by design (it ships to browsers); reusing the "
            "authoritative key here defeats the trust-tier split entirely."
        )
    if cfg.cors_origins_list == ["*"]:
        raise RuntimeError(
            "FATAL: CORS_ORIGINS cannot be '*' in production. "
            "Set it to your actual storefront domain(s) for defense-in-depth."
        )


settings = Settings()
_validate_security(settings)
