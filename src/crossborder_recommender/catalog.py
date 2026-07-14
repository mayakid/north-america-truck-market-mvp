"""HS chapter catalog and alias resolution."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from .constants import COMMODITY_ALIASES
from .settings import PROJECT_ROOT

CATALOG_PATH = PROJECT_ROOT / "data" / "reference" / "hs2_commodities.csv"


@lru_cache(maxsize=1)
def load_commodity_catalog(path: Path = CATALOG_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"code": str})
    frame["code"] = frame["code"].str.zfill(2)
    return frame


def commodity_description(code: str) -> str:
    frame = load_commodity_catalog()
    match = frame.loc[frame["code"] == str(code).zfill(2), "description"]
    return str(match.iloc[0]) if not match.empty else f"HS chapter {str(code).zfill(2)}"


def resolve_commodity_code(text: str | None) -> str | None:
    if not text:
        return None
    normalized = text.strip().casefold()
    if normalized.isdigit() and 1 <= int(normalized) <= 99:
        return normalized.zfill(2)
    sorted_aliases = sorted(
        COMMODITY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    )
    for alias, code in sorted_aliases:
        if alias.casefold() in normalized:
            return code
    catalog = load_commodity_catalog()
    for row in catalog.itertuples(index=False):
        description = str(row.description).casefold()
        if normalized in description or description in normalized:
            return str(row.code).zfill(2)
    return None


def catalog_for_prompt() -> str:
    return "\n".join(
        f"{row.code}: {row.description}" for row in load_commodity_catalog().itertuples(index=False)
    )
