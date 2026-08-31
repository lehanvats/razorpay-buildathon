"""Configuration from the environment.

Secrets live in `.env` (git-ignored); `.env.example` documents the shape with
placeholder values only. Nothing in this file may carry a real key, and no
setting here is a compliance knob — the regulatory constants live in
policy/rules.py so that changing one is a visible code change with a
reviewer, not an env var flipped at 2am.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings, loaded once at import."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg://localhost/recoup"
    """Neon Postgres connection string. Use the pooled endpoint."""

    # --- Razorpay (test mode only) ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    """Used for HMAC-SHA256 signature verification. Distinct from the API
    secret — Razorpay issues it separately when the webhook is configured."""

    # --- LLM ---
    llm_provider: str = "anthropic"
    """anthropic | gemini. Gemini's free tier is the Rs 0 fallback."""
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
