from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mis Eventos API"
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mis_eventos"
    )
    test_database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mis_eventos_test"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    media_root: str = "/app/media"
    jwt_secret_key: str = "change-me-in-production-min-32-chars"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
