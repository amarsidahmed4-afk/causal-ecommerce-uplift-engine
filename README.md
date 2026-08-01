# Causal Ecommerce Uplift Engine v2.1

A low-latency microservice designed to optimize e-commerce gross margins using Causal Inference (CATE Estimation), Expected Monetary Value (EMV) Decision Gating, and Dual-Mode Telemetry.

Unlike propensity models that predict raw purchase likelihood (and often discount organic buyers who would convert at full price), this microservice estimates the Conditional Average Treatment Effect (CATE) to identify incremental sales caused specifically by an intervention.

---

## Core Architecture

### Propensity vs. Causal Uplift
$$\text{CATE } \tau(X) = \mathbb{E}[Y^{(1)} - Y^{(0)} \mid X]$$

* Propensity Models (v1.0): Estimate $P(Y=1 \mid X)$. Frequently discount high-intent buyers who convert organically.
* Causal Uplift Models (v2.0+): Estimate $\tau(X) = P(Y^{(1)} \mid X) - P(Y^{(0)} \mid X)$. Targets persuadable sessions to protect gross margins.

### Expected Monetary Value (EMV) Decision Gate
Interventions are triggered only when the calculated Expected Monetary Value is positive:

$$\text{EMV} = \left[ P(Y^{(1)}) \times (\text{AOV} \times \text{Margin} - \text{Discount Cost}) \right] - \left[ P(Y^{(0)}) \times (\text{AOV} \times \text{Margin}) \right]$$

An incentive is recommended only if $\text{EMV} \ge \text{MIN\_EMV\_THRESHOLD}$ (configured via settings).

---

## Capabilities & Production Scope

### Technical Capabilities
* Inference Performance: C-contiguous 2D NumPy array execution in FastAPI, bypassing Pandas DataFrame instantiation on the critical inference path.
* Probability Calibration: LightGBM base estimators wrapped with Platt scaling (`CalibratedClassifierCV`) to ensure predicted probabilities reflect empirical rates before entering financial formulas.
* Dual-Mode Telemetry: Supports client-side browser dataLayer events and server-side GTM proxying.
* Asynchronous Logging: Non-blocking Cloud Pub/Sub publishing with direct BigQuery streaming.
* Input Validation & Security: Pydantic upper bounds on input fields, optional API key header authentication (`X-API-Key`), sanitized error responses, and customizable CORS origins.

### Production Prerequisites
The model artifacts provided in this repository are trained on semi-synthetic A/B clickstream data (`notebooks/01_causal_t_learner_training.py`) to demonstrate pipeline functionality. Before deploying to live traffic with real marketing budgets:
1. The T-Learner must be retrained on real historical randomized A/B experiment data or logged online holdout streams.
2. Store economics (AOV, Gross Margin %, Discount Rate, and MIN_EMV_THRESHOLD) must be tuned to match the merchant's unit economics.

---

## Repository Structure

```text
causal-ecommerce-uplift-engine/
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD deployment to Google Cloud Run
├── config/
│   └── settings.py             # Type-safe environment settings
├── models/                     # Serialized Causal LightGBM artifacts (.joblib)
│   ├── t_learner_control.joblib
│   └── t_learner_treatment.joblib
├── notebooks/
│   ├── 01_causal_t_learner_training.py  # A/B dataset generation, calibration & training
│   ├── 02_shopify_store_simulation.py   # Multi-persona traffic simulation
│   └── 03_merchant_onboarding_test.py   # End-to-end merchant onboarding protocol
├── src/
│   ├── api/                    # FastAPI routes (/predict_v2) & Pydantic schemas
│   ├── causal/                 # T-Learner CATE estimator & EMV Decision Gate
│   ├── features/               # Intra-session NumPy feature pipeline
│   └── telemetry/              # Async Cloud Pub/Sub publisher
├── tests/                      # Pytest unit & regression test suite
├── ui/                         # Streamlit interactive dashboard
├── Dockerfile                  # Container definition (runs as appuser)
├── GTM_INTEGRATION_V2.md       # Client-side integration guide
├── GTM_SERVER_SIDE_INTEGRATION.md # Server-side integration guide
├── pytest.ini                  # Pytest configuration
└── requirements.txt            # Production dependencies
```

---

## Quickstart

### 1. Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Model Calibration & Training
```bash
python3 notebooks/01_causal_t_learner_training.py
```

### 3. Test Suite Execution
```bash
python3 -m pytest
```

### 4. Run Development API
```bash
uvicorn src.api.main:app --reload --port 8000
```
Swagger UI available at `http://127.0.0.1:8000/docs`

### 5. Run Merchant Simulation
```bash
python3 notebooks/03_merchant_onboarding_test.py
```

### 6. Run Streamlit Dashboard
```bash
streamlit run ui/streamlit_app.py
```

---

## API Payload Specification

### Request Body (`POST /predict_v2`)
```json
{
  "visitor_type_encoded": 1,
  "traffic_type": 2,
  "session_duration_sec": 120.0,
  "product_views_count": 5,
  "cart_add_count": 1,
  "price_sum_viewed": 150.0,
  "time_since_last_action": 12.5,
  "tracking_mode": "client_side"
}
```

### Response Body
```json
{
  "trigger_discount": true,
  "model_source": "trained_artifact",
  "is_holdout": false,
  "version": "2.1.0",
  "tracking_mode": "client_side"
}
```

*(Note: Internal values such as `cate_uplift` and `net_emv_dollars` are hidden by default to prevent client-side inspection. Pass `?verbose=true` on authorized requests to include debug fields.)*

---

## Integration Documentation
* Client-Side Integration: `GTM_INTEGRATION_V2.md`
* Server-Side Integration: `GTM_SERVER_SIDE_INTEGRATION.md`