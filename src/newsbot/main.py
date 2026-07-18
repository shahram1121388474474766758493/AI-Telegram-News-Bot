"""Command-line entrypoint and process launcher for AI-Telegram-News-Bot.

Phase 0 ships a *stub* CLI: it parses arguments, reports the version, and
recognizes the process commands that later phases will implement
(``pipeline``, ``publisher``, ``admin``, ``all``). Each command currently
prints a "not yet implemented" notice and exits cleanly, so the executable
contract (``python -m newsbot`` / the ``newsbot`` console script) is stable
from the very first phase and only its internals grow over time.

Design choices:
* ``argparse`` (stdlib) — zero runtime dependency for the Phase 0 stub.
* A subcommand table maps names to handlers, so wiring real workers later is
  a one-line change per command (Phase 11).
* ``main()`` returns an ``int`` exit code and never raises for expected user
  errors, which keeps it testable and shell-friendly.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from newsbot import __version__

PROGRAM_NAME = "newsbot"

# Process commands the finished bot will expose (see roadmap Phase 11).
# Mapped to a short human description; handlers are wired in later phases.
COMMANDS: dict[str, str] = {
    "pipeline": "Run the fetch -> extract -> dedup -> score -> rewrite -> image -> enqueue pipeline.",
    "publisher": "Drain the post queue and publish to Telegram, respecting the min-gap.",
    "admin": "Long-poll Telegram for admin commands (/status, /pause, ...).",
    "all": "Launch every process together (pipeline + publisher + admin + scheduler).",
}


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser and its subcommands."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description="AI-powered Telegram gaming-news bot.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{PROGRAM_NAME} {__version__}",
        help="Show the program version and exit.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="{" + ",".join(COMMANDS) + "}",
        help="Process to run.",
    )
    for name, description in COMMANDS.items():
        subparsers.add_parser(name, help=description, description=description)

    return parser


def _run_command(command: str) -> int:
    """Dispatch a recognized process command.

    In Phase 0 every command is a stub that reports its intent. Later phases
    replace the body of this function (or register real handlers) without
    changing the CLI surface.
    """
    description = COMMANDS[command]
    print(f"[{PROGRAM_NAME}] '{command}' — {description}")
    print(f"[{PROGRAM_NAME}] not yet implemented (Phase 0 stub); coming in a later phase.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Program entrypoint.

    Args:
        argv: Optional argument vector (excluding the program name). Defaults
            to ``sys.argv[1:]`` when ``None``, which makes ``main`` easy to
            drive from tests.

    Returns:
        A process exit code (``0`` on success).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # No subcommand given: show help and signal misuse.
        parser.print_help()
        return 1

    return _run_command(args.command)


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    sys.exit(main())
