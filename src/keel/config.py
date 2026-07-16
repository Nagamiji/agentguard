from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config. All env vars are prefixed KEEL_. Never hardcode secrets."""

    model_config = SettingsConfigDict(env_prefix="KEEL_", env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    # The APP connects as keel_app: a least-privilege, non-superuser role. This is
    # security-critical — superusers bypass Row-Level Security, which would silently
    # disable tenant isolation (see docker/initdb/01-app-role.sql).
    # Published on 5433 to avoid colliding with a native Postgres on 5432.
    database_url: str = "postgresql+psycopg://keel_app:keel_app@localhost:5433/keel"

    # MIGRATIONS connect as the owner (DDL needs privileges the app must never have).
    migration_database_url: str = "postgresql+psycopg://keel:keel@localhost:5433/keel"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
