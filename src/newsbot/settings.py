"""Centralized, validated, environment-driven configuration (Phase 1).

Every runtime knob the bot needs — secrets, database URL, AI provider
coordinates, publishing cadence, and decision thresholds — is declared here as
a single, strongly-typed :class:`Settings` object built on
``pydantic-settings``. This module is the *only* place in the codebase that is
allowed to read process environment / ``.env`` values; every other module must
depend on :func:`get_settings` so that:

* configuration is **validated once** (bad values fail fast with a clear
  message rather than surfacing as a cryptic error deep in the pipeline), and
* it is trivially **mockable in tests** (override the environment or the cache).

Design decisions
----------------
* **Enums for closed vocabularies.** ``environment`` and ``log_level`` are
  ``StrEnum`` values, not free strings, so typos are impossible and downstream
  code can branch on them exhaustively.
* **Production is strict, development is forgiving.** In ``production`` the
  required secrets must be present and non-placeholder; in ``development`` the
  bot can still boot with template values so contributors can run tooling and
  tests without real credentials.
* **Derived, typed accessors.** ``admin_user_ids`` is parsed from a
  comma-separated string into a frozen tuple of ``int``; ``min_post_gap`` /
  ``poll_interval`` are exposed as ``timedelta`` helpers so callers never
  re-derive units.
* **Cached accessor.** :func:`get_settings` memoizes the parsed object so the
  environment is read exactly once per process; tests can clear the cache.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "Environment",
    "LogLevel",
    "Settings",
    "get_settings",
    "reload_settings",
]


class Environment(StrEnum):
    """Deployment environment. Governs how strict validation is."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Supported logging verbosity levels (mirrors the stdlib ``logging`` names)."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# Placeholder values shipped in ``.env.example``. If any of these leak into a
# ``production`` deployment, the corresponding secret was never configured, so
# we treat them as "missing" and refuse to start.
_PLACEHOLDER_SECRETS: frozenset[str] = frozenset(
    {
        "",
        "123456:ABC-your-bot-token-here",
        "sk-your-llm-key",
        "your-image-provider-key",
        "@your_channel",
    }
)


