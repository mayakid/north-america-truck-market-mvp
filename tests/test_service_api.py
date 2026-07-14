from __future__ import annotations

import asyncio

import httpx

from crossborder_recommender import api
from crossborder_recommender.generation import ExplanationGenerator
from crossborder_recommender.parsing import NaturalLanguageParser
from crossborder_recommender.rag import EvidenceRetriever
from crossborder_recommender.service import RecommendationService
from crossborder_recommender.settings import Settings


def test_api_returns_top5_and_explicit_port_scope(
    monkeypatch, project_root, tmp_path, trained_bundle
):
    settings = Settings(
        model_artifact_path=tmp_path / "unused.joblib",
        knowledge_dir=project_root / "knowledge",
        rag_working_dir=tmp_path / "rag",
    )
    service = RecommendationService(
        settings,
        bundle=trained_bundle,
        parser=NaturalLanguageParser(settings),
        retriever=EvidenceRetriever(settings),
        generator=ExplanationGenerator(settings),
    )
    monkeypatch.setattr(api, "get_service", lambda: service)
    async def request_recommendation():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/v1/recommend",
                json={
                    "query": (
                        "Michigan的中型承运商运输汽车零部件到加拿大，"
                        "10月份有哪些市场？"
                    )
                },
            )

    response = asyncio.run(request_recommendation())

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["recommendations"]) == 5
    assert len({item["province_code"] for item in body["recommendations"]}) == 5
    assert len(body["market_trends"]) == 5
    assert [item["province_code"] for item in body["market_trends"]] == [
        item["province_code"] for item in body["recommendations"]
    ]
    assert all(len(item["points"]) == 24 for item in body["market_trends"])
    assert all(
        item["source_scope"] == "origin_state_commodity"
        for item in body["market_trends"]
    )
    assert body["methodology"]["scope"] == "U.S. exports to Canada by truck"
    assert "without commodity" in body["methodology"]["port_scope"]
    assert body["auxiliary_ports"] == []
    assert any("合成数据" in item for item in body["limitations"])
    assert any("验收门槛" in item for item in body["limitations"])
