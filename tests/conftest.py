"""Shared pytest configuration and fixtures.

Phase 0 keeps this minimal: it only guarantees the ``src`` layout is
importable when the package has not been installed editable (belt-and-braces
alongside ``pyproject.toml``'s ``[tool.pytest.ini_options].pythonpath``).

Later phases grow this file with reusable fixtures (in-memory database,
fake LLM / image / Telegram providers, sample articles) per roadmap Phase 14.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:  # pragma: no cover - environment guard
    sys.path.insert(0, str(_SRC))
