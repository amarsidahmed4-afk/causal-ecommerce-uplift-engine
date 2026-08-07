# Causal Ecommerce Uplift Engine v2.2

A low-latency microservice designed to optimize e-commerce gross margins using Causal Inference (CATE Estimation), Risk-Adjusted Expected Monetary Value (EMV) Decision Gating, and Dual-Mode Telemetry.

Unlike propensity models that predict raw purchase likelihood (and often discount organic buyers who convert at full price), this microservice estimates the Conditional Average Treatment Effect (CATE) to identify incremental sales caused specifically by an intervention.

---

## Core Architecture

### Propensity vs. Causal Uplift
$$\text{CATE } \tau(X) = \mathbb{E}[Y^{(1)} - Y^{(0)} \mid X]$$

* Propensity Models (v1.0): Estimate $P(Y=1 \mid X)$. Frequently discount high-intent buyers who convert organically.
* Causal Uplift Models (v2.0+): Estimate $\tau(X) = P(Y^{(1)} \mid X) - P(Y^{(0)} \mid X)$. Targets persuadable sessions to protect gross margins.

### Risk-Adjusted Expected Monetary Value (EMV) Decision Gate
Interventions are triggered only when the calculated Expected Monetary Value is positive:

$$\text{EMV} = \left[ P(Y^{(1)}) \times (\text{AOV} \times \text{Margin} - \text{Discount Cost}) \right] - \left[ P(Y^{(0)}) \times (\text{AOV} \times \text{Margin}) \right]$$

$$\text{EMV}_{\text{risk-adjusted}} = \text{EMV} - \lambda \cdot (\sigma_{\text{CATE}} \times \text{AOV} \times \text{Margin})$$

An incentive is recommended only if $\text{EMV}_{\text{risk-adjusted}} \ge (\text{AOV} \times \text{MIN-EMV-AOV-PERCENT-THRESHOLD})$ (configured via settings, default 2%).

---

## Capabilities & Production Scope

### Technical Capabilities
* Inference Performance: C-contiguous 2D NumPy array execution in FastAPI, bypassing Pandas DataFrame instantiation on the critical inference path.
* Calibrated Model Artifacts: LightGBM base estimators wrapped with Platt scaling (`CalibratedClassifierCV`) shipped directly inside the Docker container (`models/*.joblib`).
* Authentication: Two-tier `X-API-Key` model. `API_KEY` (authoritative, server-to-server only) is safe to wire to real actions; `PUBLIC_API_KEY` (advisory, client-side) is assumed public and every response it authenticates is labeled `"trust_level": "advisory"` — see `GTM_INTEGRATION_V2.md` for why a single shared secret can't work when part of the call chain runs in the browser. Neither key has an insecure default: with `ENVIRONMENT=production`, the service refuses to start unless a real, distinct `API_KEY` is configured.
* Adversarial Protection: Clamps all key numeric input features to reasonable maximums based on the training data distribution, preventing malicious callers from passing inflated values to force discount triggers.
* Dual-Mode Telemetry: Supports client-side browser dataLayer events and server-side GTM proxying (`X-Tracking-Mode`).
* Asynchronous Logging: Non-blocking Cloud Pub/Sub publishing for robust, high-throughput telemetry. The default Pub/Sub client includes retry mechanisms for transient network issues.
* Offline Policy Evaluation: Implements Doubly Robust (DR) policy value estimation and Inverse Propensity Weighting (IPW) in `notebooks/04_policy_evaluation.py`.
* Exploration Policy: Configurable 5% randomized holdout arm (`EXPLORATION_RATE`) to continuously collect unbiased online experiment streams (`is_holdout=true`).

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
│       └── deploy.yml          # CI/CD deployment to Google Cloud Run with SHA pinning
├── config/
│   └── settings.py             # Type-safe environment settings
├── models/                     # Serialized Causal LightGBM artifacts (.joblib)
│   ├── t_learner_control.joblib
│   └── t_learner_treatment.joblib
├── notebooks/
│   ├── 01_causal_t_learner_training.py  # A/B dataset generation, calibration & training
│   ├── 02_shopify_store_simulation.py   # Multi-persona traffic simulation
│   ├── 03_merchant_onboarding_test.py   # End-to-end merchant onboarding protocol
│   └── 04_policy_evaluation.py         # Doubly Robust (DR) & IPW offline policy evaluation
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

### 4. Offline Policy Evaluation
```bash
python3 notebooks/04_policy_evaluation.py
```

### 5. Run Development API
```bash
uvicorn src.api.main:app --reload --port 8080
```
Swagger UI available at `http://127.0.0.1:8080/docs`

### 6. Run Merchant Onboarding Simulation
```bash
python3 notebooks/03_merchant_onboarding_test.py
```

### 7. Run Streamlit Dashboard
```bash
streamlit run ui/streamlit_app.py
```

---

## API Payload Specification

**Note:** All requests to `/predict_v2` must include a valid `X-API-Key` header — either `API_KEY` (authoritative) or `PUBLIC_API_KEY` (advisory). Every response includes `"trust_level"` so callers can tell which tier answered; only `"authoritative"` responses should ever be wired to a real coupon/checkout action. See "Trust Model" in `GTM_INTEGRATION_V2.md`.

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
  "version": "2.2.0",
  "tracking_mode": "client_side"
}
```

*(Note: Internal values such as `cate_uplift` and `net_emv_dollars` are hidden by default to prevent client-side inspection. Pass `?verbose=true` on authorized requests to include debug fields.)*

---

## Integration Documentation
* Client-Side Integration: `GTM_INTEGRATION_V2.md`
* Server-Side Integration: `GTM_SERVER_SIDE_INTEGRATION.md`
