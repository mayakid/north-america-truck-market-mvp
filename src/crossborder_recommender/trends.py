"""Chart-ready historical series for the recommended Canadian markets."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import PROVINCE_BY_RAW
from .exceptions import DataUnavailableError
from .features import validate_history
from .schemas import MarketTrendSeries, TrendPoint


def market_trend_series(
    history: pd.DataFrame,
    *,
    origin_state: str,
    commodity_code: str,
    province_codes: list[str],
    months: int = 24,
) -> list[MarketTrendSeries]:
    """Return complete monthly series using the same cold-start scope as ranking."""

    if months < 1:
        raise ValueError("months must be positive")

    data = validate_history(history)
    if data.empty:
        raise DataUnavailableError("No valid normalized history is available")

    scoped = data.loc[
        (data["origin_state"] == origin_state)
        & (data["commodity_code"] == commodity_code)
    ].copy()
    source_scope = "origin_state_commodity"
    if scoped.empty:
        scoped = (
            data.loc[data["commodity_code"] == commodity_code]
            .groupby(["date", "province_code"], as_index=False, observed=True)["value"]
            .sum()
        )
        source_scope = "national_commodity_fallback"
    if scoped.empty:
        raise DataUnavailableError(
            f"No BTS history is available for commodity chapter {commodity_code}"
        )

    cutoff = data["date"].max()
    all_dates = pd.date_range(data["date"].min(), cutoff, freq="MS")
    output: list[MarketTrendSeries] = []

    for province_code in province_codes:
        province = PROVINCE_BY_RAW[province_code]
        monthly = (
            scoped.loc[scoped["province_code"] == province_code]
            .groupby("date", observed=True)["value"]
            .sum()
            .reindex(all_dates, fill_value=0.0)
            .astype(float)
        )
        rolling_3m = monthly.rolling(3, min_periods=1).sum()
        previous_year = monthly.shift(12)
        yoy = (monthly / previous_year) - 1.0
        yoy = yoy.where(previous_year > 0).replace([np.inf, -np.inf], np.nan)

        display_dates = all_dates[-months:]
        points = [
            TrendPoint(
                month=timestamp.date(),
                trade_value_usd=float(monthly.loc[timestamp]),
                rolling_3m_trade_value_usd=float(rolling_3m.loc[timestamp]),
                yoy_growth=(
                    float(yoy.loc[timestamp])
                    if pd.notna(yoy.loc[timestamp])
                    else None
                ),
            )
            for timestamp in display_dates
        ]
        output.append(
            MarketTrendSeries(
                province_code=province_code,
                province_postal_code=province.postal_code,
                province_name=province.name,
                source_scope=source_scope,
                points=points,
            )
        )
    return output
