"""TreeSHAP contribution extraction with stable human-readable feature labels."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .constants import FEATURE_LABELS
from .features import MODEL_FEATURE_COLUMNS
from .ranking import RankerBundle
from .schemas import FeatureContribution


def _shap_values(bundle: RankerBundle, matrix: pd.DataFrame) -> np.ndarray:
    try:
        import shap

        explainer = shap.TreeExplainer(bundle.model.booster_)
        values: Any = explainer.shap_values(matrix)
        if isinstance(values, list):
            values = values[0]
        array = np.asarray(values, dtype=float)
        if array.ndim == 3:
            array = array[:, :, 0]
        return array
    except Exception:
        # LightGBM's pred_contrib uses the same TreeSHAP decomposition. The final
        # column is the expected value and is excluded here.
        values = bundle.model.booster_.predict(matrix, pred_contrib=True)
        return np.asarray(values, dtype=float)[:, :-1]


def explain_candidates(
    bundle: RankerBundle,
    candidates: pd.DataFrame,
    *,
    max_features: int = 5,
) -> list[list[FeatureContribution]]:
    matrix = bundle.transform(candidates)
    shap_values = _shap_values(bundle, matrix)
    explanations: list[list[FeatureContribution]] = []
    for row_position, (_, original) in enumerate(candidates.iterrows()):
        values = shap_values[row_position]
        order = np.argsort(np.abs(values))[::-1][:max_features]
        contributions: list[FeatureContribution] = []
        for feature_index in order:
            feature = MODEL_FEATURE_COLUMNS[int(feature_index)]
            contribution = float(values[int(feature_index)])
            original_value: object = original.get(feature)
            if feature == "origin_state_code":
                original_value = original.get("origin_state")
            elif feature == "commodity_code_encoded":
                original_value = original.get("commodity_code")
            elif feature == "province_code_encoded":
                original_value = original.get("province_code")
            if isinstance(original_value, (np.floating, np.integer)):
                original_value = float(original_value)
            contributions.append(
                FeatureContribution(
                    feature=feature,
                    label=FEATURE_LABELS.get(feature, feature),
                    value=original_value,
                    contribution=contribution,
                    direction="positive" if contribution >= 0 else "negative",
                )
            )
        explanations.append(contributions)
    return explanations

