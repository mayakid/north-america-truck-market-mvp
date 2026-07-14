"""Pydantic contracts shared by parsing, ranking, API, and CLI layers."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import PROVINCE_BY_POSTAL, PROVINCE_BY_RAW, STATE_CODE_BY_NAME, US_STATE_NAMES


class FleetSize(StrEnum):
    small = "small"
    medium = "medium"
    large = "large"


class ParseDraft(BaseModel):
    """Nullable structure requested from the LLM before strict validation."""

    origin_state: str | None = None
    commodity: str | None = None
    commodity_code: str | None = None
    country: str | None = None
    month: int | None = None
    year: int | None = None
    fleet_size: FleetSize | None = None
    hazmat_capable: bool | None = None
    hazmat_required: bool = False
    preferred_port: str | None = None
    language: Literal["zh", "en"] = "zh"


class ParsedRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    origin_state: str
    commodity: str
    commodity_code: str
    country: Literal["Canada"] = "Canada"
    month: int = Field(ge=1, le=12)
    year: int | None = Field(default=None, ge=2007, le=2100)
    fleet_size: FleetSize | None = None
    hazmat_capable: bool | None = None
    hazmat_required: bool = False
    preferred_port: str | None = None
    language: Literal["zh", "en"] = "zh"
    raw_query: str | None = None

    @field_validator("origin_state", mode="before")
    @classmethod
    def normalize_state(cls, value: Any) -> str:
        text = str(value).strip()
        upper = text.upper()
        if upper in US_STATE_NAMES:
            return upper
        mapped = STATE_CODE_BY_NAME.get(text.casefold())
        if mapped:
            return mapped
        raise ValueError(f"Unsupported U.S. state: {text}")

    @field_validator("commodity_code", mode="before")
    @classmethod
    def normalize_commodity_code(cls, value: Any) -> str:
        code = str(value).strip()
        if code.isdigit() and 1 <= int(code) <= 99:
            return code.zfill(2)
        raise ValueError("commodity_code must be a 2-digit HS chapter between 01 and 99")

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, value: Any) -> str:
        text = str(value).strip().casefold()
        if text in {"canada", "ca", "加拿大"}:
            return "Canada"
        raise ValueError("Only Canada is supported by the confirmed product scope")

    @model_validator(mode="after")
    def validate_hazmat(self) -> ParsedRequest:
        if self.hazmat_required and self.hazmat_capable is False:
            raise ValueError("HazMat cargo requires a HazMat-capable carrier")
        return self


class ParseRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)


class RecommendRequest(BaseModel):
    query: str | None = Field(default=None, min_length=3, max_length=4000)
    structured: ParsedRequest | None = None

    @model_validator(mode="after")
    def require_exactly_one_input(self) -> RecommendRequest:
        if (self.query is None) == (self.structured is None):
            raise ValueError("Provide exactly one of query or structured")
        return self


class FeatureContribution(BaseModel):
    feature: str
    label: str
    value: float | str | None = None
    contribution: float
    direction: Literal["positive", "negative"]


class Evidence(BaseModel):
    evidence_id: str
    title: str
    excerpt: str
    source_url: str
    source_type: Literal["BTS", "model", "system"] = "BTS"


class PortStatistic(BaseModel):
    port_code: str
    port_name: str | None = None
    province_codes: list[str] = Field(default_factory=list)
    latest_12m_trade_value_usd: float
    yoy_growth: float | None = None
    preferred_port_match: bool = False
    caveat: str = (
        "Port statistics are independent auxiliary aggregates and are not a joint "
        "state + commodity + province + port estimate."
    )


class MarketRecommendation(BaseModel):
    rank: int
    province_code: str
    province_postal_code: str
    province_name: str
    opportunity_score: float = Field(ge=0, le=1)
    raw_ranker_score: float
    latest_3m_trade_value_usd: float
    latest_12m_trade_value_usd: float
    recent_yoy_growth: float | None = None
    cold_start: bool = False
    shap_contributions: list[FeatureContribution] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    explanation: str | None = None

    @field_validator("province_code")
    @classmethod
    def valid_province(cls, value: str) -> str:
        if value not in PROVINCE_BY_RAW:
            raise ValueError(f"Unknown BTS Canadian province code: {value}")
        return value

    @model_validator(mode="after")
    def fill_postal_consistency(self) -> MarketRecommendation:
        expected = PROVINCE_BY_RAW[self.province_code].postal_code
        if (
            self.province_postal_code != expected
            or self.province_postal_code not in PROVINCE_BY_POSTAL
        ):
            raise ValueError("province raw and postal codes are inconsistent")
        return self


class TrendPoint(BaseModel):
    month: date
    trade_value_usd: float = Field(ge=0)
    rolling_3m_trade_value_usd: float = Field(ge=0)
    yoy_growth: float | None = None


class MarketTrendSeries(BaseModel):
    province_code: str
    province_postal_code: str
    province_name: str
    source_scope: Literal["origin_state_commodity", "national_commodity_fallback"]
    points: list[TrendPoint] = Field(default_factory=list)

    @field_validator("province_code")
    @classmethod
    def valid_province(cls, value: str) -> str:
        if value not in PROVINCE_BY_RAW:
            raise ValueError(f"Unknown BTS Canadian province code: {value}")
        return value

    @model_validator(mode="after")
    def fill_postal_consistency(self) -> MarketTrendSeries:
        expected = PROVINCE_BY_RAW[self.province_code].postal_code
        if self.province_postal_code != expected:
            raise ValueError("province raw and postal codes are inconsistent")
        return self


class RecommendationResponse(BaseModel):
    request: ParsedRequest
    resolved_planning_date: date
    data_cutoff: date
    recommendations: list[MarketRecommendation]
    market_trends: list[MarketTrendSeries] = Field(default_factory=list)
    auxiliary_ports: list[PortStatistic] = Field(default_factory=list)
    methodology: dict[str, Any]
    limitations: list[str]
    generated_summary: str | None = None
    retrieval_backend: str
    model_version: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_ready: bool
    feature_snapshot_ready: bool
    deepseek_configured: bool
    lightrag_available: bool
