from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config. All env vars are prefixed KEEL_. Never hardcode secrets."""

    model_config = SettingsConfigDict(env_prefix="KEEL_", env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://keel:keel@localhost:5432/keel"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
