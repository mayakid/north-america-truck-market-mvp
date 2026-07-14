"""Leakage-safe feature and label construction for province ranking."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .constants import VALID_PROVINCE_CODES
from .exceptions import DataUnavailableError

QUERY_COLUMNS = ["date", "origin_state", "commodity_code"]
CATEGORICAL_COLUMNS = [
    "origin_state_code",
    "commodity_code_encoded",
    "province_code_encoded",
    "planning_month",
]
NUMERIC_FEATURE_COLUMNS = [
    "value_lag_1",
    "value_lag_2",
    "value_lag_3",
    "rolling_3_mean",
    "rolling_6_mean",
    "rolling_12_mean",
    "rolling_3_growth",
    "recent_yoy_growth",
    "rolling_6_volatility",
    "nonzero_ratio_12",
    "route_share_12",
    "commodity_province_share_12",
    "state_province_share_12",
    "seasonality_index",
]
MODEL_FEATURE_COLUMNS = CATEGORICAL_COLUMNS + NUMERIC_FEATURE_COLUMNS


def validate_history(history: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "origin_state", "commodity_code", "province_code", "value"}
    missing = required.difference(history.columns)
    if missing:
        raise DataUnavailableError(f"Normalized history is missing columns: {sorted(missing)}")
    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.to_period("M").dt.to_timestamp()
    frame["value"] = (
        pd.to_numeric(frame["value"], errors="coerce")
        .fillna(0.0)
        .clip(lower=0)
        .astype("float64")
    )
    frame["origin_state"] = frame["origin_state"].astype(str).str.upper()
    frame["commodity_code"] = frame["commodity_code"].astype(str).str.zfill(2)
    frame["province_code"] = frame["province_code"].astype(str).str.upper()
    frame = frame.loc[frame["province_code"].isin(VALID_PROVINCE_CODES)]
    return (
        frame.groupby(
            ["date", "origin_state", "commodity_code", "province_code"],
            as_index=False,
            observed=True,
        )["value"]
        .sum()
        .sort_values(["origin_state", "commodity_code", "province_code", "date"])
        .reset_index(drop=True)
    )


def _safe_log_growth(current: pd.Series, previous: pd.Series) -> pd.Series:
    return np.log1p(current.clip(lower=0)) - np.log1p(previous.clip(lower=0))


def _route_group_features(group: pd.DataFrame, all_dates: pd.DatetimeIndex) -> pd.DataFrame:
    state = str(group["origin_state"].iloc[0])
    commodity = str(group["commodity_code"].iloc[0])
    index = pd.MultiIndex.from_product(
        [all_dates, VALID_PROVINCE_CODES], names=["date", "province_code"]
    )
    values = (
        group.set_index(["date", "province_code"])["value"]
        .groupby(level=[0, 1])
        .sum()
        .reindex(index, fill_value=0.0)
        .rename("value")
        .reset_index()
    )
    values["origin_state"] = state
    values["commodity_code"] = commodity
    values["planning_month"] = values["date"].dt.month.astype("int8")

    by_province = values.groupby("province_code", observed=True)["value"]
    for lag in (1, 2, 3, 4, 5, 6, 12, 13):
        values[f"value_lag_{lag}"] = by_province.shift(lag)
    for window in (3, 6, 12):
        values[f"rolling_{window}_mean"] = by_province.transform(
            lambda series, size=window: series.shift(1).rolling(size, min_periods=1).mean()
        )
    values["rolling_6_std"] = by_province.transform(
        lambda series: series.shift(1).rolling(6, min_periods=2).std()
    )
    values["nonzero_ratio_12"] = by_province.transform(
        lambda series: series.shift(1).gt(0).rolling(12, min_periods=1).mean()
    )
    prior_3_mean = values[["value_lag_4", "value_lag_5", "value_lag_6"]].mean(axis=1)
    values["rolling_3_growth"] = _safe_log_growth(values["rolling_3_mean"], prior_3_mean)
    values["recent_yoy_growth"] = _safe_log_growth(
        values["value_lag_1"], values["value_lag_13"]
    )
    values["rolling_6_volatility"] = (
        values["rolling_6_std"] / values["rolling_6_mean"].replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)

    values["route_value_12"] = values["rolling_12_mean"] * 12.0
    query_total_12 = values.groupby("date", observed=True)["route_value_12"].transform("sum")
    values["route_share_12"] = values["route_value_12"] / query_total_12.replace(0, np.nan)

    same_month_mean = values.groupby(
        ["province_code", "planning_month"], observed=True
    )["value"].transform(lambda series: series.shift(1).expanding(min_periods=1).mean())
    values["seasonality_index"] = (
        same_month_mean / values["rolling_12_mean"].replace(0, np.nan)
    ).clip(lower=0, upper=5)
    values["label_yoy_growth"] = _safe_log_growth(values["value"], values["value_lag_12"])
    values["query_history_value_12"] = query_total_12
    values["target_total_value"] = values.groupby("date", observed=True)["value"].transform("sum")
    return values


def _aggregate_share(
    history: pd.DataFrame,
    primary_column: str,
    output_column: str,
    all_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    grouped = history.groupby(
        ["date", primary_column, "province_code"], as_index=False, observed=True
    )["value"].sum()
    combinations = grouped[[primary_column, "province_code"]].drop_duplicates()
    pieces: list[pd.DataFrame] = []
    for row in combinations.itertuples(index=False, name=None):
        primary, province = row
        series = grouped.loc[
            (grouped[primary_column] == primary) & (grouped["province_code"] == province),
            ["date", "value"],
        ].set_index("date")["value"]
        complete = series.reindex(all_dates, fill_value=0.0)
        trailing = complete.shift(1).rolling(12, min_periods=1).sum()
        pieces.append(
            pd.DataFrame(
                {
                    "date": all_dates,
                    primary_column: primary,
                    "province_code": province,
                    "trailing_value": trailing.to_numpy(),
                }
            )
        )
    result = pd.concat(pieces, ignore_index=True)
    denominator = result.groupby(["date", primary_column], observed=True)[
        "trailing_value"
    ].transform("sum")
    result[output_column] = result["trailing_value"] / denominator.replace(0, np.nan)
    return result[["date", primary_column, "province_code", output_column]]


def build_training_frame(history: pd.DataFrame, min_history_months: int = 12) -> pd.DataFrame:
    """Build one row per query/province with strictly prior-month features.

    The continuous opportunity label is exactly:
        0.60 * within-query size percentile
      + 0.40 * within-query YoY-growth percentile

    LightGBM LambdaRank consumes a 0..4 integer relevance grade derived from that
    continuous label; the continuous score remains available for calibration/evaluation.
    """

    data = validate_history(history)
    if data.empty:
        raise DataUnavailableError("No valid Canada truck-export records are available")
    start = data["date"].min()
    cutoff = data["date"].max()
    all_dates = pd.date_range(start, cutoff, freq="MS")

    pieces: list[pd.DataFrame] = []
    for _, group in data.groupby(["origin_state", "commodity_code"], observed=True):
        pieces.append(_route_group_features(group, all_dates))
    frame = pd.concat(pieces, ignore_index=True)

    commodity_share = _aggregate_share(
        data, "commodity_code", "commodity_province_share_12", all_dates
    )
    state_share = _aggregate_share(data, "origin_state", "state_province_share_12", all_dates)
    frame = frame.merge(
        commodity_share,
        on=["date", "commodity_code", "province_code"],
        how="left",
        validate="many_to_one",
    ).merge(
        state_share,
        on=["date", "origin_state", "province_code"],
        how="left",
        validate="many_to_one",
    )

    minimum_date = start + pd.offsets.MonthBegin(min_history_months)
    frame = frame.loc[
        (frame["date"] >= minimum_date)
        & (frame["query_history_value_12"] > 0)
        & (frame["target_total_value"] > 0)
    ].copy()

    grouped_query = frame.groupby(QUERY_COLUMNS, sort=False, observed=True)
    frame["size_percentile"] = grouped_query["value"].rank(method="average", pct=True)
    frame["growth_percentile"] = grouped_query["label_yoy_growth"].rank(
        method="average", pct=True
    )
    frame["opportunity_label"] = (
        0.60 * frame["size_percentile"] + 0.40 * frame["growth_percentile"]
    )
    frame["relevance"] = np.floor(frame["opportunity_label"] * 5).clip(0, 4).astype("int8")
    frame["latest_3m_trade_value_usd"] = frame["rolling_3_mean"] * 3.0
    frame["latest_12m_trade_value_usd"] = frame["rolling_12_mean"] * 12.0
    return _finalize_features(frame)


def _finalize_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["origin_state_code"] = result["origin_state"]
    result["commodity_code_encoded"] = result["commodity_code"]
    result["province_code_encoded"] = result["province_code"]
    fill_zero = [column for column in NUMERIC_FEATURE_COLUMNS if column != "seasonality_index"]
    result[fill_zero] = result[fill_zero].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    result["seasonality_index"] = (
        result["seasonality_index"].replace([np.inf, -np.inf], np.nan).fillna(1.0)
    )
    return result


def _series_metrics(series: pd.Series) -> dict[str, float]:
    values = series.astype(float)
    lags = values.iloc[::-1].to_list()

    def lag(number: int) -> float:
        return float(lags[number - 1]) if len(lags) >= number else 0.0

    last3 = values.tail(3)
    last6 = values.tail(6)
    last12 = values.tail(12)
    previous3 = values.iloc[-6:-3]
    rolling_3_mean = float(last3.mean()) if not last3.empty else 0.0
    rolling_6_mean = float(last6.mean()) if not last6.empty else 0.0
    rolling_12_mean = float(last12.mean()) if not last12.empty else 0.0
    prior3_mean = float(previous3.mean()) if not previous3.empty else 0.0
    volatility = (
        float(last6.std(ddof=1) / rolling_6_mean)
        if len(last6) >= 2 and rolling_6_mean > 0
        else 0.0
    )
    return {
        "value_lag_1": lag(1),
        "value_lag_2": lag(2),
        "value_lag_3": lag(3),
        "rolling_3_mean": rolling_3_mean,
        "rolling_6_mean": rolling_6_mean,
        "rolling_12_mean": rolling_12_mean,
        "rolling_3_growth": float(np.log1p(rolling_3_mean) - np.log1p(prior3_mean)),
        "recent_yoy_growth": float(np.log1p(lag(1)) - np.log1p(lag(13))),
        "rolling_6_volatility": volatility,
        "nonzero_ratio_12": float(last12.gt(0).mean()) if not last12.empty else 0.0,
        "latest_3m_trade_value_usd": float(last3.sum()),
        "latest_12m_trade_value_usd": float(last12.sum()),
        "history_nonzero_months": int(values.gt(0).sum()),
    }


def build_inference_candidates(
    history: pd.DataFrame,
    origin_state: str,
    commodity_code: str,
    planning_month: int,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Build current as-of features for all 13 province/territory candidates."""

    data = validate_history(history)
    if data.empty:
        raise DataUnavailableError("No valid normalized history is available")
    cutoff = data["date"].max()
    dates = pd.date_range(data["date"].min(), cutoff, freq="MS")
    scoped = data.loc[
        (data["origin_state"] == origin_state) & (data["commodity_code"] == commodity_code)
    ]
    if scoped.empty:
        # Cold-start fallback: use nationwide commodity history while retaining the requested state.
        scoped = (
            data.loc[data["commodity_code"] == commodity_code]
            .groupby(["date", "commodity_code", "province_code"], as_index=False, observed=True)[
                "value"
            ]
            .sum()
        )
        scoped["origin_state"] = origin_state
    if scoped.empty:
        raise DataUnavailableError(
            f"No BTS history is available for commodity chapter {commodity_code}"
        )

    rows: list[dict[str, object]] = []
    for province in VALID_PROVINCE_CODES:
        series = (
            scoped.loc[scoped["province_code"] == province]
            .groupby("date", observed=True)["value"]
            .sum()
            .reindex(dates, fill_value=0.0)
        )
        metrics = _series_metrics(series)
        seasonal_values = series.loc[series.index.month == planning_month]
        seasonal_mean = float(seasonal_values.mean()) if not seasonal_values.empty else 0.0
        baseline = float(metrics["rolling_12_mean"])
        seasonality = seasonal_mean / baseline if baseline > 0 else 1.0
        rows.append(
            {
                "date": cutoff + pd.offsets.MonthBegin(1),
                "origin_state": origin_state,
                "commodity_code": commodity_code,
                "province_code": province,
                "planning_month": planning_month,
                "seasonality_index": float(np.clip(seasonality, 0, 5)),
                **metrics,
            }
        )
    candidates = pd.DataFrame(rows)

    route_total = candidates["latest_12m_trade_value_usd"].sum()
    candidates["route_share_12"] = (
        candidates["latest_12m_trade_value_usd"] / route_total if route_total > 0 else 0.0
    )
    last_12_start = cutoff - pd.offsets.MonthBegin(11)
    recent = data.loc[data["date"].between(last_12_start, cutoff)]

    commodity_values = (
        recent.loc[recent["commodity_code"] == commodity_code]
        .groupby("province_code", observed=True)["value"]
        .sum()
    )
    commodity_total = float(commodity_values.sum())
    candidates["commodity_province_share_12"] = candidates["province_code"].map(
        lambda code: float(commodity_values.get(code, 0.0) / commodity_total)
        if commodity_total > 0
        else 0.0
    )

    state_values = (
        recent.loc[recent["origin_state"] == origin_state]
        .groupby("province_code", observed=True)["value"]
        .sum()
    )
    state_total = float(state_values.sum())
    candidates["state_province_share_12"] = candidates["province_code"].map(
        lambda code: float(state_values.get(code, 0.0) / state_total) if state_total > 0 else 0.0
    )
    return _finalize_features(candidates), cutoff


def group_sizes(frame: pd.DataFrame, query_columns: Iterable[str] = QUERY_COLUMNS) -> list[int]:
    """Return contiguous LambdaRank group sizes after stable query sorting."""

    return (
        frame.groupby(list(query_columns), sort=False, observed=True)
        .size()
        .astype(int)
        .to_list()
    )
