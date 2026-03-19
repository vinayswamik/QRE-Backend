from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "QRE Backend"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # CORS – include both hostname forms so Chrome works regardless of whether
    # the user opens localhost or 127.0.0.1, and include the Vite preview port.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
