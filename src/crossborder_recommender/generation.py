"""Grounded recommendation explanation generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import pandas as pd

from .llm import DeepSeekClient, format_evidence_for_prompt
from .schemas import Evidence, FeatureContribution, ParsedRequest
from .settings import Settings


@dataclass
class GeneratedExplanation:
    summary: str
    market_explanations: dict[str, str]
    backend: str


class ExplanationGenerator:
    def __init__(self, settings: Settings, client: DeepSeekClient | None = None) -> None:
        self.settings = settings
        self._client = client

    def generate(
        self,
        request: ParsedRequest,
        ranked: pd.DataFrame,
        contributions: dict[str, list[FeatureContribution]],
        evidence: list[Evidence],
    ) -> GeneratedExplanation:
        if self.settings.deepseek_api_key is None and self._client is None:
            return self._deterministic(request, ranked, contributions)
        client = self._client or DeepSeekClient(self.settings)
        facts = []
        for row in ranked.head(5).itertuples(index=False):
            province_contribs = contributions.get(row.province_code, [])
            facts.append(
                {
                    "rank": int(row.rank),
                    "province_code": row.province_code,
                    "province_name": row.province_name,
                    "opportunity_score": round(float(row.opportunity_score), 4),
                    "latest_3m_trade_value_usd": round(float(row.latest_3m_trade_value_usd), 2),
                    "latest_12m_trade_value_usd": round(float(row.latest_12m_trade_value_usd), 2),
                    "recent_yoy_log_growth": round(float(row.recent_yoy_growth), 4),
                    "tree_shap": [item.model_dump() for item in province_contribs],
                }
            )
        language = "Chinese" if request.language == "zh" else "English"
        system = f"""You write a grounded cross-border market recommendation in {language}.
Return strict JSON with keys summary and market_explanations. market_explanations must be an
object keyed by province_code. Use only supplied model facts and evidence. Cite evidence IDs
in square brackets when an industry/data fact is used. Do not invent rates, border wait times,
carrier capacity, causal claims, or a state+commodity+province+port joint statistic. Explain
that opportunity_score is a calibrated ranking signal, not a probability or guaranteed revenue.
Keep each province explanation under 100 words and the summary under 180 words.
"""
        user = (
            "Request:\n"
            + json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
            + "\n\nModel facts:\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\nEvidence:\n"
            + format_evidence_for_prompt([item.model_dump() for item in evidence])
        )
        try:
            payload = client.complete_json(system_prompt=system, user_prompt=user, max_tokens=1800)
            explanations = payload.get("market_explanations", {})
            if not isinstance(explanations, dict) or not payload.get("summary"):
                raise ValueError("Explanation JSON is missing required keys")
            expected_codes = ranked.head(5)["province_code"].astype(str).to_list()
            expected_code_set = set(expected_codes)
            normalized = {str(key): str(value) for key, value in explanations.items()}
            if not expected_code_set.issubset(normalized):
                raise ValueError("Explanation JSON does not cover every Top-5 market")
            allowed_evidence_ids = {item.evidence_id for item in evidence}
            generated_text = "\n".join([str(payload["summary"]), *normalized.values()])
            cited_ids = set(re.findall(r"\[([A-Z][A-Z0-9_-]{2,})\]", generated_text))
            if not cited_ids.issubset(allowed_evidence_ids):
                raise ValueError("Explanation JSON contains an unknown evidence citation")
            return GeneratedExplanation(
                summary=str(payload["summary"]),
                market_explanations={code: normalized[code] for code in expected_codes},
                backend=f"deepseek:{self.settings.deepseek_model}",
            )
        except Exception:
            return self._deterministic(request, ranked, contributions)

    @staticmethod
    def _deterministic(
        request: ParsedRequest,
        ranked: pd.DataFrame,
        contributions: dict[str, list[FeatureContribution]],
    ) -> GeneratedExplanation:
        explanations: dict[str, str] = {}
        for row in ranked.head(5).itertuples(index=False):
            top = contributions.get(row.province_code, [])[:2]
            drivers = "、".join(item.label for item in top) if top else "历史规模与增长信号"
            if request.language == "zh":
                explanations[row.province_code] = (
                    f"{row.province_name} 排名第 {row.rank}，主要模型信号为{drivers}。"
                    "该分数是排序信号，不是成功概率或收入保证。"
                )
            else:
                explanations[row.province_code] = (
                    f"{row.province_name} ranks {row.rank}; the strongest model signals are "
                    f"{drivers}. The score is a ranking signal, not a probability or "
                    "revenue guarantee."
                )
        names = ", ".join(ranked.head(5)["province_name"].astype(str))
        summary = (
            f"Top five province/territory markets: {names}. Results use historical BTS trade "
            "signals and do not represent live rates or border wait times."
        )
        if request.language == "zh":
            summary = (
                f"最值得关注的五个加拿大省/地区为：{names}。结果依据 BTS 历史贸易信号，"
                "不代表实时运价、口岸等待时间或业务结果保证。"
            )
        return GeneratedExplanation(
            summary=summary,
            market_explanations=explanations,
            backend="deterministic_grounded_fallback",
        )
