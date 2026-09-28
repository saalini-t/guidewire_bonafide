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

    # Image analysis (Phase 2A). "none" (the default) means every
    # /analyze-image request returns 503 — there is no deterministic
    # fallback for pixels the way there is for text, so "no provider
    # configured" must be an honest failure, not a fabricated guess.
    vision_provider: str = "none"
    # A vision-capable model name, e.g. "llava" or "qwen2.5vl" — deliberately
    # separate from ollama_model, which is a text-only model unsuitable for
    # image input.
    vision_model: str = "llava"
    # Vision inference is slower than text; independent of
    # ollama_timeout_seconds so tuning one doesn't silently affect the other.
    vision_timeout_seconds: float = 15.0


settings = Settings()
