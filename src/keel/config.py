import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config. All env vars are prefixed KEEL_. Never hardcode secrets."""

    model_config = SettingsConfigDict(env_prefix="KEEL_", env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    # Secrets & Tokens
    secret_key: str = ""
    api_key_hash_secret: str = ""
    cloudflare_token: str = ""
    webhook_secret: str = ""

    # The APP connects as keel_app: a least-privilege, non-superuser role. This is
    # security-critical — superusers bypass Row-Level Security, which would silently
    # disable tenant isolation (see docker/initdb/01-app-role.sql).
    # Published on 5433 to avoid colliding with a native Postgres on 5432.
    database_url: str = "postgresql+psycopg://keel_app:keel_app@localhost:5433/keel"

    # MIGRATIONS connect as the owner (DDL needs privileges the app must never have).
    migration_database_url: str = "postgresql+psycopg://keel:keel@localhost:5433/keel"
    redis_url: str = "redis://localhost:6379/0"

    # --- evaluation: real model execution (EVAL-02) ---
    # No API key lives here. Vertex uses Application Default Credentials, so the process
    # holds no credential of its own and a leaked config leaks nothing.
    # Falls back to GOOGLE_CLOUD_PROJECT/LOCATION, which is what gcloud already sets.
    vertex_project: str = ""
    vertex_location: str = "us-central1"
    vertex_model: str = "gemini-2.5-flash"

    # Bound every run: an agent that loops forever must cost a bounded amount and fail,
    # not run up a bill. Both are cost controls as much as correctness controls.
    eval_max_turns: int = 6
    eval_timeout_seconds: int = 60

    # HMAC key for signing gate verdicts (Phase 5). Empty = signing disabled. Lets a party
    # that trusts this server and holds the key confirm a verdict was not tampered with.
    # This is symmetric integrity, NOT third-party non-repudiation — see keel/signing.py.
    signing_secret: str = ""

    # --- rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_scans_per_minute: int = 10
    rate_limit_scans_burst: int = 3
    rate_limit_general_per_minute: int = 100
    rate_limit_general_burst: int = 20

    # --- tenant provisioning (S7) ---
    # Shared secret gating the unauthenticated org/onboarding endpoints. When set, callers
    # must present it as `X-Provisioning-Key`. When unset, provisioning is allowed only in
    # dev (see keel/provisioning.py) and DISABLED in production — fail-closed by default.
    onboarding_secret: str = ""
    # Per-IP ceiling on org/onboarding creation. Fail-closed if the limiter store is down.
    onboarding_rate_limit_per_hour: int = 10

    # Comma-separated IPs / CIDRs of proxies whose `X-Forwarded-For` we trust (e.g. the
    # Cloudflare edge ranges or a load balancer). EMPTY BY DEFAULT: with no trusted proxy
    # configured, the client identity is the direct TCP peer (`request.client.host`) and
    # `X-Forwarded-For` is ignored entirely — a caller-controlled header must never set the
    # rate-limit identity. Only when the request's peer matches an entry here is XFF walked
    # (right-to-left, skipping trusted hops) to recover the real client. See keel/net.py.
    trusted_proxies: str = ""


settings = Settings()

# gcloud/Vertex conventions use GOOGLE_CLOUD_*; honour them so a developer whose shell is
# already authenticated does not have to restate the same values as KEEL_*.
if not settings.vertex_project:
    settings.vertex_project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
if os.getenv("GOOGLE_CLOUD_LOCATION"):
    settings.vertex_location = os.environ["GOOGLE_CLOUD_LOCATION"]
