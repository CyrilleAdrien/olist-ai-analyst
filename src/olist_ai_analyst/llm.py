"""Chat model factory: the provider is chosen in .env, the rest of the code stays the same."""

from langchain_core.language_models import BaseChatModel

from olist_ai_analyst.config import Settings

EXTRAS = {"groq": "groq", "anthropic": "anthropic", "openai": "openai"}


def get_chat_model(settings: Settings) -> BaseChatModel:
    provider, model = settings.llm_provider, settings.model_name
    temperature = settings.llm_temperature
    try:
        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=model, base_url=settings.ollama_base_url, temperature=temperature
            )
        if provider == "groq":
            from langchain_groq import ChatGroq

            return ChatGroq(model=model, temperature=temperature)
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=model, temperature=temperature)
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=model, temperature=temperature)
    except ImportError as exc:
        raise ImportError(
            f"The {provider} provider needs an extra: uv sync --extra {EXTRAS[provider]}"
        ) from exc
    raise ValueError(f"Unknown LLM provider: {provider}")
