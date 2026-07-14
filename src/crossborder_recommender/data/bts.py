"""Download and normalize official BTS TransBorder raw-data tables.

The confirmed product scope uses:
* DOT2 / Table 2 for state + commodity + Canadian province ranking.
* DOT1 / Table 1 for independent state/province/port auxiliary statistics.
"""

from __future__ import annotations

import calendar
import io
import re
import time
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx
import pandas as pd

from ..constants import (
    BTS_COUNTRY_CANADA,
    BTS_MODE_TRUCK,
    BTS_TRADE_EXPORT,
    PROVINCE_BY_POSTAL,
    US_STATE_NAMES,
    VALID_PROVINCE_CODES,
)
from ..exceptions import DataUnavailableError

BTS_RAW_URL = (
    "https://www.bts.gov/sites/bts.dot.gov/files/transborder-raw/"
    "{year}/{month_name}{year}.zip"
)

TABLE2_REQUIRED = {
    "COUNTRY",
    "TRDTYPE",
    "DISAGMOT",
    "USASTATE",
    "COMMODITY",
    "CANPROV",
    "VALUE",
    "STATYR",
    "STATMO",
}
TABLE1_REQUIRED = {
    "COUNTRY",
    "TRDTYPE",
    "DISAGMOT",
    "USASTATE",
    "CANPROV",
    "DEPE",
    "VALUE",
    "STATYR",
    "STATMO",
}

CURRENT_FORMAT_ALIASES = {
    "COMMODITY2": "COMMODITY",
    "MONTH": "STATMO",
    "YEAR": "STATYR",
}


def iter_months(start: str | pd.Period, end: str | pd.Period) -> Iterator[pd.Period]:
    start_period = pd.Period(start, freq="M")
    end_period = pd.Period(end, freq="M")
    if end_period < start_period:
        raise ValueError("end month must not precede start month")
    yield from pd.period_range(start_period, end_period, freq="M")


class BTSDownloader:
    """Cache official monthly BTS ZIP files without extracting untrusted paths."""

    def __init__(self, destination: Path, timeout_seconds: float = 120.0) -> None:
        self.destination = destination
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def url_for(period: pd.Period) -> str:
        return BTS_RAW_URL.format(
            year=period.year,
            month_name=calendar.month_name[period.month],
        )

    def path_for(self, period: pd.Period) -> Path:
        filename = f"{calendar.month_name[period.month]}{period.year}.zip"
        return self.destination / str(period.year) / filename

    def download_month(self, period: str | pd.Period, *, overwrite: bool = False) -> Path:
        month = pd.Period(period, freq="M")
        output = self.path_for(month)
        if output.exists() and not overwrite:
            self._validate_zip(output)
            return output

        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_suffix(".zip.part")
        headers = {
            "User-Agent": "crossborder-opportunity-recommender/0.1 (+BTS public data research)",
            "Accept": "application/zip,application/octet-stream;q=0.9,*/*;q=0.1",
            "Referer": "https://www.bts.gov/topics/transborder-raw-data",
        }
        url = self.url_for(month)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.stream(
                    "GET",
                    url,
                    headers=headers,
                    follow_redirects=True,
                    timeout=self.timeout_seconds,
                ) as response:
                    response.raise_for_status()
                    with partial.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
                self._validate_zip(partial)
                partial.replace(output)
                return output
            except (httpx.HTTPError, OSError, zipfile.BadZipFile) as exc:
                last_error = exc
                partial.unlink(missing_ok=True)
                if attempt < 2:
                    time.sleep(2**attempt)

        raise DataUnavailableError(
            f"Unable to download official BTS data for {month}: {last_error}. "
            "The BTS CDN may reject automated clients; manually place the official ZIP at "
            f"{output} and rerun the command."
        )

    def download_range(
        self,
        start: str | pd.Period,
        end: str | pd.Period,
        *,
        overwrite: bool = False,
    ) -> list[Path]:
        return [
            self.download_month(period, overwrite=overwrite)
            for period in iter_months(start, end)
        ]

    @staticmethod
    def _validate_zip(path: Path) -> None:
        if path.stat().st_size == 0:
            raise zipfile.BadZipFile("empty BTS archive")
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise zipfile.BadZipFile(f"corrupt member: {bad_member}")


def _canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [re.sub(r"[^A-Z0-9]+", "", str(column).upper()) for column in result.columns]
    return result.rename(columns=CURRENT_FORMAT_ALIASES)


def _read_delimited(payload: bytes) -> pd.DataFrame:
    # Current-format DOT files are delimited. sep=None asks the Python engine to infer
    # comma, tab, or pipe separators, which vary across archived releases.
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                io.BytesIO(payload),
                sep=None,
                engine="python",
                dtype=str,
                encoding=encoding,
            )
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise DataUnavailableError("BTS table is not a supported delimited text file")


