"""Configuration from the environment.

Secrets live in `.env` (git-ignored); `.env.example` documents the shape with
placeholder values only. Nothing in this file may carry a real key, and no
setting here is a compliance knob — the regulatory constants live in
policy/rules.py so that changing one is a visible code change with a
reviewer, not an env var flipped at 2am.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _with_psycopg_driver(url: str) -> str:
    """Force the psycopg 3 driver onto a bare Postgres URL.

    Neon (like most managed providers) hands out connection strings scheme'd
    `postgresql://` or `postgres://`. SQLAlchemy reads that as "use the
    default driver", which is psycopg2 — a package this project does not
    install. The failure is an ImportError at engine construction, far from
    the pasted string that caused it.

    Normalising here means a URL can be pasted from the Neon dashboard
    verbatim. An already-qualified URL (`+psycopg`, `+asyncpg`) is untouched.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    """Environment-backed settings, loaded once at import."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg://localhost/recoup"
    """Neon Postgres connection string. Use the pooled endpoint (`-pooler` in
    the host): request handlers are short-lived and want PgBouncer in front."""

    database_url_unpooled: str = ""
    """Neon's direct endpoint, used for migrations. Alembic holds
    session-scoped state — an advisory lock, and DDL spanning several
    statements — that transaction-mode pooling does not preserve, and the
    resulting failures are intermittent rather than clean. Empty falls back
    to `database_url`, which is right for a plain Postgres with no pooler."""

    @field_validator("database_url", "database_url_unpooled")
    @classmethod
    def _normalise_driver(cls, v: str) -> str:
        return _with_psycopg_driver(v)

    @property
    def migration_database_url(self) -> str:
        """The URL Alembic should use: direct if configured, else pooled."""
        return self.database_url_unpooled or self.database_url

    # --- Razorpay (test mode only) ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    """Used for HMAC-SHA256 signature verification. Distinct from the API
    secret — Razorpay issues it separately when the webhook is configured."""

    # --- LLM ---
    llm_provider: str = "groq"
    """groq | anthropic | gemini. Groq (openai/gpt-oss-120b) is primary;
    Gemini's free tier is the Rs 0 fallback."""
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # --- Email ---
    resend_api_key: str = ""
    email_from: str = "recoup@example.com"
    email_enabled: bool = False
    """False makes sending a logged no-op — rehearse the batch without
    burning the 100/day free-tier quota. The audit trail is identical."""

    # --- App ---
    cors_origins: list[str] = ["http://localhost:5173"]
    demo_mode: bool = True
    """Enables the /api/demo routes (seeder, customer simulator). Must be
    False in any deployment that could touch live keys."""


settings = Settings()
