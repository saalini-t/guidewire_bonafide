from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/bonafide"
    document_storage_path: str = "../storage/documents"
    max_upload_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    ai_service_url: str = "http://localhost:8100"
    ai_service_timeout_seconds: float = 2.0
    ai_confidence_threshold: float = 0.85
    litigation_confidence_threshold: float = 0.85
    image_analysis_confidence_threshold: float = 0.85
    # Vision inference is slower than text classification — a separate,
    # longer timeout so tuning the fast text path doesn't affect this one
    # (and vice versa; reusing ai_service_timeout_seconds would cause
    # spurious "unavailable" results on a working-but-slower vision call).
    # Must stay comfortably above ai_service's own VISION_TIMEOUT_SECONDS
    # (default 30s) for the same reason ai_service_timeout_seconds must
    # exceed ai_service's OLLAMA_TIMEOUT_SECONDS — verified against a real
    # CPU-only Ollama+llava round trip, which took ~15s once warmed up.
    image_analysis_timeout_seconds: float = 40.0
    # Comma-separated list of origins the browser-based frontend is served
    # from. Needed because the React app (Vite dev server / built assets)
    # runs on a different origin than this API.
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
