from __future__ import annotations

import numpy as np
import pytest

from crossborder_recommender.constants import VALID_PROVINCE_CODES
from crossborder_recommender.exceptions import ModelUnavailableError
from crossborder_recommender.explainability import explain_candidates
from crossborder_recommender.ranking import RankerBundle, temporal_split


def test_ranker_scores_all_candidates_and_returns_stable_top5(trained_bundle):
    ranked, method = trained_bundle.rank("MI", "87", 10)

    assert method == "lightgbm_lambdarank"
    assert len(ranked) == len(VALID_PROVINCE_CODES) == 13
    assert ranked["province_code"].nunique() == 13
    assert ranked["rank"].tolist() == list(range(1, 14))
    assert np.isfinite(ranked["raw_ranker_score"]).all()
    assert ranked["opportunity_score"].between(0, 1).all()
    assert ranked["raw_ranker_score"].is_monotonic_decreasing
    gate = trained_bundle.metadata["acceptance_gate"]
    assert gate["metric"] == "ndcg@5"
    assert gate["passed"] == (gate["model_value"] > gate["baseline_value"])


def test_bundle_round_trip_and_tree_shap(tmp_path, trained_bundle):
    artifact = tmp_path / "ranker.joblib"
    trained_bundle.save(artifact)
    restored = RankerBundle.load(artifact)
    ranked, _ = restored.rank("MI", "87", 10)

    explanations = explain_candidates(restored, ranked.head(5), max_features=4)

    assert len(explanations) == 5
    assert all(1 <= len(items) <= 4 for items in explanations)
    assert all(np.isfinite(item.contribution) for items in explanations for item in items)


def test_temporal_split_never_silently_shrinks_confirmed_windows(feature_frame):
    months = sorted(feature_frame["date"].unique())[:10]
    short = feature_frame.loc[feature_frame["date"].isin(months)]

    with pytest.raises(ModelUnavailableError, match="2 training, 6 validation, and 12 test"):
        temporal_split(short, validation_months=6, test_months=12)
