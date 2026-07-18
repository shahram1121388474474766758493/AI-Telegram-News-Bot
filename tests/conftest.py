"""Shared pytest configuration and fixtures.

Phase 0 guaranteed the ``src`` layout is importable; Phase 2 adds the first
reusable database fixtures — an isolated in-memory SQLite engine and a
transactional session — so every DB/repository test runs hermetically (no
files on disk, no real ``DATABASE_URL``, no network). Later phases grow this
file with fake LLM / image / Telegram providers and sample articles per
roadmap Phase 14.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:  # pragma: no cover - environment guard
    sys.path.insert(0, str(_SRC))

# Imported after the path shim above so the package resolves in either layout.
from sqlalchemy import Engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from newsbot.db.engine import (  # noqa: E402
    create_db_engine,
    create_session_factory,
    init_db,
)


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite engine with the full schema, disposed on teardown."""
    engine = create_db_engine("sqlite://")
    init_db(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the isolated in-memory engine."""
    return create_session_factory(db_engine)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A single session with an outer transaction rolled back on teardown.

    Tests can add/flush/query freely; nothing persists beyond the test.
    """
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