class Settings(BaseSettings):
    """Validated application configuration.

    Values are sourced (in precedence order) from real environment variables,
    then a local ``.env`` file, then the field defaults below. Field names map
    to ``UPPER_SNAKE_CASE`` environment variables (case-insensitive).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # ---- Runtime ------------------------------------------------------------
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment; 'production' enforces strict secret checks.",
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Root logging verbosity.",
    )

    # ---- Telegram -----------------------------------------------------------
    telegram_bot_token: SecretStr = Field(
        default=SecretStr(""),
        description="Bot token from @BotFather. Required in production.",
    )
    telegram_channel_id: str = Field(
        default="",
        description="Target channel: '@username' or a numeric '-100...' id.",
    )
    admin_user_ids: str = Field(
        default="",
        description="Comma-separated Telegram user IDs allowed to run admin commands.",
    )

    # ---- Database -----------------------------------------------------------
    database_url: str = Field(
        default="sqlite:///data/newsbot.db",
        description="SQLAlchemy database URL (SQLite in dev, PostgreSQL in prod).",
    )

    # ---- AI / LLM -----------------------------------------------------------
    llm_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key for the OpenAI-compatible LLM provider.",
    )
    llm_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL of the OpenAI-compatible LLM endpoint.",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Model identifier used for importance scoring and rewriting.",
    )

    # ---- Image provider -----------------------------------------------------
    image_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key for the image generation/search provider.",
    )
    image_base_url: str = Field(
        default="",
        description="Base URL of the image provider (optional).",
    )

    # ---- Publishing behavior ------------------------------------------------
    min_post_gap_minutes: int = Field(
        default=20,
        ge=0,
        description="Minimum minutes between two consecutive posts.",
    )
    importance_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Publish gate: only articles scoring >= this are posted.",
    )
    poll_interval_minutes: int = Field(
        default=10,
        ge=1,
        description="How often (minutes) to poll sources for new items.",
    )
    max_posts_per_day: int = Field(
        default=0,
        ge=0,
        description="Safety cap on posts per day (0 = unlimited).",
    )

    # ---- Cost controls ------------------------------------------------------
    max_ai_spend_per_day: float = Field(
        default=0.0,
        ge=0.0,
        description="Approximate max LLM spend per day in currency units (0 = unlimited).",
    )

    # ---- Deduplication thresholds ------------------------------------------
    dedup_simhash_max_distance: int = Field(
        default=3,
        ge=0,
        description="SimHash Hamming distance below which items are near-duplicates.",
    )
    dedup_title_fuzz_min: int = Field(
        default=90,
        ge=0,
        le=100,
        description="rapidfuzz title similarity (0-100) above which items are near-duplicates.",
    )

    # ---- Derived / typed accessors -----------------------------------------
    @property
    def is_production(self) -> bool:
        """True when running under the production environment."""
        return self.environment is Environment.PRODUCTION

    @property
    def admin_ids(self) -> tuple[int, ...]:
        """Admin user IDs parsed into an immutable tuple of integers."""
        return _parse_admin_ids(self.admin_user_ids)

    @property
    def min_post_gap(self) -> timedelta:
        """Minimum spacing between posts as a :class:`~datetime.timedelta`."""
        return timedelta(minutes=self.min_post_gap_minutes)

    @property
    def poll_interval(self) -> timedelta:
        """Source polling cadence as a :class:`~datetime.timedelta`."""
        return timedelta(minutes=self.poll_interval_minutes)

    # ---- Field validators ---------------------------------------------------
    @field_validator("admin_user_ids")
    @classmethod
    def _validate_admin_user_ids(cls, value: str) -> str:
        """Ensure every comma-separated admin id parses as an integer."""
        # Raising here (rather than in the property) gives a fail-fast error at
        # load time, while ``admin_ids`` stays a cheap, side-effect-free getter.
        _parse_admin_ids(value)
        return value

    @model_validator(mode="after")
    def _enforce_production_requirements(self) -> Settings:
        """In production, required secrets must be real (non-placeholder)."""
        if self.environment is not Environment.PRODUCTION:
            return self

        missing: list[str] = []
        if self.telegram_bot_token.get_secret_value() in _PLACEHOLDER_SECRETS:
            missing.append("TELEGRAM_BOT_TOKEN")
        if self.telegram_channel_id in _PLACEHOLDER_SECRETS:
            missing.append("TELEGRAM_CHANNEL_ID")
        if self.llm_api_key.get_secret_value() in _PLACEHOLDER_SECRETS:
            missing.append("LLM_API_KEY")

        if missing:
            raise ValueError(
                "Missing required configuration for production environment: "
                + ", ".join(missing)
                + ". Set these environment variables (see .env.example)."
            )
        return self


def _parse_admin_ids(value: str) -> tuple[int, ...]:
    """Parse a comma-separated string of user IDs into a tuple of ints.

    Empty / whitespace-only input yields an empty tuple. Any non-integer token
    raises :class:`ValueError` with a message naming the offending token.
    """
    ids: list[int] = []
    for raw in value.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError as exc:
            raise ValueError(
                f"ADMIN_USER_IDS must be comma-separated integers; got {token!r}."
            ) from exc
    return tuple(ids)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide, memoized :class:`Settings` instance.

    The environment (and ``.env``) is parsed exactly once; subsequent calls
    return the cached object. Tests that mutate the environment should call
    :func:`reload_settings` to force a fresh read.
    """
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache and rebuild settings from the current environment.

    Primarily a testing/ops affordance (e.g. after changing env vars). Returns
    the freshly built :class:`Settings`.
    """
    get_settings.cache_clear()
    return get_settings()
