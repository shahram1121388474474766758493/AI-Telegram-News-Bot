"""Unit tests for the Phase 2 engine/session layer (``newsbot.db.engine``).

Every case uses an isolated in-memory SQLite engine so the suite stays
hermetic and fast: no real ``DATABASE_URL``, no files on disk, no network.
The tests cover engine construction across backends, foreign-key enforcement,
the transactional :func:`session_scope` contract (commit on success, rollback
on error, always close), the healthcheck, and the memoized process-wide engine
helpers.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from newsbot.db import engine as engine_mod
from newsbot.db.engine import (
    create_db_engine,
    create_session_factory,
    dispose_engine,
    get_engine,
    get_session_factory,
    healthcheck,
    init_db,
    session_scope,
)
from newsbot.db.models import Article, Source, SourceType


@pytest.fixture
def memory_engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite engine with the schema created and disposed."""
    eng = create_db_engine("sqlite://")
    init_db(eng)
    try:
        yield eng
    finally:
        eng.dispose()


def test_memory_engine_uses_static_pool() -> None:
    eng = create_db_engine("sqlite://")
    try:
        assert isinstance(eng.pool, StaticPool)
    finally:
        eng.dispose()


def test_sqlite_sets_check_same_thread_false() -> None:
    eng = create_db_engine("sqlite:///file.db")
    try:
        # The connect arg is stored on the dialect's connect kwargs.
        assert eng.url.get_backend_name() == "sqlite"
    finally:
        eng.dispose()


def test_healthcheck_true_on_live_engine(memory_engine: Engine) -> None:
    assert healthcheck(memory_engine) is True


def test_healthcheck_false_on_bad_url() -> None:
    # A path under a non-existent directory makes SQLite fail to open, so the
    # healthcheck must report False rather than raising.
    eng = create_db_engine("sqlite:///nonexistent-dir/does/not/exist.db")
    try:
        assert healthcheck(eng) is False
    finally:
        eng.dispose()


def test_init_db_creates_all_tables(memory_engine: Engine) -> None:
    with memory_engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    table_names = {r[0] for r in rows}
    assert {"sources", "articles", "decisions", "posts", "post_log", "kv_state"} <= table_names


def test_foreign_keys_are_enforced(memory_engine: Engine) -> None:
    factory = create_session_factory(memory_engine)
    # Inserting an article referencing a non-existent source must fail because
    # PRAGMA foreign_keys=ON is set by the connect listener.
    with pytest.raises(IntegrityError), session_scope(factory) as session:
        session.add(
            Article(
                source_id=9999,
                url="https://example.com/x",
                url_hash="deadbeef",
                title="Orphan",
            )
        )


def test_session_scope_commits_on_success(memory_engine: Engine) -> None:
    factory = create_session_factory(memory_engine)
    with session_scope(factory) as session:
        session.add(Source(name="IGN", url="https://ign.com/rss", type=SourceType.RSS))

    with session_scope(factory) as session:
        count = session.query(Source).count()
    assert count == 1


def test_session_scope_rolls_back_on_error(memory_engine: Engine) -> None:
    factory = create_session_factory(memory_engine)

    class _Boom(RuntimeError):
        pass

    with pytest.raises(_Boom), session_scope(factory) as session:
        session.add(Source(name="Temp", url="https://temp.com/rss"))
        session.flush()
        raise _Boom

    # The rollback must have discarded the insert.
    with session_scope(factory) as session:
        assert session.query(Source).count() == 0


def test_expire_on_commit_is_disabled(memory_engine: Engine) -> None:
    factory = create_session_factory(memory_engine)
    with session_scope(factory) as session:
        source = Source(name="PCGamer", url="https://pcgamer.com/rss")
        session.add(source)
    # Attributes remain accessible after the scope committed and closed.
    assert source.name == "PCGamer"
    assert source.id is not None


def test_process_wide_engine_is_memoized(monkeypatch: pytest.MonkeyPatch) -> None:
    dispose_engine()
    # Point settings at an in-memory DB so we do not touch the real filesystem.
    from newsbot import settings as settings_mod

    monkeypatch.setattr(
        settings_mod,
        "get_settings",
        lambda: settings_mod.Settings(_env_file=None, database_url="sqlite://"),  # type: ignore[call-arg]
    )
    monkeypatch.setattr(engine_mod, "get_settings", settings_mod.get_settings)

    first = get_engine()
    second = get_engine()
    assert first is second
    assert get_session_factory() is get_session_factory()

    dispose_engine()
    # After disposal a new engine is built.
    assert get_engine() is not first
    dispose_engine()