def read_bts_table_from_zip(path: Path, table_number: int) -> pd.DataFrame:
    required = TABLE2_REQUIRED if table_number == 2 else TABLE1_REQUIRED
    name_pattern = re.compile(rf"(^|[^0-9])dot\s*{table_number}([^0-9]|$)", re.IGNORECASE)
    candidates: list[tuple[int, str, pd.DataFrame]] = []

    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            supported_suffixes = {"", ".csv", ".txt", ".dat"}
            if member.endswith("/") or Path(member).suffix.lower() not in supported_suffixes:
                continue
            payload = archive.read(member)
            try:
                frame = _canonical_columns(_read_delimited(payload))
            except DataUnavailableError:
                continue
            score = len(required.intersection(frame.columns))
            member_stem = Path(member).stem
            if name_pattern.search(member_stem):
                score += len(required)
            if re.fullmatch(
                rf"dot\s*{table_number}[_ -]?(?:0[1-9]|1[0-2])\d{{2}}",
                member_stem,
                flags=re.IGNORECASE,
            ):
                # December archives may also contain annual and YTD tables.
                # Prefer the exact monthly member so each ZIP contributes once.
                score += 2
            candidates.append((score, member, frame))

    if not candidates:
        raise DataUnavailableError(f"No readable tables found in {path}")
    score, member, frame = max(candidates, key=lambda item: item[0])
    missing = required.difference(frame.columns)
    if missing:
        raise DataUnavailableError(
            f"Could not identify BTS Table {table_number} in {path}; best member {member} "
            f"is missing {sorted(missing)}"
        )
    return frame


def _read_input_table(path: Path, table_number: int) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return read_bts_table_from_zip(path, table_number)
    if suffix == ".parquet":
        return _canonical_columns(pd.read_parquet(path))
    if suffix in {".csv", ".txt", ".dat"}:
        return _canonical_columns(pd.read_csv(path, dtype=str, sep=None, engine="python"))
    raise DataUnavailableError(f"Unsupported BTS input file: {path}")


def _normalize_province(value: object) -> str | None:
    code = str(value).strip().upper()
    if code in VALID_PROVINCE_CODES:
        return code
    province = PROVINCE_BY_POSTAL.get(code)
    return province.raw_code if province else None


def _normalize_common(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in (
        "COUNTRY",
        "TRDTYPE",
        "DISAGMOT",
        "USASTATE",
        "COMMODITY",
        "CANPROV",
        "DEPE",
        "STATYR",
        "STATMO",
    ):
        if column in result:
            result[column] = result[column].astype("string").str.strip().str.upper()
    result["VALUE"] = pd.to_numeric(
        result["VALUE"].astype("string").str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0.0).astype("float64")
    result["province_code"] = result["CANPROV"].map(_normalize_province)
    result["date"] = pd.to_datetime(
        result["STATYR"].str.zfill(4) + "-" + result["STATMO"].str.zfill(2) + "-01",
        errors="coerce",
    )
    return result


def _iter_frames(paths: Iterable[Path], table_number: int) -> Iterator[pd.DataFrame]:
    for path in paths:
        yield _normalize_common(_read_input_table(Path(path), table_number))


def load_and_normalize_table2(paths: Iterable[Path]) -> pd.DataFrame:
    """Return monthly state/commodity/province values for the confirmed scope."""

    selected: list[pd.DataFrame] = []
    for frame in _iter_frames(paths, table_number=2):
        scoped = frame.loc[
            (frame["COUNTRY"] == BTS_COUNTRY_CANADA)
            & (frame["TRDTYPE"] == BTS_TRADE_EXPORT)
            & (frame["DISAGMOT"] == BTS_MODE_TRUCK)
            & frame["province_code"].notna()
            & frame["date"].notna(),
            ["date", "USASTATE", "COMMODITY", "province_code", "VALUE"],
        ].rename(
            columns={
                "USASTATE": "origin_state",
                "COMMODITY": "commodity_code",
                "VALUE": "value",
            }
        )
        scoped["commodity_code"] = scoped["commodity_code"].str.zfill(2)
        selected.append(scoped)

    if not selected:
        raise DataUnavailableError("No BTS Table 2 inputs were supplied")
    combined = pd.concat(selected, ignore_index=True)
    combined = combined.loc[
        combined["origin_state"].isin(US_STATE_NAMES)
        & combined["commodity_code"].str.fullmatch(r"\d{2}", na=False)
    ]
    return (
        combined.groupby(
            ["date", "origin_state", "commodity_code", "province_code"],
            as_index=False,
            observed=True,
        )["value"]
        .sum()
        .sort_values(["date", "origin_state", "commodity_code", "province_code"])
        .reset_index(drop=True)
    )


def load_and_normalize_table1(paths: Iterable[Path]) -> pd.DataFrame:
    """Return port values used only as an independent auxiliary aggregate."""

    selected: list[pd.DataFrame] = []
    for frame in _iter_frames(paths, table_number=1):
        scoped = frame.loc[
            (frame["COUNTRY"] == BTS_COUNTRY_CANADA)
            & (frame["TRDTYPE"] == BTS_TRADE_EXPORT)
            & (frame["DISAGMOT"] == BTS_MODE_TRUCK)
            & frame["province_code"].notna()
            & frame["date"].notna(),
            ["date", "USASTATE", "province_code", "DEPE", "VALUE"],
        ].rename(columns={"USASTATE": "origin_state", "DEPE": "port_code", "VALUE": "value"})
        selected.append(scoped)

    if not selected:
        raise DataUnavailableError("No BTS Table 1 inputs were supplied")
    combined = pd.concat(selected, ignore_index=True)
    combined = combined.loc[combined["origin_state"].isin(US_STATE_NAMES)]
    return (
        combined.groupby(
            ["date", "origin_state", "province_code", "port_code"],
            as_index=False,
            observed=True,
        )["value"]
        .sum()
        .sort_values(["date", "origin_state", "province_code", "port_code"])
        .reset_index(drop=True)
    )
