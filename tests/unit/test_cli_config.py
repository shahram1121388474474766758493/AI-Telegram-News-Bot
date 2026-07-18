"""Tests for the Phase 1 ``newsbot config`` CLI command.

Covers the success path (validates config, prints a masked JSON summary,
exits 0), the secret-masking guarantee, and the failure path (a broken
configuration is reported cleanly on stderr with a non-zero exit code).
"""

from __future__ import annotations

import json

import pytest

from newsbot.main import build_parser, main
from newsbot.settings import get_settings, reload_settings


def test_config_command_prints_masked_json(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "a-real-looking-token")
    monkeypatch.setenv("ADMIN_USER_IDS", "42,43")
    reload_settings()

    rc = main(["config"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    # Secrets are masked, never echoed verbatim.
    assert payload["telegram_bot_token"] == "***set***"
    assert "a-real-looking-token" not in json.dumps(payload)
    # Derived values are surfaced for the operator.
    assert payload["admin_user_ids"] == [42, 43]
    assert payload["environment"] == "development"

    reload_settings()  # restore cache to ambient env for other tests


def test_config_command_reports_validation_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Production without real secrets must fail validation and surface cleanly.
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHANNEL_ID", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    # Clear the memoized settings so `newsbot config` re-reads this environment.
    get_settings.cache_clear()

    rc = main(["config"])
    assert rc == 2

    captured = capsys.readouterr()
    assert "configuration error" in captured.err
    assert captured.out == ""

    # Only clear the cache here; monkeypatch restores the environment at
    # teardown, so we must NOT rebuild settings while ENVIRONMENT=production is
    # still active (that itself would raise). The next reader rebuilds lazily.
    get_settings.cache_clear()


def test_parser_registers_config_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["config"])
    assert args.command == "config"
