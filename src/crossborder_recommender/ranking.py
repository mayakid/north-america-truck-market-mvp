"""LightGBM LambdaRank training, persistence, inference, and cold-start fallback."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.isotonic import IsotonicRegression
from sklearn.preprocessing import OrdinalEncoder

from .exceptions import ModelUnavailableError
from .features import (
    CATEGORICAL_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    QUERY_COLUMNS,
    build_inference_candidates,
    group_sizes,
)

ARTIFACT_VERSION = "1.0"


@dataclass
class RankerBundle:
    model: Any
    encoder: OrdinalEncoder
    calibrator: IsotonicRegression | None
    history: pd.DataFrame
    data_cutoff: pd.Timestamp
    port_history: pd.DataFrame | None = None
    feature_columns: list[str] = field(default_factory=lambda: list(MODEL_FEATURE_COLUMNS))
    categorical_columns: list[str] = field(default_factory=lambda: list(CATEGORICAL_COLUMNS))
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    artifact_version: str = ARTIFACT_VERSION

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        joblib.dump(self, temporary, compress=3)
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> RankerBundle:
        if not path.exists():
            raise ModelUnavailableError(f"Ranker artifact does not exist: {path}")
        bundle = joblib.load(path)
        if not isinstance(bundle, cls):
            raise ModelUnavailableError(f"Unexpected artifact type in {path}")
        if bundle.artifact_version != ARTIFACT_VERSION:
            raise ModelUnavailableError(
                f"Artifact version {bundle.artifact_version} is incompatible with "
                f"{ARTIFACT_VERSION}"
            )
        return bundle

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        missing = set(self.feature_columns).difference(frame.columns)
        if missing:
            raise ModelUnavailableError(f"Inference frame is missing features: {sorted(missing)}")
        matrix = frame[self.feature_columns].copy()
        matrix[self.categorical_columns] = self.encoder.transform(
            matrix[self.categorical_columns].astype(str)
        ).astype("int32")
        matrix[NUMERIC_FEATURE_COLUMNS] = (
            matrix[NUMERIC_FEATURE_COLUMNS]
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
        )
        return matrix

    def score(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        matrix = self.transform(frame)
        raw = np.asarray(self.model.predict(matrix), dtype=float)
        if self.calibrator is not None:
            calibrated = np.asarray(self.calibrator.predict(raw), dtype=float)
        else:
            calibrated = expit(raw)
        return raw, np.clip(calibrated, 0.0, 1.0)

    def rank(
        self,
        origin_state: str,
        commodity_code: str,
        planning_month: int,
    ) -> tuple[pd.DataFrame, str]:
        candidates, _ = build_inference_candidates(
            self.history, origin_state, commodity_code, planning_month
        )
        try:
            raw, calibrated = self.score(candidates)
            candidates["raw_ranker_score"] = raw
            candidates["opportunity_score"] = calibrated
            method = "lightgbm_lambdarank"
        except Exception as exc:
            # Model runtime failures degrade explicitly and remain visible in metadata.
            fallback = _fallback_score(candidates)
            candidates["raw_ranker_score"] = fallback
            candidates["opportunity_score"] = fallback
            candidates["fallback_reason"] = str(exc)
            method = "transparent_market_signal_fallback"
        candidates["cold_start"] = candidates["history_nonzero_months"] < 12
        # Isotonic calibration can legitimately map several raw scores to the
        # same probability.  Preserve the ranker's ordering in those plateaus;
        # the calibrated value is for interpretation, not re-ranking.
        candidates = candidates.sort_values(
            ["raw_ranker_score", "latest_12m_trade_value_usd", "province_code"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        candidates["rank"] = np.arange(1, len(candidates) + 1)
        return candidates, method


def _fallback_score(frame: pd.DataFrame) -> np.ndarray:
    growth = frame["recent_yoy_growth"].rank(method="average", pct=True).to_numpy()
    size = frame["latest_12m_trade_value_usd"].rank(method="average", pct=True).to_numpy()
    return np.clip(0.60 * size + 0.40 * growth, 0.0, 1.0)


def _prepare_matrix(
    frame: pd.DataFrame,
    encoder: OrdinalEncoder | None = None,
) -> tuple[pd.DataFrame, OrdinalEncoder]:
    matrix = frame[MODEL_FEATURE_COLUMNS].copy()
    if encoder is None:
        encoder = OrdinalEncoder(
            handle_unknown="use_encoded_value",
            unknown_value=-1,
            encoded_missing_value=-1,
            dtype=np.int32,
        )
        encoded = encoder.fit_transform(matrix[CATEGORICAL_COLUMNS].astype(str))
    else:
        encoded = encoder.transform(matrix[CATEGORICAL_COLUMNS].astype(str))
    matrix[CATEGORICAL_COLUMNS] = encoded.astype("int32")
    matrix[NUMERIC_FEATURE_COLUMNS] = (
        matrix[NUMERIC_FEATURE_COLUMNS]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    return matrix, encoder


def temporal_split(
    frame: pd.DataFrame,
    validation_months: int = 6,
    test_months: int = 12,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    months = pd.DatetimeIndex(sorted(pd.to_datetime(frame["date"]).unique()))
    required = validation_months + test_months + 2
    if len(months) < required:
        raise ModelUnavailableError(
            f"At least {required} eligible target months are required: 2 training, "
            f"{validation_months} validation, and {test_months} test months; got {len(months)}"
        )
    validation_start = months[-(test_months + validation_months)]
    test_start = months[-test_months]

    train = frame.loc[frame["date"] < validation_start].copy()
    validation = frame.loc[
        (frame["date"] >= validation_start) & (frame["date"] < test_start)
    ].copy()
    test = frame.loc[frame["date"] >= test_start].copy()
    if train.empty or validation.empty or test.empty:
        raise ModelUnavailableError("Temporal split produced an empty partition")
    ranges = {
        "train": f"{train['date'].min():%Y-%m}..{train['date'].max():%Y-%m}",
        "validation": f"{validation['date'].min():%Y-%m}..{validation['date'].max():%Y-%m}",
        "test": f"{test['date'].min():%Y-%m}..{test['date'].max():%Y-%m}",
    }
    return train, validation, test, ranges


def _sort_queries(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(
        QUERY_COLUMNS + ["province_code"], kind="stable"
    ).reset_index(drop=True)


def train_ranker(
    feature_frame: pd.DataFrame,
    history: pd.DataFrame,
    *,
    port_history: pd.DataFrame | None = None,
    validation_months: int = 6,
    test_months: int = 12,
    synthetic_data: bool = False,
    random_state: int = 42,
) -> tuple[RankerBundle, pd.DataFrame]:
    """Train LambdaRank with chronological validation/test partitions."""

    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ModelUnavailableError("lightgbm is not installed") from exc

    train, validation, test, ranges = temporal_split(
        feature_frame, validation_months=validation_months, test_months=test_months
    )
    train = _sort_queries(train)
    validation = _sort_queries(validation)
    test = _sort_queries(test)

    x_train, encoder = _prepare_matrix(train)
    x_validation, _ = _prepare_matrix(validation, encoder)
    x_test, _ = _prepare_matrix(test, encoder)

    model = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        boosting_type="gbdt",
        n_estimators=600,
        learning_rate=0.04,
        num_leaves=31,
        max_depth=-1,
        min_child_samples=30,
        subsample=0.90,
        colsample_bytree=0.90,
        reg_alpha=0.05,
        reg_lambda=0.10,
        random_state=random_state,
        n_jobs=-1,
        verbosity=-1,
        label_gain=[0, 1, 3, 7, 15],
    )
    model.fit(
        x_train,
        train["relevance"].astype(int),
        group=group_sizes(train),
        eval_set=[(x_validation, validation["relevance"].astype(int))],
        eval_group=[group_sizes(validation)],
        eval_at=[1, 3, 5],
        categorical_feature=CATEGORICAL_COLUMNS,
        callbacks=[lgb.early_stopping(60, verbose=False)],
    )

    validation_raw = np.asarray(model.predict(x_validation), dtype=float)
    calibrator: IsotonicRegression | None = None
    if np.unique(validation_raw).size >= 2:
        calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        calibrator.fit(validation_raw, validation["opportunity_label"].to_numpy(dtype=float))

    test_raw = np.asarray(model.predict(x_test), dtype=float)
    test_scored = test.copy()
    test_scored["raw_ranker_score"] = test_raw
    test_scored["opportunity_score"] = (
        calibrator.predict(test_raw) if calibrator is not None else expit(test_raw)
    )

    cutoff = pd.to_datetime(history["date"]).max()
    bundle = RankerBundle(
        model=model,
        encoder=encoder,
        calibrator=calibrator,
        history=history.copy(),
        data_cutoff=cutoff,
        port_history=None if port_history is None else port_history.copy(),
        metadata={
            "trained_at_utc": datetime.now(UTC).isoformat(),
            "split_ranges": ranges,
            "label_formula": "0.60 * size_percentile + 0.40 * yoy_growth_percentile",
            "relevance_grades": "floor(opportunity_label * 5), clipped to 0..4",
            "synthetic_data": synthetic_data,
            "python_version": platform.python_version(),
            "lightgbm_version": lgb.__version__,
            "best_iteration": model.best_iteration_,
            "training_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
        },
    )
    from .evaluation import evaluate_ranking_frame, flatten_metrics

    evaluation_report = evaluate_ranking_frame(test_scored)
    bundle.metrics = flatten_metrics(evaluation_report)
    bundle.metadata["evaluation"] = evaluation_report
    model_ndcg5 = float(evaluation_report["model"]["metrics"]["ndcg@5"])
    baseline_ndcg5 = float(
        evaluation_report["historical_volume_baseline"]["metrics"]["ndcg@5"]
    )
    bundle.metadata["acceptance_gate"] = {
        "metric": "ndcg@5",
        "rule": "model must exceed historical-volume baseline on the held-out test period",
        "model_value": model_ndcg5,
        "baseline_value": baseline_ndcg5,
        "passed": model_ndcg5 > baseline_ndcg5,
    }
    return bundle, test_scored
