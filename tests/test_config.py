import pytest

from olist_ai_analyst.config import Settings


def test_defaults_point_to_local_ollama_and_marts():
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "ollama"
    assert settings.model_name == "qwen2.5-coder:7b"
    assert settings.agent_db_schema == "marts"


def test_explicit_model_wins_over_default():
    settings = Settings(_env_file=None, llm_provider="groq", llm_model="llama-3.1-8b-instant")
    assert settings.model_name == "llama-3.1-8b-instant"


def test_paid_provider_needs_an_explicit_model():
    settings = Settings(_env_file=None, llm_provider="anthropic")
    with pytest.raises(ValueError, match="LLM_MODEL"):
        _ = settings.model_name


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_provider="mistral")
