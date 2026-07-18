"""Phase 0 smoke tests.

These prove the project skeleton is sound before any feature code exists:
the package imports, exposes a semantic version, and the CLI entrypoint runs
for the recognized process commands and for ``--version``.
"""

from __future__ import annotations

import re

import pytest

import newsbot
from newsbot.main import COMMANDS, build_parser, main


def test_package_imports_and_exposes_version() -> None:
    """The package imports and advertises a SemVer-shaped version string."""
    assert isinstance(newsbot.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", newsbot.__version__), newsbot.__version__


def test_version_matches_pyproject() -> None:
    """The runtime version stays in lockstep with pyproject.toml."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["version"] == newsbot.__version__


def test_cli_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """``newsbot --version`` prints the version and exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert newsbot.__version__ in captured.out


def test_cli_no_command_returns_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    """Running with no subcommand shows help and signals misuse (rc=1)."""
    rc = main([])
    assert rc == 1
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_cli_stub_commands_run_cleanly(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Every recognized process command runs as a clean Phase 0 stub (rc=0)."""
    rc = main([command])
    assert rc == 0
    assert command in capsys.readouterr().out


def test_parser_registers_all_commands() -> None:
    """The argument parser exposes exactly the documented process commands."""
    parser = build_parser()
    # Parsing each command name must succeed and round-trip the choice.
    for command in COMMANDS:
        args = parser.parse_args([command])
        assert args.command == command
