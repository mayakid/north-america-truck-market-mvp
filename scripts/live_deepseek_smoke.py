from __future__ import annotations

import argparse
import asyncio
import getpass
import json
from pathlib import Path

from crossborder_recommender.parsing import NaturalLanguageParser
from crossborder_recommender.rag import EvidenceRetriever
from crossborder_recommender.service import RecommendationService
from crossborder_recommender.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_QUERY = (
    "我是Michigan的中型承运商，主要运输汽车零部件到加拿大，"
    "10月份有哪些市场值得关注？"
)


async def run_smoke(settings: Settings, *, skip_index: bool) -> dict[str, object]:
    parser = NaturalLanguageParser(settings)
    parsed = await asyncio.to_thread(parser.parse, EXAMPLE_QUERY)
    if parser.last_source != "deepseek_json":
        raise RuntimeError(f"Expected DeepSeek parser, got {parser.last_source}")

    retriever = EvidenceRetriever(settings)
    index_result: dict[str, object] | None = None
    if not skip_index:
        index_result = await retriever.index()

    service = RecommendationService(
        settings,
        parser=parser,
        retriever=retriever,
    )
    response = await service.recommend(query=EXAMPLE_QUERY)
    return {
        "parser_backend": response.methodology["parser"],
        "parsed": parsed.model_dump(mode="json", exclude={"raw_query"}),
        "index": index_result,
        "retrieval_backend": response.retrieval_backend,
        "explanation_backend": response.methodology["explanation"],
        "recommendation_count": len(response.recommendations),
        "top_markets": [
            {
                "rank": item.rank,
                "province": item.province_name,
                "score": round(item.opportunity_score, 4),
            }
            for item in response.recommendations
        ],
        "limitations": response.limitations,
    }


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--artifact",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "SYNTHETIC_ranker.joblib",
    )
    argument_parser.add_argument(
        "--rag-dir",
        type=Path,
        default=PROJECT_ROOT / "rag_storage" / "live-smoke",
    )
    argument_parser.add_argument("--skip-index", action="store_true")
    args = argument_parser.parse_args()

    key = getpass.getpass("DeepSeek API key (hidden, not persisted): ").strip()
    if not key:
        raise SystemExit("No API key supplied")

    settings = Settings(
        deepseek_api_key=key,
        model_artifact_path=args.artifact,
        knowledge_dir=PROJECT_ROOT / "knowledge",
        rag_working_dir=args.rag_dir,
        llm_timeout_seconds=90,
    )
    try:
        result = asyncio.run(run_smoke(settings, skip_index=args.skip_index))
    except Exception as exc:
        sanitized = str(exc).replace(key, "[REDACTED]")
        print(json.dumps({"status": "failed", "error": sanitized}, ensure_ascii=False))
        return 1
    finally:
        key = ""

    print(json.dumps({"status": "passed", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
