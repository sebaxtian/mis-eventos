from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_SECRET_PLACEHOLDER = "change-me-in-production-min-32-chars"


class Settings(BaseSettings):
    app_name: str = "Mis Eventos API"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mis_eventos"
    )
    test_database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/mis_eventos_test"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    media_root: str = "/app/media"
    jwt_secret_key: str = Field(default=JWT_SECRET_PLACEHOLDER, repr=False)
    jwt_expire_minutes: int = 480
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = Field(default=None, repr=False)
    bootstrap_admin_full_name: str = "Administrador"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_jwt_secret_length(cls, value: str) -> str:
        if len(value.strip()) < 32:
            raise ValueError(
                "La clave JWT debe tener al menos 32 caracteres"
            )
        return value

    @model_validator(mode="after")
    def _validate_production_jwt_secret(self) -> "Settings":
        if self.app_env.strip().lower() == "production":
            if (
                len(self.jwt_secret_key.strip()) < 32
                or self.jwt_secret_key == JWT_SECRET_PLACEHOLDER
            ):
                raise ValueError(
                    "En producción debes configurar una clave JWT segura de al menos 32 caracteres"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
