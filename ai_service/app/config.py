from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # None/empty disables Ollama entirely — DeterministicProvider is used
    # for every request. Never hardcode a model that may not exist on the
    # host machine; this is read from the environment only.
    ollama_base_url: str | None = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    # Must stay comfortably below the CORE backend's timeout to THIS
    # service (AI_SERVICE_TIMEOUT_SECONDS, default 2.0s) — otherwise, when
    # Ollama is configured but unreachable, the core gives up on us before
    # we finish falling back to the deterministic provider, and a call that
    # would have succeeded gets treated as "AI unavailable" instead.
    ollama_timeout_seconds: float = 1.0


settings = Settings()
