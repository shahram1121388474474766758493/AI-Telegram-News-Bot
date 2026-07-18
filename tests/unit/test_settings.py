"""Unit tests for the Phase 1 configuration layer (``newsbot.settings``).

These tests are hermetic: every case builds :class:`Settings` from an
explicitly controlled environment and disables ``.env`` file discovery via
``_env_file=None`` so a contributor's local ``.env`` can never influence the
result. Both the happy path (defaults, parsing, derived accessors) and the
failure modes (bad admin ids, missing production secrets, out-of-range
thresholds) are asserted.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from newsbot.settings import (
    Environment,
    LogLevel,
    Settings,
    get_settings,
    reload_settings,
)


def _make(**overrides: object) -> Settings:
    """Build Settings from an isolated environment (no real ``.env``)."""
    # ``_env_file=None`` disables dotenv discovery; kwargs override fields.
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_defaults_are_sensible() -> None:
    settings = _make()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO
    assert settings.database_url == "sqlite:///data/newsbot.db"
    assert settings.min_post_gap_minutes == 20
    assert settings.importance_threshold == pytest.approx(0.6)
    assert settings.poll_interval_minutes == 10
    assert settings.max_posts_per_day == 0
    assert settings.is_production is False


def test_derived_accessors() -> None:
    settings = _make(min_post_gap_minutes=45, poll_interval_minutes=5)

    assert settings.min_post_gap == timedelta(minutes=45)
    assert settings.poll_interval == timedelta(minutes=5)


def test_secrets_are_masked_in_repr() -> None:
    settings = _make(telegram_bot_token="super-secret-token")

    # SecretStr never leaks its value through str()/repr().
    assert "super-secret-token" not in repr(settings)
    assert settings.telegram_bot_token.get_secret_value() == "super-secret-token"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ()),
        ("   ", ()),
        ("111", (111,)),
        ("111,222,333", (111, 222, 333)),
        (" 111 , 222 ,, 333 ", (111, 222, 333)),
    ],
)
def test_admin_ids_parsing(raw: str, expected: tuple[int, ...]) -> None:
    assert _make(admin_user_ids=raw).admin_ids == expected


def test_admin_ids_reject_non_integer() -> None:
    with pytest.raises(ValidationError, match="comma-separated integers"):
        _make(admin_user_ids="111,notanumber")


def test_importance_threshold_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        _make(importance_threshold=1.5)
    with pytest.raises(ValidationError):
        _make(importance_threshold=-0.1)


def test_negative_gap_rejected() -> None:
    with pytest.raises(ValidationError):
        _make(min_post_gap_minutes=-1)


def test_environment_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("MIN_POST_GAP_MINUTES", "33")
    monkeypatch.setenv("ADMIN_USER_IDS", "7,8,9")

    settings = _make()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.min_post_gap_minutes == 33
    assert settings.admin_ids == (7, 8, 9)


def test_production_requires_real_secrets() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _make(environment="production")

    message = str(excinfo.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "LLM_API_KEY" in message
    assert "TELEGRAM_CHANNEL_ID" in message


def test_production_with_placeholder_secrets_rejected() -> None:
    # The exact placeholder shipped in .env.example must be treated as missing.
    with pytest.raises(ValidationError, match="TELEGRAM_BOT_TOKEN"):
        _make(
            environment="production",
            telegram_bot_token="123456:ABC-your-bot-token-here",
            telegram_channel_id="@real_channel",
            llm_api_key="sk-real-key",
        )


def test_production_with_real_secrets_ok() -> None:
    settings = _make(
        environment="production",
        telegram_bot_token="1234:REALTOKEN",
        telegram_channel_id="@my_channel",
        llm_api_key="sk-real-key",
    )

    assert settings.is_production is True
    assert settings.telegram_channel_id == "@my_channel"


def test_settings_is_frozen() -> None:
    settings = _make()
    with pytest.raises(ValidationError):
        settings.min_post_gap_minutes = 99  # type: ignore[misc]


def test_get_settings_is_cached() -> None:
    reload_settings()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_reload_settings_rebuilds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIN_POST_GAP_MINUTES", "12")
    first = reload_settings()
    assert first.min_post_gap_minutes == 12

    monkeypatch.setenv("MIN_POST_GAP_MINUTES", "34")
    # Without reload the cached value persists...
    assert get_settings().min_post_gap_minutes == 12
    # ...and reload picks up the new environment.
    assert reload_settings().min_post_gap_minutes == 34
