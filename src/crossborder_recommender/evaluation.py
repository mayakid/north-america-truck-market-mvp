"""Held-out ranking evaluation with query-level bootstrap confidence intervals."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, ndcg_score

from .features import QUERY_COLUMNS


def _average_precision_at_k(predicted: list[str], relevant: set[str], k: int) -> float:
    hits = 0
    total = 0.0
    for rank, item in enumerate(predicted[:k], start=1):
        if item in relevant:
            hits += 1
            total += hits / rank
    return total / min(len(relevant), k) if relevant else 0.0


def _query_metrics(group: pd.DataFrame, score_column: str, k: int = 5) -> dict[str, float]:
    ordered_true = group.sort_values(
        ["opportunity_label", "province_code"], ascending=[False, True]
    )
    ordered_predicted = group.sort_values(
        [score_column, "province_code"], ascending=[False, True]
    )
    effective_k = min(k, len(group))
    true_top = ordered_true.head(effective_k)["province_code"].astype(str).to_list()
    predicted_top = (
        ordered_predicted.head(effective_k)["province_code"].astype(str).to_list()
    )
    relevant = set(true_top)
    hits = len(relevant.intersection(predicted_top))
    precision = hits / effective_k if effective_k else 0.0
    recall = hits / len(relevant) if relevant else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    truth = group["opportunity_label"].to_numpy(dtype=float)
    predicted = group[score_column].to_numpy(dtype=float)
    if (
        truth.size < 2
        or np.ptp(truth) == 0
        or np.ptp(predicted) == 0
    ):
        correlation = 0.0
    else:
        correlation = float(spearmanr(truth, predicted).statistic)
    return {
        "ndcg@1": float(ndcg_score(truth[None, :], predicted[None, :], k=1)),
        "ndcg@3": float(ndcg_score(truth[None, :], predicted[None, :], k=min(3, len(group)))),
        "ndcg@5": float(ndcg_score(truth[None, :], predicted[None, :], k=effective_k)),
        "precision@5": precision,
        "recall@5": recall,
        "f1@5": f1,
        "map@5": _average_precision_at_k(predicted_top, relevant, effective_k),
        "top1_accuracy": float(predicted_top[0] == true_top[0]),
        "spearman": correlation if np.isfinite(correlation) else 0.0,
    }


def _bootstrap_mean_ci(
    values: np.ndarray,
    *,
    confidence: float = 0.95,
    samples: int = 1000,
    random_state: int = 42,
) -> dict[str, float]:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = np.random.default_rng(random_state)
    indices = rng.integers(0, clean.size, size=(samples, clean.size))
    bootstrap = clean[indices].mean(axis=1)
    alpha = (1 - confidence) / 2
    return {
        "mean": float(clean.mean()),
        "ci_low": float(np.quantile(bootstrap, alpha)),
        "ci_high": float(np.quantile(bootstrap, 1 - alpha)),
    }


def _evaluate_score(
    frame: pd.DataFrame,
    score_column: str,
    *,
    bootstrap_samples: int,
) -> dict[str, Any]:
    query_rows: list[dict[str, float]] = []
    selected: set[str] = set()
    for _, group in frame.groupby(QUERY_COLUMNS, sort=False, observed=True):
        query_rows.append(_query_metrics(group, score_column))
        selected.update(
            group.nlargest(min(5, len(group)), score_column)["province_code"].astype(str)
        )
    per_query = pd.DataFrame(query_rows)
    intervals = {
        metric: _bootstrap_mean_ci(
            per_query[metric].to_numpy(), samples=bootstrap_samples, random_state=42
        )
        for metric in per_query.columns
    }
    return {
        "queries": len(per_query),
        "metrics": {metric: values["mean"] for metric, values in intervals.items()},
        "confidence_intervals_95": intervals,
        "province_coverage@5": len(selected) / frame["province_code"].nunique(),
    }


def evaluate_ranking_frame(
    test_scored: pd.DataFrame,
    *,
    bootstrap_samples: int = 1000,
) -> dict[str, Any]:
    """Evaluate the model once on the held-out chronological test partition."""

    required = {
        *QUERY_COLUMNS,
        "province_code",
        "opportunity_label",
        "opportunity_score",
        "rolling_12_mean",
        "recent_yoy_growth",
    }
    missing = required.difference(test_scored.columns)
    if missing:
        raise ValueError(f"Evaluation frame is missing columns: {sorted(missing)}")
    frame = test_scored.copy()
    report: dict[str, Any] = {
        "definition": {
            "relevant_market": "ground-truth top 5 by the confirmed composite opportunity label",
            "query_group": "target month + origin state + HS2 commodity",
            "split": "chronological held-out test months",
        }
    }
    report["model"] = _evaluate_score(
        frame, "opportunity_score", bootstrap_samples=bootstrap_samples
    )
    report["historical_volume_baseline"] = _evaluate_score(
        frame, "rolling_12_mean", bootstrap_samples=bootstrap_samples
    )
    report["recent_growth_baseline"] = _evaluate_score(
        frame, "recent_yoy_growth", bootstrap_samples=bootstrap_samples
    )
    report["model"]["calibration_mae"] = float(
        mean_absolute_error(frame["opportunity_label"], frame["opportunity_score"])
    )
    report["model"]["calibration_rmse"] = float(
        mean_squared_error(
            frame["opportunity_label"], frame["opportunity_score"]
        )
        ** 0.5
    )
    return report


def flatten_metrics(report: dict[str, Any], models: Iterable[str] = ("model",)) -> dict[str, float]:
    flattened: dict[str, float] = {}
    for model_name in models:
        section = report.get(model_name, {})
        for metric, value in section.get("metrics", {}).items():
            flattened[f"{model_name}.{metric}"] = float(value)
        for metric in ("province_coverage@5", "calibration_mae", "calibration_rmse"):
            if metric in section:
                flattened[f"{model_name}.{metric}"] = float(section[metric])
    return flattened
