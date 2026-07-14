from __future__ import annotations

from pathlib import Path

import pytest

from crossborder_recommender.features import build_training_frame
from crossborder_recommender.ranking import RankerBundle, train_ranker
from crossborder_recommender.synthetic import make_synthetic_history


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def synthetic_history():
    return make_synthetic_history(periods=48)


@pytest.fixture(scope="session")
def feature_frame(synthetic_history):
    return build_training_frame(synthetic_history)


@pytest.fixture(scope="session")
def trained_bundle(feature_frame, synthetic_history) -> RankerBundle:
    bundle, _ = train_ranker(
        feature_frame,
        synthetic_history,
        validation_months=6,
        test_months=6,
        synthetic_data=True,
    )
    return bundle
