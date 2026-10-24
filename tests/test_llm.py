from langchain_ollama import ChatOllama

from olist_ai_analyst.config import Settings
from olist_ai_analyst.llm import get_chat_model


def test_ollama_model_uses_settings():
    settings = Settings(_env_file=None, ollama_base_url="http://ollama:11434")
    model = get_chat_model(settings)
    assert isinstance(model, ChatOllama)
    assert model.model == "qwen2.5-coder:7b"
    assert model.base_url == "http://ollama:11434"
    assert model.temperature == 0.0
