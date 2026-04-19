"""Application settings loaded from environment variables and .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """QRE Backend configuration with sensible defaults."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "QRE Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    CORS_ORIGINS: list[str] = [
        "https://qre.pages.dev",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    CORS_ORIGIN_REGEX: str = r"^https://([a-z0-9-]+\.)?qre\.pages\.dev$"
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_VALIDATE_REQUESTS: int = 500
    RATE_LIMIT_ANALYZE_REQUESTS: int = 200


settings = Settings()
