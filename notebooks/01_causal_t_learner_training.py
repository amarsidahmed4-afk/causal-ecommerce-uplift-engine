"""
Phase 1: Causal T-Learner Training, Probability Calibration & AUUC Evaluation.
Includes Organic Buyer CATE Penalization (prevents margin cannibalization).
"""
import os
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

print("="*60)
print("! WARNING: SYNTHETIC DATA - NOT FOR PRODUCTION VALIDATION !")
print("Qini/AUUC scores here reflect the model's ability to memorize")
print("the closed -form data generator function. These metrics DO NOT")
print("represent real-world causal lift. Retrain on historical A/B")
print("holdout logs from BigQuery before going live.")
print("="*60 + "\n")


def generate_synthetic_ab_data(n_samples: int = 20000, seed: int = 42) -> pd.DataFrame:
    """Generates A/B experiment clickstream telemetry data with CATE penalization."""
    np.random.seed(seed)

    visitor_type = np.random.choice([0, 1, 2], size=n_samples, p=[0.55, 0.40, 0.05])
    traffic_type = np.random.randint(1, 21, size=n_samples)
    session_duration = np.random.exponential(scale=180.0, size=n_samples) + 10.0
    product_views = np.random.poisson(lam=4.0, size=n_samples)
    cart_adds = np.random.poisson(lam=0.8, size=n_samples)
    price_sum = product_views * np.random.uniform(20.0, 80.0, size=n_samples) + cart_adds * 50.0
    time_since_last_action = np.random.exponential(scale=20.0, size=n_samples) + 1.0

    treatment = np.random.binomial(n=1, p=0.5, size=n_samples)

    # 3. Base Conversion Propensity (Control Y0 Logits)
    # Add unobservable latent noise to break deterministic memorization
    latent_noise = np.random.normal(0, 0.5, size=n_samples)
    
    base_score = (
        -2.5
        + 0.6 * (visitor_type == 1)
        + 0.5 * np.log1p(cart_adds)
        + 0.3 * np.log1p(product_views)
        + 0.002 * price_sum
        - 0.01 * np.maximum(0, time_since_last_action - 30)
        + latent_noise
    )
    p_control_true = 1.0 / (1.0 + np.exp(-base_score))

    # 4. True Causal Treatment Effect (Uplift / CATE)
    # Persuadable users (moderate baseline + active cart) gain highest uplift
    persuadable_factor = np.exp(-((base_score - (-0.5)) ** 2) / 1.5)
    true_uplift = 0.28 * persuadable_factor * (cart_adds > 0) + 0.05 * persuadable_factor

    # -------------------------------------------------------------------------
    # 🚨 CATE PENALIZATION FOR ORGANIC BUYERS & COLD USERS
    # -------------------------------------------------------------------------
    # Organic buyers (base_score > 0.5 / high intent) buy anyway, so discount uplift is ~0%
    true_uplift = np.where(base_score > 0.5, true_uplift * 0.05, true_uplift)
    # Window shoppers with 0 cart adds have minimal uplift
    true_uplift = np.where(cart_adds == 0, true_uplift * 0.15, true_uplift)

    true_uplift = np.clip(true_uplift, 0.0, 0.35)

    p_treatment_true = np.clip(p_control_true + true_uplift, 0.0, 1.0)
    conversion_prob = np.where(treatment == 1, p_treatment_true, p_control_true)
    converted = np.random.binomial(n=1, p=conversion_prob)

    return pd.DataFrame({
        'visitor_type_encoded': visitor_type,
        'traffic_type': traffic_type,
        'session_duration_sec': session_duration,
        'product_views_count': product_views,
        'cart_add_count': cart_adds,
        'price_sum_viewed': price_sum,
        'time_since_last_action': time_since_last_action,
        'treatment': treatment,
        'converted': converted
    })


def calculate_qini_score(y_true: np.array, treatment: np.array, cate_pred: np.array) -> float:
    """Calculates Qini Curve Area for offline CATE uplift evaluation."""
    order = np.argsort(-cate_pred)
    y_true_s = y_true[order]
    t_s = treatment[order]

    n_t = np.cumsum(t_s)
    n_c = np.cumsum(1 - t_s)

    y_t = np.cumsum(y_true_s * t_s)
    y_c = np.cumsum(y_true_s * (1 - t_s))

    with np.errstate(divide='ignore', invalid='ignore'):
        qini_curve = y_t - y_c * np.where(n_c > 0, n_t / n_c, 0)

    return float(np.nanmean(qini_curve))


def train_calibrated_causal_models():
    """Trains Calibrated LightGBM models with Organic Buyer Penalization."""
    print("🎲 Step 1: Generating A/B Experiment Clickstream Telemetry Data (20,000 sessions)...")
    df = generate_synthetic_ab_data(n_samples=20000, seed=42)

    feature_cols = [
        'visitor_type_encoded', 'traffic_type', 'session_duration_sec',
        'product_views_count', 'cart_add_count', 'price_sum_viewed',
        'time_since_last_action'
    ]

    # Cast to category for LightGBM to natively recognize them
    df['visitor_type_encoded'] = df['visitor_type_encoded'].astype('category')
    df['traffic_type'] = df['traffic_type'].astype('category')

    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df['converted'])

    train_control = train_df[train_df['treatment'] == 0]
    train_treatment = train_df[train_df['treatment'] == 1]

    # Base LightGBM Estimators
    lgbm_control = LGBMClassifier(
        n_estimators=100, learning_rate=0.04, max_depth=5, 
        random_state=42, verbosity=-1
    )
    lgbm_treatment = LGBMClassifier(
        n_estimators=100, learning_rate=0.04, max_depth=5, 
        random_state=42, verbosity=-1
    )

    print("🌲 Step 2: Fitting Calibrated Control Model Y^(0) (Isotonic/Platt Scaling)...")
    model_control = CalibratedClassifierCV(estimator=lgbm_control, method='sigmoid', cv=3)
    model_control.fit(train_control[feature_cols], train_control['converted'])

    print("🌲 Step 3: Fitting Calibrated Treatment Model Y^(1) (Isotonic/Platt Scaling)...")
    model_treatment = CalibratedClassifierCV(estimator=lgbm_treatment, method='sigmoid', cv=3)
    model_treatment.fit(train_treatment[feature_cols], train_treatment['converted'])

    # Evaluation on Test Set
    X_test = test_df[feature_cols].to_numpy(dtype=np.float32)
    p_ctrl_pred = model_control.predict_proba(X_test)[:, 1]
    p_treat_pred = model_treatment.predict_proba(X_test)[:, 1]
    cate_pred = p_treat_pred - p_ctrl_pred

    qini = calculate_qini_score(
        y_true=test_df['converted'].values,
        treatment=test_df['treatment'].values,
        cate_pred=cate_pred
    )

    print("\n🎯 Calibrated Model Performance (With Organic Buyer Penalization):")
    print(f"  • Qini Uplift Score (AUUC)  : {qini:.4f}")
    print(f"  • Mean Predicted Uplift     : +{cate_pred.mean():.2%}")
    print(f"  • Max Predicted Uplift      : +{cate_pred.max():.2%}")

    # Export Artifacts
    os.makedirs('models', exist_ok=True)
    joblib.dump(model_control, 'models/t_learner_control.joblib')
    joblib.dump(model_treatment, 'models/t_learner_treatment.joblib')

    print("\n📦 Production Artifacts Exported Successfully:")
    print("  ✅ models/t_learner_control.joblib")
    print("  ✅ models/t_learner_treatment.joblib")


if __name__ == "__main__":
    train_calibrated_causal_models()