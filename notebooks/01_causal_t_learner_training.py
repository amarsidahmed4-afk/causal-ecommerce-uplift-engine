"""
Phase 1: Causal T-Learner Training & Artifact Export.
Generates an A/B experiment dataset, fits Control (Y^0) and Treatment (Y^1) LightGBM models,
evaluates CATE uplift and EMV distribution, and exports production .joblib artifacts.
"""
import os
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score


def generate_synthetic_ab_data(n_samples: int = 20000, seed: int = 42) -> pd.DataFrame:
    """
    Generates realistic A/B experiment clickstream telemetry for e-commerce causal training.
    Features:
      0: visitor_type_encoded (0: New, 1: Returning, 2: Other)
      1: traffic_type (1-20)
      2: session_duration_sec
      3: product_views_count
      4: cart_add_count
      5: price_sum_viewed
      6: time_since_last_action
    """
    np.random.seed(seed)

    # 1. Feature Distributions
    visitor_type = np.random.choice([0, 1, 2], size=n_samples, p=[0.55, 0.40, 0.05])
    traffic_type = np.random.randint(1, 21, size=n_samples)
    session_duration = np.random.exponential(scale=180.0, size=n_samples) + 10.0
    product_views = np.random.poisson(lam=4.0, size=n_samples)
    cart_adds = np.random.poisson(lam=0.8, size=n_samples)
    price_sum = product_views * np.random.uniform(20.0, 80.0, size=n_samples) + cart_adds * 50.0
    time_since_last_action = np.random.exponential(scale=20.0, size=n_samples) + 1.0

    # 2. Random A/B Treatment Assignment (50% Control [No Discount], 50% Treatment [10% Discount])
    treatment = np.random.binomial(n=1, p=0.5, size=n_samples)

    # 3. Base Conversion Propensity (Control Y0 Logits)
    base_score = (
        -2.5
        + 0.6 * (visitor_type == 1)
        + 0.5 * np.log1p(cart_adds)
        + 0.3 * np.log1p(product_views)
        + 0.002 * price_sum
        - 0.01 * np.maximum(0, time_since_last_action - 30)
    )
    p_control_true = 1.0 / (1.0 + np.exp(-base_score))

    # 4. True Causal Treatment Effect (Uplift / CATE)
    # "Persuadables" (moderate baseline, active cart) gain highest uplift from discounts
    persuadable_factor = np.exp(-((base_score - (-0.5)) ** 2) / 1.5)
    true_uplift = 0.25 * persuadable_factor * (cart_adds > 0) + 0.08 * persuadable_factor
    true_uplift = np.clip(true_uplift, 0.0, 0.40)

    p_treatment_true = np.clip(p_control_true + true_uplift, 0.0, 1.0)

    # 5. Observed Conversion Outcome Y
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


def train_and_export_causal_models():
    """Trains T-Learner Control and Treatment LightGBM models and saves .joblib artifacts."""
    print("🎲 Step 1: Generating A/B Experiment Clickstream Telemetry Data (20,000 sessions)...")
    df = generate_synthetic_ab_data(n_samples=20000, seed=42)

    feature_cols = [
        'visitor_type_encoded', 'traffic_type', 'session_duration_sec',
        'product_views_count', 'cart_add_count', 'price_sum_viewed',
        'time_since_last_action'
    ]

    # Train / Test Split
    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df['converted'])

    # Split into Control (treatment=0) and Treatment (treatment=1) subsets
    train_control = train_df[train_df['treatment'] == 0]
    train_treatment = train_df[train_df['treatment'] == 1]

    print("📊 Training Split Summary:")
    print(f"  • Control Group (No Discount) : {len(train_control)} samples (Conversion Rate: {train_control['converted'].mean():.1%})")
    print(f"  • Treatment Group (Discount)  : {len(train_treatment)} samples (Conversion Rate: {train_treatment['converted'].mean():.1%})")

    # 1. Fit Control Model Y^(0)
    print("\n🌲 Step 2: Fitting Control Model Y^(0) (Predicts Organic Conversion)...")
    model_control = LGBMClassifier(
        n_estimators=120,
        learning_rate=0.04,
        max_depth=5,
        num_leaves=25,
        random_state=42,
        verbosity=-1
    )
    model_control.fit(train_control[feature_cols], train_control['converted'])

    # 2. Fit Treatment Model Y^(1)
    print("🌲 Step 3: Fitting Treatment Model Y^(1) (Predicts Discounted Conversion)...")
    model_treatment = LGBMClassifier(
        n_estimators=120,
        learning_rate=0.04,
        max_depth=5,
        num_leaves=25,
        random_state=42,
        verbosity=-1
    )
    model_treatment.fit(train_treatment[feature_cols], train_treatment['converted'])

    # 3. Model Evaluation on Test Set
    test_control = test_df[test_df['treatment'] == 0]
    test_treatment = test_df[test_df['treatment'] == 1]

    auc_control = roc_auc_score(test_control['converted'], model_control.predict_proba(test_control[feature_cols])[:, 1])
    auc_treatment = roc_auc_score(test_treatment['converted'], model_treatment.predict_proba(test_treatment[feature_cols])[:, 1])

    print("\n🎯 Model Performance (ROC-AUC on Holdout Test Set):")
    print(f"  • Control Model ROC-AUC   : {auc_control:.4f}")
    print(f"  • Treatment Model ROC-AUC : {auc_treatment:.4f}")

    # 4. Predict CATE Uplift on Full Test Set
    X_test = test_df[feature_cols].to_numpy(dtype=np.float32)
    p_ctrl_pred = model_control.predict_proba(X_test)[:, 1]
    p_treat_pred = model_treatment.predict_proba(X_test)[:, 1]
    cate_pred = p_treat_pred - p_ctrl_pred

    print("\n💡 CATE Uplift Predictions on Holdout Test Set:")
    print(f"  • Mean Predicted Uplift   : +{cate_pred.mean():.2%}")
    print(f"  • Max Predicted Uplift    : +{cate_pred.max():.2%}")
    print(f"  • Min Predicted Uplift    : {cate_pred.min():.2%}")

    # 5. Export Production Artifacts to models/
    os.makedirs('models', exist_ok=True)

    control_path = 'models/t_learner_control.joblib'
    treatment_path = 'models/t_learner_treatment.joblib'

    joblib.dump(model_control, control_path)
    joblib.dump(model_treatment, treatment_path)

    print("\n📦 Production Artifacts Exported Successfully:")
    print(f"  ✅ {control_path}")
    print(f"  ✅ {treatment_path}")


if __name__ == "__main__":
    train_and_export_causal_models()