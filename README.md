# Causal Ecommerce Uplift Engine v2.0

An enterprise-grade, low-latency microservice designed to maximize e-commerce gross margins using **Causal Inference (CATE Estimation)** and **Expected Monetary Value (EMV) Decision Gating**.

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

## Technical Stack

* **Inference Pipeline:** FastAPI, LightGBM (T-Learner), NumPy (Zero-Pandas Allocation in API path).
* **Telemetry & Logging:** Asynchronous Google Cloud Pub/Sub $\rightarrow$ BigQuery Direct Subscription (0% data loss).
* **Causal Libraries:** EconML / Scikit-Learn.
* **Infrastructure:** Docker, Google Cloud Run, GitHub Actions CI/CD.

---

## Quickstart

### 1. Set Up Local Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Local Development API
```bash
uvicorn src.api.main:app --reload --port 8000
```