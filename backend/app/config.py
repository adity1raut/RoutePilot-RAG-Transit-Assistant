"""Application settings, loaded from environment variables or backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # LLM: "auto" picks Claude, Gemini or OpenAI depending on which key is set (in that order);
    # "none" disables the LLM and returns the retrieved information directly.
    llm_provider: str = "auto"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "medium"  # low | medium | high | xhigh | max
    google_api_key: str | None = Field(default=None, validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"))
    openai_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"  # alias that always points to the current Gemini Flash model
    google_vertexai: bool = False  # true for Vertex AI "express mode" API keys
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None  # any OpenAI-compatible API, e.g. Groq or OpenRouter
    llm_temperature: float = 0.2

    # Retrieval
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    collection_name: str = "transport_docs"
    chunk_size: int = 500
    chunk_overlap: int = 80
    top_k: int = 5

    # Paths
    data_dir: Path = BACKEND_DIR / "data" / "raw"
    chroma_dir: Path = BACKEND_DIR / "data" / "chroma"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def resolved_provider(self) -> str:
        provider = self.llm_provider.lower()
        if provider == "claude":
            return "anthropic"
        if provider == "auto":
            if self.anthropic_api_key:
                return "anthropic"
            if self.google_api_key:
                return "gemini"
            if self.openai_api_key:
                return "openai"
            return "none"
        return provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
