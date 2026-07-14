"""Export a path-sanitized real model artifact for the public Docker image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from crossborder_recommender.ranking import RankerBundle

PUBLIC_PATHS = {
    "history_path": "data/processed/table2_history.parquet",
    "port_history_path": "data/processed/table1_ports.parquet",
    "source_manifest_path": "data/raw/manifest.sha256",
}
FORBIDDEN_METADATA_FRAGMENTS = ("/Users/", "\\Users\\", "DEEPSEEK_API_KEY", "sk-")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_metadata(metadata: dict[str, Any]) -> None:
    provenance = metadata.get("data_provenance")
    if isinstance(provenance, dict):
        for key, public_path in PUBLIC_PATHS.items():
            if key in provenance and provenance[key] is not None:
                provenance[key] = public_path
    metadata["distribution"] = {
        "purpose": "public Docker portfolio demo",
        "source": "BTS public TransBorder Freight Data",
        "sanitized": True,
    }


def validate_metadata(metadata: dict[str, Any]) -> None:
    serialized = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    found = [fragment for fragment in FORBIDDEN_METADATA_FRAGMENTS if fragment in serialized]
    if found:
        raise ValueError(f"Public artifact metadata contains forbidden fragments: {found}")
    if metadata.get("synthetic_data") is not False:
        raise ValueError("Public Docker artifact must be the real BTS model, not synthetic data")
    if not metadata.get("acceptance_gate", {}).get("passed", False):
        raise ValueError("Public Docker artifact must pass the recorded acceptance gate")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("artifacts/ranker.joblib"))
    parser.add_argument("--output", type=Path, default=Path("docker/model/ranker.joblib"))
    args = parser.parse_args()

    bundle = RankerBundle.load(args.source)
    sanitize_metadata(bundle.metadata)
    validate_metadata(bundle.metadata)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    bundle.save(args.output)

    exported = RankerBundle.load(args.output)
    validate_metadata(exported.metadata)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "bytes": args.output.stat().st_size,
                "sha256": sha256(args.output),
                "data_cutoff": str(exported.data_cutoff.date()),
                "synthetic_data": exported.metadata.get("synthetic_data"),
                "acceptance_gate": exported.metadata.get("acceptance_gate"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
