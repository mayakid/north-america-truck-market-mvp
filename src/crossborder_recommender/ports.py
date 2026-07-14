"""Independent BTS Table 1 port summaries (never commodity-joint estimates)."""

from __future__ import annotations

import pandas as pd

from .schemas import PortStatistic


def port_statistics(
    history: pd.DataFrame | None,
    *,
    origin_state: str,
    province_codes: list[str],
    preferred_port: str | None = None,
    limit: int = 5,
) -> list[PortStatistic]:
    if history is None or history.empty:
        return []
    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.to_period("M").dt.to_timestamp()
    cutoff = frame["date"].max()
    current_start = cutoff - pd.offsets.MonthBegin(11)
    previous_start = cutoff - pd.offsets.MonthBegin(23)
    scoped = frame.loc[
        (frame["origin_state"] == origin_state) & frame["province_code"].isin(province_codes)
    ]
    if scoped.empty:
        return []
    current = (
        scoped.loc[scoped["date"].between(current_start, cutoff)]
        .groupby("port_code", observed=True)["value"]
        .sum()
    )
    previous = (
        scoped.loc[
            scoped["date"].between(previous_start, current_start - pd.offsets.MonthBegin(1))
        ]
        .groupby("port_code", observed=True)["value"]
        .sum()
    )
    provinces = (
        scoped.loc[scoped["date"].between(current_start, cutoff)]
        .groupby("port_code", observed=True)["province_code"]
        .apply(lambda values: sorted(set(map(str, values))))
    )
    preference = preferred_port.strip().casefold() if preferred_port else None
    results: list[PortStatistic] = []
    for port_code, value in current.sort_values(ascending=False).head(limit).items():
        old = float(previous.get(port_code, 0.0))
        growth = (float(value) - old) / old if old > 0 else None
        results.append(
            PortStatistic(
                port_code=str(port_code),
                port_name=None,
                province_codes=provinces.get(port_code, []),
                latest_12m_trade_value_usd=float(value),
                yoy_growth=growth,
                preferred_port_match=(
                    preference is not None and preference == str(port_code).casefold()
                ),
            )
        )
    return results

