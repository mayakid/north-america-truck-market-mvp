"""Deterministic synthetic history used only for tests and local smoke demos."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .constants import VALID_PROVINCE_CODES


def _stable_noise(*parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:4], "big") / (2**32 - 1)


def make_synthetic_history(
    start: str = "2021-01",
    periods: int = 60,
) -> pd.DataFrame:
    """Create obvious but non-trivial province preferences; never production data."""

    dates = pd.date_range(pd.Period(start, freq="M").to_timestamp(), periods=periods, freq="MS")
    states = ("MI", "NY", "TX", "WA")
    commodities = ("87", "84", "85", "39")
    base_by_province = {
        "XO": 1.00,
        "XQ": 0.58,
        "XC": 0.42,
        "XA": 0.34,
        "XM": 0.25,
        "XS": 0.18,
        "XB": 0.14,
        "XN": 0.12,
        "XW": 0.08,
        "XP": 0.05,
        "XT": 0.03,
        "XY": 0.025,
        "XV": 0.015,
    }
    rows: list[dict[str, object]] = []
    for month_index, date in enumerate(dates):
        seasonal = 1.0 + 0.16 * np.cos((date.month - 10) * 2 * np.pi / 12)
        trend = 1.0 + 0.008 * month_index
        for state in states:
            for commodity in commodities:
                state_scale = {"MI": 1.35, "NY": 1.05, "TX": 0.82, "WA": 0.72}[state]
                commodity_scale = {"87": 1.45, "84": 1.10, "85": 0.96, "39": 0.72}[commodity]
                for province in VALID_PROVINCE_CODES:
                    affinity = base_by_province[province]
                    if state == "MI" and commodity == "87" and province == "XO":
                        affinity *= 2.4
                    if state == "NY" and province == "XQ":
                        affinity *= 1.65
                    if state == "WA" and province == "XC":
                        affinity *= 2.2
                    if state == "TX" and province == "XA":
                        affinity *= 1.4
                    noise = 0.90 + 0.20 * _stable_noise(date, state, commodity, province)
                    value = (
                        4_000_000
                        * state_scale
                        * commodity_scale
                        * affinity
                        * seasonal
                        * trend
                        * noise
                    )
                    rows.append(
                        {
                            "date": date,
                            "origin_state": state,
                            "commodity_code": commodity,
                            "province_code": province,
                            "value": round(value, 2),
                        }
                    )
    return pd.DataFrame(rows)
