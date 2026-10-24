"""Settings read from the environment and the .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["ollama", "groq", "anthropic", "openai"]

DEFAULT_MODELS: dict[str, str] = {
    "ollama": "qwen2.5-coder:7b",
    "groq": "llama-3.3-70b-versatile",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "olist"
    agent_db_user: str = "olist_agent"
    agent_db_password: SecretStr = SecretStr("")
    # Only the schema built by dbt for BI tools is exposed to the agent
    agent_db_schema: str = "marts"
    statement_timeout_ms: int = 10_000

    llm_provider: Provider = "ollama"
    llm_model: str = ""
    llm_temperature: float = 0.0
    ollama_base_url: str = "http://localhost:11434"

    @property
    def model_name(self) -> str:
        """The configured model, or the provider's default when LLM_MODEL is empty."""
        if self.llm_model:
            return self.llm_model
        if self.llm_provider in DEFAULT_MODELS:
            return DEFAULT_MODELS[self.llm_provider]
        raise ValueError(f"Set LLM_MODEL in .env to use the {self.llm_provider} provider")


@lru_cache
def get_settings() -> Settings:
    return Settings()
