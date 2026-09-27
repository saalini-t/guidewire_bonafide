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
    ai_service_url: str = "http://localhost:8100"
    ai_service_timeout_seconds: float = 2.0
    ai_confidence_threshold: float = 0.85
    litigation_confidence_threshold: float = 0.85
    # Comma-separated list of origins the browser-based frontend is served
    # from. Needed because the React app (Vite dev server / built assets)
    # runs on a different origin than this API.
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
