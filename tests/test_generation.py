from __future__ import annotations

from crossborder_recommender.constants import PROVINCE_BY_RAW
from crossborder_recommender.generation import ExplanationGenerator
from crossborder_recommender.parsing import NaturalLanguageParser
from crossborder_recommender.schemas import Evidence
from crossborder_recommender.settings import Settings


class StubClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, **kwargs):
        return self.payload


def _inputs(trained_bundle):
    ranked, _ = trained_bundle.rank("MI", "87", 10)
    ranked = ranked.head(5).copy()
    ranked["province_name"] = ranked["province_code"].map(
        lambda code: PROVINCE_BY_RAW[code].name
    )
    request = NaturalLanguageParser(Settings()).parse(
        "Michigan运输汽车零部件到加拿大，10月份有哪些市场？"
    )
    evidence = [
        Evidence(
            evidence_id="BTS-TABLE-STRUCTURE",
            title="BTS tables",
            excerpt="Table 2 contains state, commodity, and province.",
            source_url="https://example.test/bts",
        )
    ]
    return ranked, request, evidence


def test_generator_accepts_complete_grounded_json(trained_bundle):
    ranked, request, evidence = _inputs(trained_bundle)
    explanations = {
        code: f"Grounded explanation [{evidence[0].evidence_id}]"
        for code in ranked["province_code"]
    }
    generator = ExplanationGenerator(
        Settings(),
        client=StubClient(
            {
                "summary": "Grounded summary [BTS-TABLE-STRUCTURE]",
                "market_explanations": explanations,
            }
        ),
    )

    result = generator.generate(request, ranked, {}, evidence)

    assert result.backend.startswith("deepseek:")
    assert set(result.market_explanations) == set(ranked["province_code"])


def test_generator_rejects_unknown_citations_and_falls_back(trained_bundle):
    ranked, request, evidence = _inputs(trained_bundle)
    explanations = {code: "Unsupported claim [MADE-UP]" for code in ranked["province_code"]}
    generator = ExplanationGenerator(
        Settings(),
        client=StubClient(
            {"summary": "Unsupported [MADE-UP]", "market_explanations": explanations}
        ),
    )

    result = generator.generate(request, ranked, {}, evidence)

    assert result.backend == "deterministic_grounded_fallback"
