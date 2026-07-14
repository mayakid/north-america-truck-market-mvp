from __future__ import annotations

from crossborder_recommender import api
from crossborder_recommender.settings import Settings


class ReadyService:
    bundle = object()


class BrokenService:
    @property
    def bundle(self):
        raise ValueError("incompatible artifact")


def test_health_requires_a_loadable_model(monkeypatch, tmp_path):
    settings = Settings(
        model_artifact_path=tmp_path / "ranker.joblib",
        feature_snapshot_path=tmp_path / "feature_snapshot.parquet",
    )
    settings.model_artifact_path.touch()
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "get_service", lambda: BrokenService())

    response = api.health()

    assert response.status == "degraded"
    assert response.model_ready is False


def test_health_reports_ready_after_model_load(monkeypatch, tmp_path):
    settings = Settings(
        model_artifact_path=tmp_path / "ranker.joblib",
        feature_snapshot_path=tmp_path / "feature_snapshot.parquet",
    )
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "get_service", lambda: ReadyService())

    response = api.health()

    assert response.status == "ok"
    assert response.model_ready is True
