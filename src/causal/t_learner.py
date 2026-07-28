"""
T-Learner Causal Uplift Estimator.
Loads Control and Treatment models to estimate CATE and evaluate EMV.
"""
import os
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
        
        self.model_control = self._load_model_artifact(self.control_path, "Control")
        self.model_treatment = self._load_model_artifact(self.treatment_path, "Treatment")

    def _load_model_artifact(self, filepath: str, model_name: str):
        """Loads serialized model artifact or returns None for mock execution."""
        if os.path.exists(filepath):
            print(f"✅ Loaded {model_name} Causal Model from: {filepath}")
            return joblib.load(filepath)
        else:
            print(f"⚠️ {model_name} Model file not found at '{filepath}'. Using baseline fallback mode.")
            return None

    def predict_uplift_and_emv(self, input_vector: np.ndarray, aov: float = None) -> dict:
        """
        Executes CATE estimation and EMV calculation on a 2D NumPy array.

        Args:
            input_vector: 2D NumPy array shape (1, n_features)
            aov: Optional custom Average Order Value for this user's cart

        Returns:
            dict containing p_control, p_treatment, cate_uplift, net_emv, trigger_discount
        """
        if input_vector.ndim == 1:
            input_vector = input_vector.reshape(1, -1)

        # 1. Inference Execution (Uses real models if loaded, or fallback heuristic for dev/testing)
        if self.model_control and self.model_treatment:
            p_control = float(self.model_control.predict_proba(input_vector)[:, 1][0])
            p_treatment = float(self.model_treatment.predict_proba(input_vector)[:, 1][0])
        else:
            # Fallback heuristic for testing before models are trained
            p_control = 0.35
            p_treatment = 0.52

        # 2. Financial Gate Evaluation
        trigger_discount, net_emv, cate_uplift = evaluate_expected_monetary_value(
            p_control=p_control,
            p_treatment=p_treatment,
            aov=aov
        )

        return {
            "p_control": round(p_control, 4),
            "p_treatment": round(p_treatment, 4),
            "cate_uplift": round(cate_uplift, 4),
            "net_emv_dollars": round(net_emv, 2),
            "trigger_discount": trigger_discount
        }