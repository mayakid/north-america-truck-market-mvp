"""LightRAG evidence indexing and retrieval for the small official-source corpus."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer

from .exceptions import ExternalServiceError
from .schemas import Evidence
from .settings import Settings

_HASH_EMBEDDER = HashingVectorizer(
    analyzer="char_wb",
    ngram_range=(2, 4),
    n_features=1024,
    alternate_sign=False,
    norm="l2",
)
_EVIDENCE_PATTERN = re.compile(
    r"EVIDENCE_ID:\s*(?P<id>[^\n]+)\n"
    r"TITLE:\s*(?P<title>[^\n]+)\n"
    r"SOURCE_URL:\s*(?P<url>[^\n]+)\n"
    r"SOURCE_TYPE:\s*(?P<type>[^\n]+)\n"
    r"CONTENT:\s*\n(?P<content>.*?)(?=\nEVIDENCE_ID:|\Z)",
    flags=re.DOTALL,
)


@dataclass
class RetrievalResult:
    evidence: list[Evidence]
    backend: str
    raw_context: str = ""


def _parse_evidence(text: str) -> list[Evidence]:
    items: list[Evidence] = []
    seen: set[str] = set()
    for match in _EVIDENCE_PATTERN.finditer(text):
        evidence_id = match.group("id").strip()
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        source_type = match.group("type").strip()
        if source_type not in {"BTS", "model", "system"}:
            source_type = "BTS"
        content = re.sub(r"\s+", " ", match.group("content")).strip()
        items.append(
            Evidence(
                evidence_id=evidence_id,
                title=match.group("title").strip(),
                excerpt=content[:900],
                source_url=match.group("url").strip(),
                source_type=source_type,
            )
        )
    return items


class EvidenceRetriever:
    """Use LightRAG when indexed, with an explicit lexical fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manifest_path = settings.rag_working_dir / "corpus_manifest.json"

    def _documents(self) -> list[Path]:
        return sorted(self.settings.knowledge_dir.glob("*.md"))

    async def _build_lightrag(self):
        try:
            from lightrag import LightRAG
            from lightrag.llm.openai import openai_complete_if_cache
            from lightrag.utils import EmbeddingFunc
        except ImportError as exc:
            raise ExternalServiceError("lightrag-hku is not installed") from exc
        if self.settings.deepseek_api_key is None:
            raise ExternalServiceError("DEEPSEEK_API_KEY is required to initialize LightRAG")

        api_key = self.settings.deepseek_api_key.get_secret_value()
        model = self.settings.deepseek_model
        base_url = self.settings.deepseek_base_url

        async def llm_model_func(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict] | None = None,
            **kwargs,
        ) -> str:
            return await openai_complete_if_cache(
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                base_url=base_url,
                api_key=api_key,
                timeout=int(self.settings.llm_timeout_seconds),
                **kwargs,
            )

        async def local_embedding(texts: list[str]) -> np.ndarray:
            return _HASH_EMBEDDER.transform(texts).toarray().astype(np.float32)

        rag = LightRAG(
            working_dir=str(self.settings.rag_working_dir),
            embedding_func=EmbeddingFunc(
                embedding_dim=1024,
                func=local_embedding,
                max_token_size=8192,
                model_name="local-char-ngram-hashing-v1",
            ),
            llm_model_func=llm_model_func,
            llm_model_name=model,
            chunk_token_size=900,
            chunk_overlap_token_size=80,
            top_k=8,
            chunk_top_k=6,
            enable_llm_cache=True,
        )
        await rag.initialize_storages()
        return rag

    async def index(self) -> dict[str, object]:
        documents = self._documents()
        if not documents:
            raise ExternalServiceError(
                f"No knowledge documents found in {self.settings.knowledge_dir}"
            )
        self.settings.rag_working_dir.mkdir(parents=True, exist_ok=True)
        previous = {}
        if self.manifest_path.exists():
            previous = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        rag = await self._build_lightrag()
        indexed = 0
        manifest: dict[str, str] = {}
        try:
            for document in documents:
                content = document.read_text(encoding="utf-8")
                digest = hashlib.sha256(content.encode()).hexdigest()
                manifest[str(document.relative_to(self.settings.knowledge_dir))] = digest
                if previous.get(str(document.relative_to(self.settings.knowledge_dir))) == digest:
                    continue
                await rag.ainsert(
                    content,
                    ids=f"evidence-{digest[:24]}",
                    file_paths=str(document),
                )
                indexed += 1
        finally:
            await rag.finalize_storages()
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return {"documents": len(documents), "indexed": indexed, "backend": "lightrag"}

    async def retrieve(self, query: str, limit: int = 5) -> RetrievalResult:
        if self.manifest_path.exists() and self.settings.deepseek_api_key is not None:
            try:
                from lightrag import QueryParam

                rag = await self._build_lightrag()
                try:
                    result = await rag.aquery_data(
                        query,
                        QueryParam(
                            mode="mix",
                            top_k=8,
                            chunk_top_k=6,
                            max_total_tokens=5000,
                            enable_rerank=False,
                        ),
                    )
                finally:
                    await rag.finalize_storages()
                chunks = result.get("data", {}).get("chunks", [])
                text = "\n\n".join(
                    str(chunk.get("content", ""))
                    for chunk in chunks
                    if isinstance(chunk, dict)
                )
                evidence = _parse_evidence(text)
                if evidence:
                    return RetrievalResult(
                        evidence=evidence[:limit],
                        backend="lightrag",
                        raw_context=text,
                    )
            except Exception:
                # The response reports the fallback; it never claims LightRAG succeeded.
                pass
        return self._lexical_retrieve(query, limit)

    def _lexical_retrieve(self, query: str, limit: int) -> RetrievalResult:
        parsed: list[Evidence] = []
        for document in self._documents():
            parsed.extend(_parse_evidence(document.read_text(encoding="utf-8")))
        if not parsed:
            return RetrievalResult(evidence=[], backend="no_evidence")
        corpus = [f"{item.title} {item.excerpt}" for item in parsed]
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        matrix = vectorizer.fit_transform(corpus + [query])
        scores = (matrix[:-1] @ matrix[-1].T).toarray().ravel()
        order = np.argsort(scores)[::-1]
        selected = [parsed[index] for index in order[:limit] if scores[index] > 0]
        if not selected:
            selected = parsed[: min(limit, len(parsed))]
        return RetrievalResult(evidence=selected, backend="lexical_fallback")


def lightrag_is_available() -> bool:
    try:
        import lightrag  # noqa: F401

        return True
    except ImportError:
        return False
