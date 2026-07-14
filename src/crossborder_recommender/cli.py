"""Project command-line interface."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from .data.bts import BTSDownloader, load_and_normalize_table1, load_and_normalize_table2
from .features import build_training_frame
from .parsing import NaturalLanguageParser
from .rag import EvidenceRetriever
from .ranking import RankerBundle, train_ranker
from .service import RecommendationService
from .settings import get_settings
from .synthetic import make_synthetic_history

app = typer.Typer(no_args_is_help=True, help="Canada cross-border opportunity recommender")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@app.command("download")
def download(
    start: Annotated[str, typer.Option(help="First month, YYYY-MM")],
    end: Annotated[str, typer.Option(help="Last month, YYYY-MM")],
    overwrite: Annotated[bool, typer.Option()] = False,
) -> None:
    settings = get_settings()
    paths = BTSDownloader(settings.raw_data_dir).download_range(start, end, overwrite=overwrite)
    typer.echo(json.dumps([str(path) for path in paths], indent=2))


@app.command("prepare")
def prepare(
    input_dir: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("data/raw"),
    history_output: Annotated[Path, typer.Option()] = Path("data/processed/table2_history.parquet"),
    ports_output: Annotated[Path, typer.Option()] = Path("data/processed/table1_ports.parquet"),
) -> None:
    paths = sorted(input_dir.rglob("*.zip"))
    if not paths:
        raise typer.BadParameter(f"No BTS ZIP files found under {input_dir}")
    history = load_and_normalize_table2(paths)
    ports = load_and_normalize_table1(paths)
    history_output.parent.mkdir(parents=True, exist_ok=True)
    ports_output.parent.mkdir(parents=True, exist_ok=True)
    history.to_parquet(history_output, index=False)
    ports.to_parquet(ports_output, index=False)
    typer.echo(f"history_rows={len(history)} ports_rows={len(ports)}")


@app.command("make-demo-data")
def make_demo_data(
    output: Annotated[Path, typer.Option()] = Path("data/processed/SYNTHETIC_history.parquet"),
    periods: Annotated[int, typer.Option(min=36, max=240)] = 60,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = make_synthetic_history(periods=periods)
    frame.to_parquet(output, index=False)
    typer.echo(f"WROTE SYNTHETIC DATA ONLY: {output} ({len(frame)} rows)")


@app.command("train")
def train(
    history_path: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    port_history_path: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    output: Annotated[Path, typer.Option()] = Path("artifacts/ranker.joblib"),
    synthetic: Annotated[
        bool, typer.Option(help="Required flag for synthetic demo inputs")
    ] = False,
) -> None:
    settings = get_settings()
    history = pd.read_parquet(history_path)
    ports = pd.read_parquet(port_history_path) if port_history_path else None
    observed_months = pd.DatetimeIndex(
        sorted(pd.to_datetime(history["date"], errors="coerce").dropna().unique())
    )
    required_months = (
        settings.min_history_months
        + settings.validation_months
        + settings.test_months
        + 2
    )
    if len(observed_months) < required_months:
        raise typer.BadParameter(
            f"Training history has {len(observed_months)} monthly periods; at least "
            f"{required_months} are required for {settings.min_history_months} months of "
            f"feature history, 2 training target months, {settings.validation_months} "
            f"validation months, and {settings.test_months} test months."
        )
    expected_months = pd.date_range(observed_months.min(), observed_months.max(), freq="MS")
    missing_months = expected_months.difference(observed_months)
    if len(missing_months):
        missing = ", ".join(month.strftime("%Y-%m") for month in missing_months)
        raise typer.BadParameter(f"Training history has missing monthly periods: {missing}")
    features = build_training_frame(history, min_history_months=settings.min_history_months)
    bundle, test_scored = train_ranker(
        features,
        history,
        port_history=ports,
        validation_months=settings.validation_months,
        test_months=settings.test_months,
        synthetic_data=synthetic,
    )
    provenance = {
        "history_path": str(history_path.resolve()),
        "history_sha256": _sha256_file(history_path),
        "port_history_path": (
            str(port_history_path.resolve()) if port_history_path is not None else None
        ),
        "port_history_sha256": (
            _sha256_file(port_history_path) if port_history_path is not None else None
        ),
    }
    source_manifest = settings.raw_data_dir / "manifest.sha256"
    if source_manifest.exists():
        provenance["source_manifest_path"] = str(source_manifest.resolve())
        provenance["source_manifest_sha256"] = _sha256_file(source_manifest)
    bundle.metadata["data_provenance"] = provenance
    bundle.save(output)
    snapshot = output.parent / "test_predictions.parquet"
    report_path = output.parent / "evaluation_report.json"
    test_scored.to_parquet(snapshot, index=False)
    report = {
        **bundle.metadata["evaluation"],
        "acceptance_gate": bundle.metadata["acceptance_gate"],
        "data_provenance": provenance,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {
        "artifact": str(output),
        "test_predictions": str(snapshot),
        "evaluation_report": str(report_path),
        **bundle.metadata,
    }
    typer.echo(json.dumps(summary, indent=2))


@app.command("index-knowledge")
def index_knowledge() -> None:
    result = asyncio.run(EvidenceRetriever(get_settings()).index())
    typer.echo(json.dumps(result, indent=2))


@app.command("parse")
def parse(query: Annotated[str, typer.Argument()]) -> None:
    parser = NaturalLanguageParser(get_settings())
    result = parser.parse(query)
    typer.echo(result.model_dump_json(indent=2))


@app.command("recommend")
def recommend(query: Annotated[str, typer.Argument()]) -> None:
    result = asyncio.run(RecommendationService(get_settings()).recommend(query=query))
    typer.echo(result.model_dump_json(indent=2))


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
) -> None:
    import uvicorn

    uvicorn.run("crossborder_recommender.api:app", host=host, port=port, reload=False)


@app.command("artifact-info")
def artifact_info(path: Annotated[Path, typer.Option()] = Path("artifacts/ranker.joblib")) -> None:
    bundle = RankerBundle.load(path)
    typer.echo(json.dumps({"version": bundle.artifact_version, **bundle.metadata}, indent=2))


if __name__ == "__main__":
    app()
