from __future__ import annotations

import zipfile

import pandas as pd

from crossborder_recommender.data.bts import (
    load_and_normalize_table1,
    load_and_normalize_table2,
)


def _write_zip(path, table1: pd.DataFrame, table2: pd.DataFrame) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sample_dot1.csv", table1.to_csv(index=False))
        archive.writestr("sample_dot2.csv", table2.to_csv(index=False))


def test_table2_keeps_only_canada_export_truck_and_known_provinces(tmp_path):
    common = {
        "USASTATE": "MI",
        "COMMODITY2": "87",
        "VALUE": "1,250",
        "YEAR": "2025",
        "MONTH": "01",
    }
    table2 = pd.DataFrame(
        [
            {**common, "COUNTRY": "1220", "TRDTYPE": "1", "DISAGMOT": "5", "CANPROV": "ON"},
            {**common, "COUNTRY": "2010", "TRDTYPE": "1", "DISAGMOT": "5", "CANPROV": "XO"},
            {**common, "COUNTRY": "1220", "TRDTYPE": "2", "DISAGMOT": "5", "CANPROV": "XO"},
            {**common, "COUNTRY": "1220", "TRDTYPE": "1", "DISAGMOT": "3", "CANPROV": "XO"},
            {**common, "COUNTRY": "1220", "TRDTYPE": "1", "DISAGMOT": "5", "CANPROV": "XX"},
            {
                **common,
                "USASTATE": "DU",
                "COUNTRY": "1220",
                "TRDTYPE": "1",
                "DISAGMOT": "5",
                "CANPROV": "XO",
            },
        ]
    )
    table1 = pd.DataFrame(
        [
            {
                "COUNTRY": "1220",
                "TRDTYPE": "1",
                "DISAGMOT": "5",
                "USASTATE": "MI",
                "CANPROV": "ON",
                "DEPE": "3801",
                "VALUE": "500",
                "YEAR": "2025",
                "MONTH": "01",
            },
            {
                "COUNTRY": "1220",
                "TRDTYPE": "1",
                "DISAGMOT": "5",
                "USASTATE": "DU",
                "CANPROV": "ON",
                "DEPE": "3801",
                "VALUE": "999",
                "YEAR": "2025",
                "MONTH": "01",
            },
        ]
    )
    archive = tmp_path / "January2025.zip"
    _write_zip(archive, table1, table2)

    result = load_and_normalize_table2([archive])

    assert pd.api.types.is_float_dtype(result["value"])
    assert result.to_dict("records") == [
        {
            "date": pd.Timestamp("2025-01-01"),
            "origin_state": "MI",
            "commodity_code": "87",
            "province_code": "XO",
            "value": 1250.0,
        }
    ]


def test_table1_is_normalized_as_independent_port_auxiliary_data(tmp_path):
    table1 = pd.DataFrame(
        [
            {
                "COUNTRY": "1220",
                "TRDTYPE": "1",
                "DISAGMOT": "5",
                "USASTATE": "MI",
                "CANPROV": "ON",
                "DEPE": "3801",
                "VALUE": "500",
                "YEAR": "2025",
                "MONTH": "01",
            },
            {
                "COUNTRY": "1220",
                "TRDTYPE": "1",
                "DISAGMOT": "5",
                "USASTATE": "DU",
                "CANPROV": "ON",
                "DEPE": "3801",
                "VALUE": "999",
                "YEAR": "2025",
                "MONTH": "01",
            },
        ]
    )
    table2 = pd.DataFrame(
        [
            {
                "COUNTRY": "1220",
                "TRDTYPE": "1",
                "DISAGMOT": "5",
                "USASTATE": "MI",
                "COMMODITY2": "87",
                "CANPROV": "ON",
                "VALUE": "1000",
                "YEAR": "2025",
                "MONTH": "01",
            }
        ]
    )
    archive = tmp_path / "January2025.zip"
    _write_zip(archive, table1, table2)

    result = load_and_normalize_table1([archive])

    assert list(result.columns) == [
        "date",
        "origin_state",
        "province_code",
        "port_code",
        "value",
    ]
    assert "commodity_code" not in result.columns
    assert result.iloc[0].to_dict() == {
        "date": pd.Timestamp("2025-01-01"),
        "origin_state": "MI",
        "province_code": "XO",
        "port_code": "3801",
        "value": 500.0,
    }
