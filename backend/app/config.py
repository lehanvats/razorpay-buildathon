"""Configuration from the environment.

Secrets live in `.env` (git-ignored); `.env.example` documents the shape with
placeholder values only. Nothing in this file may carry a real key, and no
setting here is a compliance knob — the regulatory constants live in
policy/rules.py so that changing one is a visible code change with a
reviewer, not an env var flipped at 2am.
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
"""Anchored to this file's own location, not the process cwd — pydantic-
settings' default `env_file` lookup is cwd-relative, so `.env` silently goes
unread (leaving every setting at its empty/default value, no error raised)
whenever something starts the app or the poller from outside `backend/`."""


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

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

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
    gemini_model: str = "gemini-3.6-flash"
    """gemini-2.0-flash was retired by Google; this is its direct
    replacement (confirmed live against the API, see corrections.md)."""

    # --- Email ---
    resend_api_key: str = ""
    email_from: str = "recoup@example.com"
    email_enabled: bool = False
    """False makes sending a logged no-op — rehearse the batch without
    burning the 100/day free-tier quota. The audit trail is identical."""

    # --- App ---
    cors_origins: list[str] = ["http://localhost:5173"]
    demo_mode: bool = True
    """Enables the /api/demo routes (seeder, customer simulator) and the
    /api/test-payment routes. Must be False in any deployment that could
    touch live keys."""

    frontend_url: str = ""
    """Public origin of the React app, used to build the `callback_url`
    Razorpay redirects a payer to after a Payment Link is paid
    (`integrations.razorpay_client.create_payment_link`). Empty falls back
    to the first CORS origin, which is the same origin in every deployment
    this project has — so nothing needs setting unless the two diverge."""

    @property
    def public_frontend_url(self) -> str:
        """Where a paying customer lands after a Payment Link: explicit
        `frontend_url` if set, else the first CORS origin, trailing slash
        stripped so route paths can be appended verbatim."""
        return (self.frontend_url or self.cors_origins[0]).rstrip("/")


settings = Settings()
