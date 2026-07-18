"""AI-Telegram-News-Bot — top-level package.

An autonomous content pipeline that watches trusted gaming-news sources,
decides which stories matter, rewrites them into clean Telegram posts, and
publishes them to a channel 24/7.

The package version is the single source of truth for the application's
semantic version and is surfaced by the CLI (``newsbot --version``) and the
smoke test. Keep it in sync with ``pyproject.toml``'s ``[project].version``.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__: str = "0.1.0"
