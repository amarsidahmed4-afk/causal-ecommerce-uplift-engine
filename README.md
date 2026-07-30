# Causal Ecommerce Uplift Engine v2.0

An enterprise-grade, low-latency microservice designed to maximize e-commerce gross margins using **Causal Inference (CATE Estimation)**, **Expected Monetary Value (EMV) Decision Gating**, and **Dual Client & Server-Side Tracking**.

Unlike traditional propensity engines that predict *intent* (and waste discounts on organic buyers), this engine isolates the **Conditional Average Treatment Effect (CATE)**—identifying the exact subset of users whose purchasing behavior is positively incremented by an intervention.

---

## Core Architecture: Propensity vs. Causal Uplift

$$\text{CATE } \tau(X) = \mathbb{E}[Y^{(1)} - Y^{(0)} \mid X]$$

* **Traditional Propensity Engine (v1.0):** Asks *"Will this user buy?"* $\rightarrow$ Gives discounts to 80%+ intent users who were going to buy anyway (Margin Destruction).
* **Causal Uplift Engine (v2.0):** Asks *"Will giving a discount INCREMENTALLY cause a purchase that wouldn't happen otherwise?"* $\rightarrow$ Targets only "Persuadables" to protect profit margins.

---

## The EMV Decision Gate

Interventions are triggered **only when the Expected Monetary Value is positive**:

$$\text{EMV} = \left[ P(Y^{(1)}) \times (\text{AOV} \cdot \text{Margin} - \text{Discount}) \right] - \left[ P(Y^{(0)}) \times (\text{AOV} \cdot \text{Margin}) \right]$$

If $\text{EMV} > \$0.50$, the API triggers the incentive tag; otherwise, it suppresses it.

---

## Dual-Mode Telemetry (Client & Server-Side Tracking)

To maximize data quality and bypass client-side ad-blockers, v2.0 supports two tracking architectures:
1. **Client-Side DataLayer Tracking:** Ultra-fast sub-20ms browser execution for immediate dynamic popups/modals (`GTM_INTEGRATION_V2.md`).
2. **GTM Server-Side Proxy Tracking:** Server-to-server HTTP proxying via first-party subdomains (`metrics.merchantstore.com`) for **100% ad-blocker immunity and Safari ITP compliance** (`GTM_SERVER_SIDE_INTEGRATION.md`).

---

## Repository Structure

```text
causal-ecommerce-uplift-engine/
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD pipeline to Cloud Run with Buildx caching
├── config/
│   └── settings.py             # Type-safe Pydantic environment configuration
├── models/                     # Serialized LightGBM Causal Artifacts (.joblib)
│   ├── t_learner_control.joblib
│   └── t_learner_treatment.joblib
├── notebooks/
│   └── 01_causal_t_learner_training.py # A/B dataset generation & model trainer
├── src/
│   ├── api/                    # FastAPI routes (/predict_v2) & Pydantic v2 schemas
│   ├── causal/                 # T-Learner CATE estimator & EMV Decision Gate
│   ├── features/               # Ultra-fast (<1ms) intra-session NumPy feature pipeline
│   └── telemetry/              # Non-blocking async Cloud Pub/Sub publisher
├── tests/                      # Pytest unit & integration test suite
├── ui/                         # Streamlit interactive dashboard simulator
├── Dockerfile                  # Production container recipe running as 'appuser'
├── GTM_INTEGRATION_V2.md       # Client-side browser & GTM integration guide
├── GTM_SERVER_SIDE_INTEGRATION.md # Server-side GTM container integration guide
├── pytest.ini                  # Pytest environment configuration
└── requirements.txt            # Production backend dependencies
```

---

## Technical Stack

* **Inference Pipeline:** FastAPI, LightGBM (T-Learner), NumPy (Zero-Pandas Allocation in API path).
* **Telemetry & Logging:** Asynchronous Google Cloud Pub/Sub $\rightarrow$ BigQuery Direct Subscription (`ml_logs.causal_predictions_log`).
* **Causal & ML Libraries:** Scikit-Learn, LightGBM, EconML.
* **Infrastructure:** Docker, Google Cloud Run, GitHub Actions CI/CD.

---

## Quickstart & Execution

### 1. Set Up Local Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Train & Export Causal Models
```bash
python3 notebooks/01_causal_t_learner_training.py
```

### 3. Run Automated Unit Tests
```bash
python3 -m pytest
```

### 4. Launch Local Development API
```bash
uvicorn src.api.main:app --reload --port 8000
```
*Interactive Swagger documentation live at:* `http://127.0.0.1:8000/docs`

### 5. Run Streamlit UI Dashboard Simulator
```bash
streamlit run ui/streamlit_app.py
```

---

## Production API Payload & Response Example

### POST `/predict_v2` Request Body
```json
{
  "visitor_type_encoded": 1,
  "traffic_type": 2,
  "session_duration_sec": 120.0,
  "product_views_count": 5,
  "cart_add_count": 1,
  "price_sum_viewed": 150.0,
  "time_since_last_action": 12.5,
  "tracking_mode": "server_side"
}
```

### Synchronous Response Packet (<20ms)
```json
{
  "trigger_discount": true,
  "net_emv_dollars": 2.24,
  "cate_uplift": 0.1712,
  "p_control": 0.35,
  "p_treatment": 0.5212,
  "version": "2.0.0",
  "tracking_mode": "server_side"
}
```

---

## Storefront Integration Guides
* **Client-Side Browser Integration:** Refer to `GTM_INTEGRATION_V2.md`.
* **Server-Side Container Integration (100% Ad-Blocker Immunity):** Refer to `GTM_SERVER_SIDE_INTEGRATION.md`.