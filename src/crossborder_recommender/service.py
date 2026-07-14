"""End-to-end parsing -> ranking -> SHAP -> retrieval -> explanation orchestration."""

from __future__ import annotations

import asyncio
from datetime import date

import numpy as np
import pandas as pd

from .catalog import commodity_description
from .constants import PROVINCE_BY_RAW
from .exceptions import ModelUnavailableError
from .explainability import explain_candidates
from .generation import ExplanationGenerator
from .parsing import NaturalLanguageParser
from .ports import port_statistics
from .rag import EvidenceRetriever
from .ranking import RankerBundle
from .schemas import (
    MarketRecommendation,
    ParsedRequest,
    RecommendationResponse,
)
from .settings import Settings, get_settings
from .trends import market_trend_series


class RecommendationService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        bundle: RankerBundle | None = None,
        parser: NaturalLanguageParser | None = None,
        retriever: EvidenceRetriever | None = None,
        generator: ExplanationGenerator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._bundle = bundle
        self.parser = parser or NaturalLanguageParser(self.settings)
        self.retriever = retriever or EvidenceRetriever(self.settings)
        self.generator = generator or ExplanationGenerator(self.settings)

    @property
    def bundle(self) -> RankerBundle:
        if self._bundle is None:
            self._bundle = RankerBundle.load(self.settings.model_artifact_path)
        return self._bundle

    def parse(self, query: str) -> ParsedRequest:
        return self.parser.parse(query)

    @staticmethod
    def resolve_planning_date(request: ParsedRequest, cutoff: pd.Timestamp) -> date:
        if request.year is not None:
            return date(request.year, request.month, 1)
        year = cutoff.year + (1 if request.month <= cutoff.month else 0)
        return date(year, request.month, 1)

    async def recommend(
        self,
        *,
        query: str | None = None,
        structured: ParsedRequest | None = None,
    ) -> RecommendationResponse:
        if (query is None) == (structured is None):
            raise ValueError("Provide exactly one of query or structured")
        request = structured or await asyncio.to_thread(self.parse, query or "")
        bundle = self.bundle
        ranked, ranking_method = bundle.rank(
            request.origin_state, request.commodity_code, request.month
        )
        ranked = ranked.head(self.settings.top_k).copy()
        ranked["province_name"] = ranked["province_code"].map(
            lambda code: PROVINCE_BY_RAW[code].name
        )
        ranked["province_postal_code"] = ranked["province_code"].map(
            lambda code: PROVINCE_BY_RAW[code].postal_code
        )

        shap_map: dict[str, list] = {}
        if ranking_method == "lightgbm_lambdarank":
            try:
                shap_lists = await asyncio.to_thread(explain_candidates, bundle, ranked)
                shap_map = {
                    code: contributions
                    for code, contributions in zip(ranked["province_code"], shap_lists, strict=True)
                }
            except Exception:
                shap_map = {}

        evidence_query = (
            f"BTS Canada truck exports {request.origin_state} HS {request.commodity_code} "
            f"{commodity_description(request.commodity_code)} province market "
            + " ".join(ranked["province_name"].astype(str))
        )
        retrieval = await self.retriever.retrieve(evidence_query, limit=5)
        generation = await asyncio.to_thread(
            self.generator.generate,
            request,
            ranked,
            shap_map,
            retrieval.evidence,
        )

        recommendations: list[MarketRecommendation] = []
        for row in ranked.itertuples(index=False):
            log_growth = float(row.recent_yoy_growth)
            growth_fraction = float(np.expm1(np.clip(log_growth, -20, 20)))
            recommendations.append(
                MarketRecommendation(
                    rank=int(row.rank),
                    province_code=row.province_code,
                    province_postal_code=row.province_postal_code,
                    province_name=row.province_name,
                    opportunity_score=float(row.opportunity_score),
                    raw_ranker_score=float(row.raw_ranker_score),
                    latest_3m_trade_value_usd=float(row.latest_3m_trade_value_usd),
                    latest_12m_trade_value_usd=float(row.latest_12m_trade_value_usd),
                    recent_yoy_growth=growth_fraction,
                    cold_start=bool(row.cold_start),
                    shap_contributions=shap_map.get(row.province_code, []),
                    evidence=retrieval.evidence,
                    explanation=generation.market_explanations.get(row.province_code),
                )
            )

        top_codes = ranked["province_code"].astype(str).to_list()
        market_trends = market_trend_series(
            bundle.history,
            origin_state=request.origin_state,
            commodity_code=request.commodity_code,
            province_codes=top_codes,
        )
        auxiliary_ports = port_statistics(
            bundle.port_history,
            origin_state=request.origin_state,
            province_codes=top_codes,
            preferred_port=request.preferred_port,
        )
        limitations = [
            "结果反映历史市场机会，不代表实时运价、口岸等待时间或收入保证。",
            "BTS 省字段和海关口岸字段可能不等于最终物理目的地或实际过境点。",
            "口岸统计来自不含商品字段的独立聚合表，不是州＋商品＋省＋口岸联合估计。",
            "车队规模已解析但不改变排序；BTS 2 位商品码不用于推断 HazMat 资质。",
        ]
        if request.year is None:
            limitations.append(
                "输入未提供年份；计划年月被解析为数据截止月之后最近一次该月份。"
            )
        if bundle.port_history is None:
            limitations.append("当前模型包未包含 BTS Table 1，因此未返回口岸辅助统计。")
        if market_trends and market_trends[0].source_scope == "national_commodity_fallback":
            limitations.append(
                "该州与商品组合缺少历史记录；趋势图和排序均回退为全美该商品的省级历史。"
            )
        if bundle.metadata.get("synthetic_data"):
            limitations.append("当前模型由合成数据训练，仅可用于功能演示，不可用于商业决策。")
        acceptance_gate = bundle.metadata.get("acceptance_gate", {})
        if acceptance_gate and not acceptance_gate.get("passed", False):
            limitations.append(
                "当前模型未超过历史贸易规模基线，未通过上线验收门槛；排序仅供研发验证。"
            )
        if retrieval.backend != "lightrag":
            limitations.append(f"证据检索本次使用 {retrieval.backend}，而非已索引的 LightRAG。")

        trained_at = str(bundle.metadata.get("trained_at_utc", "unknown"))
        return RecommendationResponse(
            request=request,
            resolved_planning_date=self.resolve_planning_date(request, bundle.data_cutoff),
            data_cutoff=bundle.data_cutoff.date(),
            recommendations=recommendations,
            market_trends=market_trends,
            auxiliary_ports=auxiliary_ports,
            methodology={
                "candidate": "13 known Canadian provinces and territories; unknown code excluded",
                "scope": "U.S. exports to Canada by truck",
                "label": "0.60 * trade-value percentile + 0.40 * YoY-growth percentile",
                "ranking_method": ranking_method,
                "score": "validation-calibrated ranking signal in [0,1], not a probability",
                "parser": self.parser.last_source,
                "explanation": generation.backend,
                "trend": (
                    "Table 2 monthly state + HS2 + province history; "
                    "ports are excluded"
                ),
                "port_scope": "independent state/province/port aggregate without commodity",
            },
            limitations=limitations,
            generated_summary=generation.summary,
            retrieval_backend=retrieval.backend,
            model_version=f"artifact-{bundle.artifact_version}@{trained_at}",
        )


def load_service(settings: Settings | None = None) -> RecommendationService:
    configured = settings or get_settings()
    if not configured.model_artifact_path.exists():
        raise ModelUnavailableError(
            f"Train a model before starting recommendations: {configured.model_artifact_path}"
        )
    return RecommendationService(configured)
