"""Runtime settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(
    os.environ.get("CROSSBORDER_PROJECT_ROOT", Path(__file__).resolve().parents[2])
).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    llm_timeout_seconds: float = 60.0

    model_artifact_path: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "artifacts" / "ranker.joblib"
    )
    feature_snapshot_path: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "artifacts" / "feature_snapshot.parquet"
    )
    rag_working_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "rag_storage")
    raw_data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "raw")
    processed_data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "processed")
    knowledge_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "knowledge")

    min_history_months: int = 12
    validation_months: int = 6
    test_months: int = 12
    top_k: int = 5

    @field_validator("deepseek_api_key", mode="before")
    @classmethod
    def blank_api_key_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.model_artifact_path.parent,
            self.feature_snapshot_path.parent,
            self.rag_working_dir,
            self.raw_data_dir,
            self.processed_data_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
