"""Engine & session-factory construction (Phase 2).

This module owns the single point at which a SQLAlchemy :class:`~sqlalchemy.engine.Engine`
is created from the configured ``database_url``. Everything else in the codebase
obtains sessions through the helpers here so that connection configuration,
pooling, and lifecycle live in exactly one place.

Design decisions
----------------
* **Backend-neutral engine tuning.** SQLite needs a couple of pragmatic tweaks
  that PostgreSQL does not (thread sharing for in-memory/file DBs, and a
  ``StaticPool`` for ``:memory:`` so every connection sees the *same* database).
  Those are applied automatically based on the URL, so the same
  :func:`create_db_engine` call works unchanged across backends.
* **Foreign keys on for SQLite.** SQLite ignores ``FOREIGN KEY`` constraints
  unless ``PRAGMA foreign_keys=ON`` is issued per connection. We register an
  event listener so the ``ON DELETE CASCADE`` relationships in
  :mod:`newsbot.db.models` behave the same as on PostgreSQL.
* **Lazy, memoized default engine.** Most of the app wants "the" engine built
  from settings; :func:`get_engine` builds it once and caches it. Tests (and
  scripts that need an isolated database) build their own via
  :func:`create_db_engine` and manage its lifetime explicitly.
* **Context-managed sessions.** :func:`session_scope` yields a session inside a
  ``try/commit/except-rollback/finally-close`` block so callers never leak
  connections or forget to commit — a common source of "database is locked"
  and pool-exhaustion bugs.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from newsbot.db.models import Base
from newsbot.settings import get_settings

__all__ = [
    "create_db_engine",
    "create_session_factory",
    "dispose_engine",
    "get_engine",
    "get_session_factory",
    "healthcheck",
    "init_db",
    "session_scope",
]


def _is_sqlite(url: str) -> bool:
    """True when ``url`` targets a SQLite backend."""
    return url.startswith("sqlite")


def _is_memory_sqlite(url: str) -> bool:
    """True when ``url`` is an in-memory SQLite database."""
    # Covers ``sqlite://`` (no path) and ``sqlite:///:memory:`` variants.
    return _is_sqlite(url) and (":memory:" in url or url in ("sqlite://", "sqlite:///"))


def create_db_engine(database_url: str, *, echo: bool = False, **kwargs: Any) -> Engine:
    """Build a configured SQLAlchemy engine for ``database_url``.

    Applies backend-appropriate defaults so the caller does not need to know
    whether it is talking to SQLite or PostgreSQL:

    * SQLite gets ``check_same_thread=False`` (safe here because sessions are
      short-lived and used from one thread at a time), and in-memory databases
      additionally use a :class:`~sqlalchemy.pool.StaticPool` so all sessions
      share one underlying connection (otherwise each connection would get its
      own empty in-memory DB).
    * A per-connection ``PRAGMA foreign_keys=ON`` listener is attached for
      SQLite so foreign-key constraints (and cascades) are enforced.

    Extra keyword arguments are forwarded verbatim to
    :func:`sqlalchemy.create_engine`, allowing tests/ops to override pooling.
    """
    engine_kwargs: dict[str, Any] = {"echo": echo, "future": True}

    if _is_sqlite(database_url):
        connect_args = dict(kwargs.pop("connect_args", {}))
        connect_args.setdefault("check_same_thread", False)
        engine_kwargs["connect_args"] = connect_args
        if _is_memory_sqlite(database_url):
            # Share a single connection so the schema/data persist across
            # sessions within a process (essential for in-memory test DBs).
            engine_kwargs["poolclass"] = StaticPool

    engine_kwargs.update(kwargs)
    engine = create_engine(database_url, **engine_kwargs)

    if _is_sqlite(database_url):
        _enable_sqlite_foreign_keys(engine)

    return engine


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    """Attach a listener enforcing ``PRAGMA foreign_keys=ON`` on SQLite."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a :class:`~sqlalchemy.orm.sessionmaker` bound to ``engine``.

    Sessions do **not** ``expire_on_commit`` so ORM objects remain usable after
    the surrounding :func:`session_scope` commits — the common pattern of
    "create, commit, then read attributes off the returned object" just works.
    """
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def init_db(engine: Engine) -> None:
    """Create all tables defined on :class:`~newsbot.db.models.Base`.

    Intended for tests and quick local bootstrapping. Production schema
    management goes through Alembic migrations; this is a convenience that
    mirrors ``Base.metadata`` directly.
    """
    Base.metadata.create_all(engine)


def healthcheck(engine: Engine) -> bool:
    """Return ``True`` if a trivial ``SELECT 1`` succeeds on ``engine``.

    Used by ``/health`` reporting and startup checks to confirm the database is
    reachable before the pipeline begins doing real work. Never raises — a
    failure is reported as ``False`` so callers can degrade gracefully.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # health checks must never propagate
        return False


# ---------------------------------------------------------------------------
# Process-wide default engine (built lazily from settings)
# ---------------------------------------------------------------------------
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide engine, building it from settings on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_db_engine(settings.database_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory, building it on first use."""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


def dispose_engine() -> None:
    """Dispose of the process-wide engine and reset the cached factory.

    Releases pooled connections (e.g. on graceful shutdown) and allows a fresh
    engine to be built afterwards — handy in tests that swap ``DATABASE_URL``.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope(
    factory: sessionmaker[Session] | None = None,
) -> Iterator[Session]:
    """Yield a transactional session, committing on success or rolling back.

    Usage::

        with session_scope() as session:
            session.add(obj)
        # committed & closed here

    ``factory`` may be supplied for tests/scripts that use an isolated engine;
    when omitted, the process-wide :func:`get_session_factory` is used.
    """
    session_factory = factory or get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
