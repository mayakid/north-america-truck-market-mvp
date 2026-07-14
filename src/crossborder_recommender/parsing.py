"""Natural-language extraction with DeepSeek JSON mode and deterministic validation."""

from __future__ import annotations

import re

from pydantic import ValidationError

from .catalog import catalog_for_prompt, commodity_description, resolve_commodity_code
from .constants import MONTH_NAMES, STATE_CODE_BY_NAME, US_STATE_NAMES
from .exceptions import ExternalServiceError, IncompleteInputError, InvalidInputError
from .llm import DeepSeekClient
from .schemas import FleetSize, ParseDraft, ParsedRequest
from .settings import Settings

PARSER_SYSTEM_PROMPT = """You extract a carrier profile and shipment request for a Canada
cross-border truck market recommender. Return one JSON object only. Use these keys:
origin_state, commodity, commodity_code, country, month, year, fleet_size,
hazmat_capable, hazmat_required, preferred_port, language.

Rules:
- origin_state must be a 2-letter U.S. postal code when identifiable.
- country must be Canada if the request targets Canada. Do not silently change a different country.
- month is an integer 1..12. year is optional and null when absent.
- commodity_code is a zero-padded 2-digit HS chapter.
- commodity preserves a concise user-facing name.
- fleet_size is small, medium, large, or null.
- hazmat_required is true only when the cargo is explicitly described as hazardous.
- hazmat_capable is true/false only when the carrier explicitly states it; otherwise null.
- language is zh for a primarily Chinese request, otherwise en.
- Any unprovided value must be null, except hazmat_required defaults to false.
- The word JSON is included here because the API's JSON response mode requires it.

BTS HS chapter catalog:
{catalog}
"""


