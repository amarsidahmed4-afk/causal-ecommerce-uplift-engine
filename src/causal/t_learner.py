"""
T-Learner Causal Uplift Estimator.
Loads Control and Treatment models to estimate CATE, evaluate Risk-Adjusted EMV, and execute exploration policy.
"""
import os
import random
import joblib
import numpy as np
from config.settings import settings
from src.causal.emv_gate import evaluate_expected_monetary_value


class CausalTLearner:
    """
    Two-Model Causal Estimator (T-Learner).
    Model Control:   Predicts P(Y=1 | No Discount)
    Model Treatment: Predicts P(Y=1 | With Discount)
    """

    def __init__(self, control_path: str = None, treatment_path: str = None):
        self.control_path = control_path or settings.MODEL_CONTROL_PATH
        self.treatment_path = treatment_path or settings.MODEL_TREATMENT_PATH
        
        self.model_control, self.control_loaded = self._load_model_artifact(self.control_path, "Control")
        self.model_treatment, self.treatment_loaded = self._load_model_artifact(self.treatment_path, "Treatment")
        
        self.is_fallback_mode = not (self.control_loaded and self.treatment_loaded)

    def _load_model_artifact(self, filepath: str, model_name: str) -> tuple[object, bool]:
        """Loads serialized model artifact and returns status boolean."""
        if os.path.exists(filepath):
            try:
                model = joblib.load(filepath)
                print(f"✅ Loaded {model_name} Causal Model from: {filepath}")
                return model, True
            except Exception as e:
                print(f"❌ Error loading {model_name} model artifact: {e}")
                return None, False
        else:
            print(f"⚠️ {model_name} Model file not found at '{filepath}'. Fallback mode active.")
            return None, False

    def predict_uplift_and_emv(self, input_vector: np.ndarray, aov: float = None) -> dict:
        """
        Executes CATE estimation, Risk-Adjusted EMV evaluation, and exploration policy on 2D NumPy array.
        """
        if input_vector.ndim == 1:
            input_vector = input_vector.reshape(1, -1)

        # 1. Inference Execution
        if self.is_fallback_mode:
            # Fail-closed: If models are not loaded, never issue a discount.
            return {
                "p_control": 0.0,
                "p_treatment": 0.0,
                "cate_uplift": 0.0,
                "net_emv_dollars": 0.0,
                "trigger_discount": False,
                "model_source": "fallback_fail_closed",
                "is_holdout": False  # No exploration in fallback
            }

        p_control = float(self.model_control.predict_proba(input_vector)[:, 1][0])
        p_treatment = float(self.model_treatment.predict_proba(input_vector)[:, 1][0])
        model_source = "trained_artifact"

        # 2. Risk-Adjusted Financial Gate Evaluation (Unpacks 4 values)
        trigger_discount, net_emv_risk, net_emv_mean, cate_uplift = evaluate_expected_monetary_value(
            p_control=p_control,
            p_treatment=p_treatment,
            aov=aov
        )

        # 3. Exploration Policy (Epsilon-Greedy Holdout Arm for Ongoing Online CATE Re-estimation)
        is_holdout = False
        if settings.EXPLORATION_RATE > 0.0 and random.random() < settings.EXPLORATION_RATE:
            is_holdout = True
            trigger_discount = random.choice([True, False])

        return {
            "p_control": round(p_control, 4),
            "p_treatment": round(p_treatment, 4),
            "cate_uplift": round(cate_uplift, 4),
            "net_emv_dollars": round(net_emv_risk, 2), # Returns Risk-Adjusted EMV ($)
            "trigger_discount": trigger_discount,
            "model_source": model_source,
            "is_holdout": is_holdout
        }