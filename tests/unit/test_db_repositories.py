"""Unit tests for the Phase 2 data-access layer (``newsbot.db.repositories``).

The tests run against the shared in-memory ``db_session`` fixture and assert
the behaviours the pipeline depends on: idempotent article ingestion, correct
queue selection/ordering, min-gap timestamp lookups, publish idempotency,
poll-due source selection, and the boolean KV flag helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from newsbot.db.models import ArticleStatus, PostStatus, SourceType, utcnow
from newsbot.db.repositories import (
    ArticleRepository,
    DecisionRepository,
    KVStateRepository,
    PostLogRepository,
    PostRepository,
    SourceRepository,
)


def _make_source(session: Session, *, url: str = "https://ign.com/rss", name: str = "IGN") -> int:
    src = SourceRepository(session).add(name=name, url=url, type=SourceType.RSS)
    return src.id


# --------------------------------------------------------------------------- #
# UtcDateTime column type                                                     #
# --------------------------------------------------------------------------- #
def test_utcdatetime_normalizes_naive_input_to_utc(db_session: Session) -> None:
    """A naive datetime written to a timestamp column reads back as aware UTC."""
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = PostRepository(db_session)
    post = repo.enqueue(article_id=art.id, text="x")
    naive = datetime(2025, 6, 1, 12, 0, 0)  # intentionally naive
    repo.mark_published(post.id, when=naive)
    # Force a reload from the DB so the value passes through UtcDateTime's
    # result processing (rather than reading back the in-memory assignment).
    db_session.expire_all()
    stored = repo.get_by_id(post.id)
    assert stored is not None
    assert stored.published_at is not None
    assert stored.published_at.tzinfo is not None
    assert stored.published_at == naive.replace(tzinfo=UTC)


def test_utcdatetime_converts_aware_input_to_utc(db_session: Session) -> None:
    """A non-UTC aware datetime is converted to the equivalent UTC instant."""
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = PostRepository(db_session)
    post = repo.enqueue(article_id=art.id, text="x")
    plus_two = timezone(timedelta(hours=2))
    aware = datetime(2025, 6, 1, 14, 0, 0, tzinfo=plus_two)  # == 12:00 UTC
    repo.mark_published(post.id, when=aware)
    db_session.expire_all()
    stored = repo.get_by_id(post.id)
    assert stored is not None
    assert stored.published_at == datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# SourceRepository                                                            #
# --------------------------------------------------------------------------- #
def test_source_upsert_is_idempotent(db_session: Session) -> None:
    repo = SourceRepository(db_session)
    a = repo.upsert_by_url(name="IGN", url="https://ign.com/rss")
    b = repo.upsert_by_url(name="IGN News", url="https://ign.com/rss", weight=2.0)
    assert a.id == b.id
    assert b.name == "IGN News"
    assert b.weight == pytest.approx(2.0)
    assert len(repo.list_all()) == 1


def test_source_list_enabled_only(db_session: Session) -> None:
    repo = SourceRepository(db_session)
    repo.add(name="On", url="https://on.com/rss")
    off = repo.add(name="Off", url="https://off.com/rss")
    repo.set_enabled(off.id, False)
    assert {s.name for s in repo.list_all(enabled_only=True)} == {"On"}
    assert len(repo.list_all()) == 2


def test_due_sources_respects_interval(db_session: Session) -> None:
    repo = SourceRepository(db_session)
    now = utcnow()
    never = repo.add(name="Never", url="https://never.com/rss")
    fresh = repo.add(name="Fresh", url="https://fresh.com/rss")
    stale = repo.add(name="Stale", url="https://stale.com/rss")
    repo.mark_polled(fresh.id, when=now)  # polled just now -> not due
    repo.mark_polled(stale.id, when=now - timedelta(hours=1))  # long ago -> due

    due = repo.due_sources(poll_interval=timedelta(minutes=10), now=now)
    due_names = {s.name for s in due}
    assert "Never" in due_names  # never polled -> always due
    assert "Stale" in due_names
    assert "Fresh" not in due_names
    assert never.id is not None


# --------------------------------------------------------------------------- #
# ArticleRepository                                                           #
# --------------------------------------------------------------------------- #
def test_article_get_or_create_is_idempotent(db_session: Session) -> None:
    source_id = _make_source(db_session)
    repo = ArticleRepository(db_session)
    a, created = repo.get_or_create(
        source_id=source_id, url="https://ign.com/a", url_hash="h1", title="T"
    )
    a2, created2 = repo.get_or_create(
        source_id=source_id, url="https://ign.com/a", url_hash="h1", title="Different title"
    )
    assert created is True
    assert created2 is False
    assert a.id == a2.id
    assert a2.title == "T"  # existing row untouched
    assert repo.exists_by_url_hash("h1") is True
    assert repo.exists_by_url_hash("missing") is False


def test_article_set_status(db_session: Session) -> None:
    source_id = _make_source(db_session)
    repo = ArticleRepository(db_session)
    a, _ = repo.get_or_create(source_id=source_id, url="u", url_hash="h", title="t")
    assert a.status is ArticleStatus.FETCHED
    updated = repo.set_status(a.id, ArticleStatus.SCORED)
    assert updated is not None
    assert updated.status is ArticleStatus.SCORED
    assert repo.set_status(999999, ArticleStatus.POSTED) is None


def test_article_recent_filters_by_window_and_status(db_session: Session) -> None:
    source_id = _make_source(db_session)
    repo = ArticleRepository(db_session)
    a1, _ = repo.get_or_create(source_id=source_id, url="u1", url_hash="h1", title="t1")
    a2, _ = repo.get_or_create(source_id=source_id, url="u2", url_hash="h2", title="t2")
    repo.set_status(a2.id, ArticleStatus.REJECTED)

    all_recent = repo.recent(window=timedelta(days=1))
    assert {a.id for a in all_recent} == {a1.id, a2.id}

    only_fetched = repo.recent(window=timedelta(days=1), statuses=(ArticleStatus.FETCHED,))
    assert {a.id for a in only_fetched} == {a1.id}


# --------------------------------------------------------------------------- #
# DecisionRepository                                                          #
# --------------------------------------------------------------------------- #
def test_decision_record_and_latest(db_session: Session) -> None:
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = DecisionRepository(db_session)
    repo.record(article_id=art.id, importance_score=0.4, reason="first")
    second = repo.record(article_id=art.id, importance_score=0.9, is_breaking=True, reason="second")
    latest = repo.latest_for_article(art.id)
    assert latest is not None
    assert latest.id == second.id
    assert latest.is_breaking is True


# --------------------------------------------------------------------------- #
# PostRepository                                                              #
# --------------------------------------------------------------------------- #
def test_post_queue_ordering_and_due_selection(db_session: Session) -> None:
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = PostRepository(db_session)
    now = utcnow()
    future = repo.enqueue(article_id=art.id, text="future", scheduled_at=now + timedelta(hours=1))
    unscheduled = repo.enqueue(article_id=art.id, text="unscheduled")
    past = repo.enqueue(article_id=art.id, text="past", scheduled_at=now - timedelta(minutes=5))

    # Unscheduled posts are treated as immediately due and preferred first.
    nxt = repo.next_publishable_post(now=now)
    assert nxt is not None
    assert nxt.id == unscheduled.id
    assert future.id != nxt.id
    assert past.id != nxt.id


def test_post_future_only_not_publishable(db_session: Session) -> None:
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = PostRepository(db_session)
    now = utcnow()
    repo.enqueue(article_id=art.id, text="future", scheduled_at=now + timedelta(hours=2))
    assert repo.next_publishable_post(now=now) is None


def test_post_publish_is_idempotent(db_session: Session) -> None:
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = PostRepository(db_session)
    post = repo.enqueue(article_id=art.id, text="hello")
    first = repo.mark_published(post.id, telegram_message_id=42)
    assert first is not None
    published_at = first.published_at
    # Second publish is a no-op: status, timestamp, and message id are stable.
    second = repo.mark_published(post.id, telegram_message_id=99)
    assert second is not None
    assert second.status is PostStatus.PUBLISHED
    assert second.telegram_message_id == 42
    assert second.published_at == published_at


def test_latest_published_at_tracks_most_recent(db_session: Session) -> None:
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = PostRepository(db_session)
    assert repo.latest_published_at() is None
    now = utcnow()
    older = repo.enqueue(article_id=art.id, text="older")
    newer = repo.enqueue(article_id=art.id, text="newer")
    repo.mark_published(older.id, when=now - timedelta(minutes=30))
    repo.mark_published(newer.id, when=now)
    latest = repo.latest_published_at()
    assert latest is not None
    # UtcDateTime guarantees a tz-aware UTC value on every backend, so a direct
    # equality against the tz-aware ``now`` holds (no naive/aware mismatch).
    assert latest.tzinfo is not None
    assert latest == now


def test_post_mark_failed(db_session: Session) -> None:
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    repo = PostRepository(db_session)
    post = repo.enqueue(article_id=art.id, text="x")
    failed = repo.mark_failed(post.id)
    assert failed is not None
    assert failed.status is PostStatus.FAILED
    assert repo.mark_failed(999999) is None


# --------------------------------------------------------------------------- #
# PostLogRepository                                                           #
# --------------------------------------------------------------------------- #
def test_post_log_record(db_session: Session) -> None:
    source_id = _make_source(db_session)
    art, _ = ArticleRepository(db_session).get_or_create(
        source_id=source_id, url="u", url_hash="h", title="t"
    )
    post = PostRepository(db_session).enqueue(article_id=art.id, text="x")
    entry = PostLogRepository(db_session).record(
        post_id=post.id, result="ok", attempt=2, error=None
    )
    assert entry.id is not None
    assert entry.attempt == 2
    assert entry.result == "ok"


# --------------------------------------------------------------------------- #
# KVStateRepository                                                           #
# --------------------------------------------------------------------------- #
def test_kv_set_get_and_defaults(db_session: Session) -> None:
    repo = KVStateRepository(db_session)
    assert repo.get("missing") is None
    assert repo.get("missing", "fallback") == "fallback"
    repo.set("last_post_at", "2025-01-01T00:00:00Z")
    assert repo.get("last_post_at") == "2025-01-01T00:00:00Z"
    # Update path.
    repo.set("last_post_at", "2025-02-02T00:00:00Z")
    assert repo.get("last_post_at") == "2025-02-02T00:00:00Z"


def test_kv_boolean_helpers(db_session: Session) -> None:
    repo = KVStateRepository(db_session)
    assert repo.get_bool("paused", default=False) is False
    repo.set_bool("paused", True)
    assert repo.get_bool("paused") is True
    assert repo.get("paused") == "true"
    repo.set_bool("paused", False)
    assert repo.get_bool("paused") is False