class NaturalLanguageParser:
    def __init__(self, settings: Settings, client: DeepSeekClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self.last_source = "not_run"

    def parse(self, query: str) -> ParsedRequest:
        if not query or len(query.strip()) < 3:
            raise IncompleteInputError(["origin_state", "commodity", "country", "month"])
        draft: ParseDraft | None = None
        llm_error: ExternalServiceError | None = None
        if self.settings.deepseek_api_key is not None or self._client is not None:
            try:
                client = self._client or DeepSeekClient(self.settings)
                payload = client.complete_json(
                    system_prompt=PARSER_SYSTEM_PROMPT.format(catalog=catalog_for_prompt()),
                    user_prompt=f"Extract the request as JSON:\n{query}",
                )
                draft = ParseDraft.model_validate(payload)
                self.last_source = "deepseek_json"
            except (ExternalServiceError, ValidationError) as exc:
                llm_error = (
                    exc
                    if isinstance(exc, ExternalServiceError)
                    else ExternalServiceError(f"DeepSeek parse schema failed: {exc}")
                )

        if draft is None:
            draft = self._deterministic_draft(query)
            self.last_source = "deterministic_fallback"

        merged = self._merge_with_deterministic(draft, query)
        try:
            return self._validate_draft(merged, query)
        except (IncompleteInputError, InvalidInputError):
            if llm_error is not None and self.last_source == "deterministic_fallback":
                raise ExternalServiceError(
                    f"DeepSeek parsing failed and deterministic parsing was incomplete: {llm_error}"
                ) from llm_error
            raise

    def _merge_with_deterministic(self, draft: ParseDraft, query: str) -> ParseDraft:
        fallback = self._deterministic_draft(query)
        values = draft.model_dump()
        for field, value in fallback.model_dump().items():
            if values.get(field) is None and value is not None:
                values[field] = value
        if not values.get("commodity_code"):
            values["commodity_code"] = resolve_commodity_code(values.get("commodity"))
        return ParseDraft.model_validate(values)

    def _validate_draft(self, draft: ParseDraft, query: str) -> ParsedRequest:
        commodity_code = draft.commodity_code or resolve_commodity_code(draft.commodity)
        missing: list[str] = []
        if not draft.origin_state:
            missing.append("origin_state")
        if not draft.commodity or not commodity_code:
            missing.append("commodity")
        if not draft.country:
            missing.append("country")
        if draft.month is None:
            missing.append("month")
        if missing:
            raise IncompleteInputError(missing)
        try:
            return ParsedRequest(
                origin_state=draft.origin_state,
                commodity=draft.commodity or commodity_description(commodity_code or ""),
                commodity_code=commodity_code,
                country=draft.country,
                month=draft.month,
                year=draft.year,
                fleet_size=draft.fleet_size,
                hazmat_capable=draft.hazmat_capable,
                hazmat_required=draft.hazmat_required,
                preferred_port=draft.preferred_port,
                language=draft.language,
                raw_query=query,
            )
        except ValidationError as exc:
            raise InvalidInputError(str(exc)) from exc

    @staticmethod
    def _deterministic_draft(query: str) -> ParseDraft:
        lowered = query.casefold()
        state: str | None = None
        for code, name in US_STATE_NAMES.items():
            if re.search(rf"(?<![a-z]){re.escape(name.casefold())}(?![a-z])", lowered):
                state = code
                break
        if state is None:
            for code in US_STATE_NAMES:
                if re.search(rf"(?<![A-Za-z]){code}(?![A-Za-z])", query, flags=re.IGNORECASE):
                    state = code
                    break
        if state is None:
            for name, code in STATE_CODE_BY_NAME.items():
                if name in lowered:
                    state = code
                    break

        month: int | None = None
        chinese_month = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*(?:月|月份)", query)
        numeric_month = re.search(
            r"(?:month|月份?)\s*[:：-]?\s*(1[0-2]|0?[1-9])", query, flags=re.IGNORECASE
        )
        if chinese_month or numeric_month:
            month = int((chinese_month or numeric_month).group(1))
        else:
            for name, number in MONTH_NAMES.items():
                if re.search(rf"\b{name}\b", lowered):
                    month = number
                    break

        year_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", query)
        year = int(year_match.group(1)) if year_match else None
        commodity_code_match = re.search(
            r"(?:HS|商品(?:代码)?|chapter)\s*[-:#：]?\s*(\d{1,2})\b",
            query,
            flags=re.IGNORECASE,
        )
        commodity_code = (
            commodity_code_match.group(1).zfill(2)
            if commodity_code_match
            else resolve_commodity_code(query)
        )
        commodity = commodity_description(commodity_code) if commodity_code else None

        country: str | None = None
        if "canada" in lowered or "加拿大" in query:
            country = "Canada"
        elif "mexico" in lowered or "墨西哥" in query:
            country = "Mexico"

        fleet_size: FleetSize | None = None
        medium_terms = (
            "medium carrier",
            "medium fleet",
            "中型承运商",
            "中型卡车承运商",
            "中型车队",
        )
        small_terms = (
            "small carrier",
            "small fleet",
            "小型承运商",
            "小型卡车承运商",
            "小型车队",
        )
        large_terms = (
            "large carrier",
            "large fleet",
            "大型承运商",
            "大型卡车承运商",
            "大型车队",
        )
        if any(term in lowered for term in medium_terms):
            fleet_size = FleetSize.medium
        elif any(term in lowered for term in small_terms):
            fleet_size = FleetSize.small
        elif any(term in lowered for term in large_terms):
            fleet_size = FleetSize.large

        hazmat_terms = ("hazmat cargo", "hazardous cargo", "dangerous goods", "危险品")
        hazmat_required = any(
            term in lowered for term in hazmat_terms
        )
        hazmat_capable: bool | None = None
        if any(term in lowered for term in ("hazmat capable", "hazmat-certified", "有危险品资质")):
            hazmat_capable = True
        if any(term in lowered for term in ("not hazmat", "no hazmat", "无危险品资质")):
            hazmat_capable = False

        preferred_port: str | None = None
        port_match = re.search(
            r"(?:preferred port|prefer(?:red)?|偏好口岸|首选口岸)\s*[:：]?\s*([\w -]{2,60})",
            query,
            flags=re.IGNORECASE,
        )
        if port_match:
            preferred_port = port_match.group(1).strip(" ,.;，。")

        language = "zh" if re.search(r"[\u4e00-\u9fff]", query) else "en"
        return ParseDraft(
            origin_state=state,
            commodity=commodity,
            commodity_code=commodity_code,
            country=country,
            month=month,
            year=year,
            fleet_size=fleet_size,
            hazmat_capable=hazmat_capable,
            hazmat_required=hazmat_required,
            preferred_port=preferred_port,
            language=language,
        )
