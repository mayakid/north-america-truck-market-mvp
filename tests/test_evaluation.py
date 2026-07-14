from __future__ import annotations

import warnings

from crossborder_recommender.evaluation import evaluate_ranking_frame


def test_evaluation_reports_model_baselines_and_confidence_intervals(feature_frame):
    frame = feature_frame.loc[feature_frame["date"] == feature_frame["date"].max()].copy()
    frame["opportunity_score"] = frame["opportunity_label"]

    report = evaluate_ranking_frame(frame, bootstrap_samples=50)

    assert {"model", "historical_volume_baseline", "recent_growth_baseline"}.issubset(report)
    assert report["model"]["metrics"]["ndcg@5"] == 1.0
    assert report["model"]["metrics"]["precision@5"] == 1.0
    interval = report["model"]["confidence_intervals_95"]["ndcg@5"]
    assert interval["ci_low"] <= 1.0 <= interval["ci_high"]


def test_constant_scores_have_defined_zero_spearman_without_warning(feature_frame):
    frame = feature_frame.loc[feature_frame["date"] == feature_frame["date"].max()].copy()
    frame["opportunity_score"] = 0.5

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = evaluate_ranking_frame(frame, bootstrap_samples=10)

    assert report["model"]["metrics"]["spearman"] == 0.0
