from __future__ import annotations

import numpy as np
import pandas as pd

from crossborder_recommender.constants import VALID_PROVINCE_CODES
from crossborder_recommender.features import (
    MODEL_FEATURE_COLUMNS,
    build_training_frame,
    validate_history,
)


def test_every_query_has_all_13_province_candidates(feature_frame):
    sizes = feature_frame.groupby(
        ["date", "origin_state", "commodity_code"], observed=True
    ).size()
    assert sizes.nunique() == 1
    assert sizes.iloc[0] == len(VALID_PROVINCE_CODES) == 13


def test_confirmed_composite_label_is_exact(feature_frame):
    expected = 0.60 * feature_frame["size_percentile"] + 0.40 * feature_frame[
        "growth_percentile"
    ]
    np.testing.assert_allclose(feature_frame["opportunity_label"], expected)


def test_nullable_integer_trade_values_are_normalized_to_numpy_float(synthetic_history):
    nullable = synthetic_history.copy()
    nullable["value"] = nullable["value"].round().astype("Int64")

    validated = validate_history(nullable)

    assert validated["value"].dtype == np.dtype("float64")


def test_future_values_do_not_change_prior_features(synthetic_history):
    cutoff = pd.Timestamp("2023-06-01")
    changed = synthetic_history.copy()
    changed.loc[changed["date"] >= cutoff, "value"] *= 1000

    original_features = build_training_frame(synthetic_history)
    changed_features = build_training_frame(changed)
    keys = ["date", "origin_state", "commodity_code", "province_code"]
    columns = keys + MODEL_FEATURE_COLUMNS
    left = original_features.loc[original_features["date"] < cutoff, columns].sort_values(keys)
    right = changed_features.loc[changed_features["date"] < cutoff, columns].sort_values(keys)

    pd.testing.assert_frame_equal(left.reset_index(drop=True), right.reset_index(drop=True))
