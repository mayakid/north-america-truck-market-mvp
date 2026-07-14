from __future__ import annotations

import asyncio

from crossborder_recommender.rag import EvidenceRetriever
from crossborder_recommender.settings import Settings


def test_lexical_fallback_returns_source_bound_evidence(project_root, tmp_path):
    settings = Settings(
        knowledge_dir=project_root / "knowledge",
        rag_working_dir=tmp_path / "rag",
    )
    retriever = EvidenceRetriever(settings)

    result = asyncio.run(retriever.retrieve("BTS Table 2 Canada truck HS 87", limit=3))

    assert result.backend == "lexical_fallback"
    assert 1 <= len(result.evidence) <= 3
    assert all(item.source_url.startswith("https://") for item in result.evidence)
    assert all(item.title and item.excerpt for item in result.evidence)


def test_structured_lightrag_chunks_are_converted_to_evidence(
    monkeypatch, project_root, tmp_path
):
    settings = Settings(
        deepseek_api_key="test-only",
        knowledge_dir=project_root / "knowledge",
        rag_working_dir=tmp_path / "rag",
    )
    settings.rag_working_dir.mkdir(parents=True)
    retriever = EvidenceRetriever(settings)
    retriever.manifest_path.write_text("{}", encoding="utf-8")
    content = (project_root / "knowledge" / "bts_table_structure.md").read_text(
        encoding="utf-8"
    )

    class FakeLightRAG:
        async def aquery_data(self, query, param):
            return {"status": "success", "data": {"chunks": [{"content": content}]}}

        async def finalize_storages(self):
            return None

    async def fake_builder():
        return FakeLightRAG()

    monkeypatch.setattr(retriever, "_build_lightrag", fake_builder)

    result = asyncio.run(retriever.retrieve("BTS Table 2", limit=2))

    assert result.backend == "lightrag"
    assert result.evidence[0].evidence_id == "BTS-TABLE-STRUCTURE"
    assert "Table 2" in result.evidence[0].excerpt
