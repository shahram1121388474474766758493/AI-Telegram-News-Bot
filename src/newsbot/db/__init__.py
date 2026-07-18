"""Persistence layer (Phase 2).

A thin, provider-agnostic database package built on SQLAlchemy 2.x:

* :mod:`newsbot.db.models` — the ORM table definitions (the schema).
* :mod:`newsbot.db.engine` — engine/session-factory construction from the
  configured ``database_url`` plus a lightweight health check.
* :mod:`newsbot.db.repositories` — the data-access layer; every query the
  pipeline needs lives behind a small, testable repository API so the rest of
  the codebase never writes raw SQL or manages sessions directly.

The same code runs unchanged on SQLite (development/tests) and PostgreSQL
(production); only ``DATABASE_URL`` differs.
"""

from __future__ import annotations

__all__: list[str] = []
