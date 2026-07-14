from __future__ import annotations

import pytest

from crossborder_recommender.exceptions import IncompleteInputError, InvalidInputError
from crossborder_recommender.parsing import NaturalLanguageParser
from crossborder_recommender.settings import Settings


def test_deterministic_parser_extracts_confirmed_query_fields():
    parser = NaturalLanguageParser(Settings())

    parsed = parser.parse(
        "我是Michigan的中型承运商，主要运输汽车零部件到加拿大，10月份有哪些市场？"
    )

    assert parsed.origin_state == "MI"
    assert parsed.commodity_code == "87"
    assert parsed.country == "Canada"
    assert parsed.month == 10
    assert parsed.fleet_size.value == "medium"
    assert parser.last_source == "deterministic_fallback"


def test_non_canada_request_is_rejected():
    parser = NaturalLanguageParser(Settings())
    with pytest.raises(InvalidInputError):
        parser.parse("Michigan HS 87 export to Mexico in October")


def test_missing_required_fields_are_reported():
    parser = NaturalLanguageParser(Settings())
    with pytest.raises(IncompleteInputError) as exc_info:
        parser.parse("10月份去加拿大")
    assert "origin_state" in exc_info.value.missing_fields
    assert "commodity" in exc_info.value.missing_fields


def test_hazmat_is_rejected_only_when_need_and_inability_are_explicit():
    parser = NaturalLanguageParser(Settings())
    with pytest.raises(InvalidInputError):
        parser.parse(
            "Michigan运输危险品到加拿大，HS 28，10月，无危险品资质"
        )
