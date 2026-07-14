from __future__ import annotations

from crossborder_recommender.settings import Settings


def test_blank_deepseek_key_is_treated_as_unset():
    assert Settings(deepseek_api_key="   ").deepseek_api_key is None


def test_non_blank_deepseek_key_remains_secret():
    settings = Settings(deepseek_api_key="test-only-placeholder")

    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "test-only-placeholder"
