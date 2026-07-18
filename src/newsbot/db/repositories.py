"""Data-access layer — repositories (Phase 2).

Every database query the pipeline needs lives here behind a small, typed,
testable API so the rest of the codebase never writes raw SQL, never manages
sessions ad hoc, and can be exercised against an in-memory database in tests.

Design decisions
----------------
* **Session injection, not session ownership.** Repositories receive a live
  :class:`~sqlalchemy.orm.Session` and never open, commit, or close it. The
  caller owns the transaction boundary (typically via
  :func:`newsbot.db.engine.session_scope`), which keeps repositories pure,
  composable, and trivial to test.
* **Idempotent ingestion.** :meth:`ArticleRepository.get_or_create` keys on the
  unique ``url_hash`` so re-processing a feed item never inserts a duplicate —
  the cornerstone of the "never post the same story twice" guarantee (§7.4).
* **Intent-revealing queries.** Methods are named for *what the pipeline asks*
  (``next_publishable_post``, ``due_sources``) rather than for the SQL they
  emit, so call sites read like the roadmap's architecture.
* **UTC everywhere.** All time comparisons use timezone-aware UTC ``datetime``
  values (see :func:`newsbot.db.models.utcnow`), avoiding the classic
  local-time scheduling bugs called out in the roadmap.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsbot.db.models import (
    Article,
    ArticleStatus,
    Decision,
    KVState,
    Post,
    PostLog,
    PostStatus,
    Source,
    SourceType,
    utcnow,
)

__all__ = [
    "ArticleRepository",
    "DecisionRepository",
    "KVStateRepository",
    "PostLogRepository",
    "PostRepository",
    "SourceRepository",
]


class SourceRepository:
    """Read/write access to the trusted-source registry."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        name: str,
        url: str,
        type: SourceType = SourceType.RSS,
        enabled: bool = True,
        weight: float = 1.0,
    ) -> Source:
        """Create and persist a new source (flushed to obtain its id)."""
        source = Source(name=name, url=url, type=type, enabled=enabled, weight=weight)
        self._session.add(source)
        self._session.flush()
        return source

    def get_by_id(self, source_id: int) -> Source | None:
        """Return the source with ``source_id`` or ``None``."""
        return self._session.get(Source, source_id)

    def get_by_url(self, url: str) -> Source | None:
        """Return the source registered under ``url`` (unique) or ``None``."""
        return self._session.scalar(select(Source).where(Source.url == url))

    def upsert_by_url(
        self,
        *,
        name: str,
        url: str,
        type: SourceType = SourceType.RSS,
        enabled: bool = True,
        weight: float = 1.0,
    ) -> Source:
        """Insert a source or update its mutable fields if ``url`` already exists.

        Makes seeding from ``config/sources.yaml`` idempotent: re-running the
        seed never creates duplicates and picks up config edits.
        """
        existing = self.get_by_url(url)
        if existing is None:
            return self.add(name=name, url=url, type=type, enabled=enabled, weight=weight)
        existing.name = name
        existing.type = type
        existing.enabled = enabled
        existing.weight = weight
        self._session.flush()
        return existing

    def list_all(self, *, enabled_only: bool = False) -> list[Source]:
        """Return all sources, optionally restricted to enabled ones."""
        stmt = select(Source).order_by(Source.id)
        if enabled_only:
            stmt = stmt.where(Source.enabled.is_(True))
        return list(self._session.scalars(stmt))

    def due_sources(self, *, poll_interval: timedelta, now: datetime | None = None) -> list[Source]:
        """Return enabled sources that are due to be polled.

        A source is due when it has never been polled, or when at least
        ``poll_interval`` has elapsed since ``last_polled_at``.
        """
        current = now or utcnow()
        cutoff = current - poll_interval
        stmt = (
            select(Source)
            .where(Source.enabled.is_(True))
            .where((Source.last_polled_at.is_(None)) | (Source.last_polled_at <= cutoff))
            .order_by(Source.id)
        )
        return list(self._session.scalars(stmt))

    def set_enabled(self, source_id: int, enabled: bool) -> Source | None:
        """Enable/disable a source; returns the updated source or ``None``."""
        source = self.get_by_id(source_id)
        if source is None:
            return None
        source.enabled = enabled
        self._session.flush()
        return source

    def mark_polled(self, source_id: int, *, when: datetime | None = None) -> None:
        """Record that ``source_id`` was just polled (``last_polled_at``)."""
        source = self.get_by_id(source_id)
        if source is not None:
            source.last_polled_at = when or utcnow()
            self._session.flush()


class ArticleRepository:
    """Idempotent access to fetched/normalized articles."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_url_hash(self, url_hash: str) -> Article | None:
        """Return the article with ``url_hash`` (unique) or ``None``."""
        return self._session.scalar(select(Article).where(Article.url_hash == url_hash))

    def exists_by_url_hash(self, url_hash: str) -> bool:
        """Fast membership check used by dedup before doing any work."""
        stmt = select(Article.id).where(Article.url_hash == url_hash).limit(1)
        return self._session.scalar(stmt) is not None

    def get_or_create(
        self,
        *,
        source_id: int,
        url: str,
        url_hash: str,
        title: str,
        body: str | None = None,
        published_at: datetime | None = None,
        image_url: str | None = None,
        content_hash: str | None = None,
        simhash: str | None = None,
    ) -> tuple[Article, bool]:
        """Return ``(article, created)`` keyed on the unique ``url_hash``.

        If an article with ``url_hash`` already exists it is returned untouched
        and ``created`` is ``False`` — making feed ingestion safely repeatable.
        """
        existing = self.get_by_url_hash(url_hash)
        if existing is not None:
            return existing, False
        article = Article(
            source_id=source_id,
            url=url,
            url_hash=url_hash,
            title=title,
            body=body,
            published_at=published_at,
            image_url=image_url,
            content_hash=content_hash,
            simhash=simhash,
        )
        self._session.add(article)
        self._session.flush()
        return article, True

    def set_status(self, article_id: int, status: ArticleStatus) -> Article | None:
        """Transition an article to ``status``; returns it or ``None``."""
        article = self._session.get(Article, article_id)
        if article is None:
            return None
        article.status = status
        self._session.flush()
        return article

    def recent(
        self,
        *,
        since: datetime | None = None,
        window: timedelta | None = None,
        statuses: tuple[ArticleStatus, ...] | None = None,
        limit: int | None = None,
    ) -> list[Article]:
        """Return recent articles for dedup candidate comparison.

        ``window`` (relative to now) or an explicit ``since`` bounds the time
        range; ``statuses`` optionally filters by lifecycle state.
        """
        stmt = select(Article).order_by(Article.created_at.desc())
        if window is not None and since is None:
            since = utcnow() - window
        if since is not None:
            stmt = stmt.where(Article.created_at >= since)
        if statuses:
            stmt = stmt.where(Article.status.in_(statuses))
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt))


class DecisionRepository:
    """Audit trail of AI/rule-based decisions per article."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        article_id: int,
        importance_score: float = 0.0,
        is_breaking: bool = False,
        is_duplicate: bool = False,
        reason: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> Decision:
        """Persist a decision row for ``article_id`` and return it."""
        decision = Decision(
            article_id=article_id,
            importance_score=importance_score,
            is_breaking=is_breaking,
            is_duplicate=is_duplicate,
            reason=reason,
            model=model,
            prompt_version=prompt_version,
        )
        self._session.add(decision)
        self._session.flush()
        return decision

    def latest_for_article(self, article_id: int) -> Decision | None:
        """Return the most recent decision recorded for ``article_id``."""
        stmt = (
            select(Decision)
            .where(Decision.article_id == article_id)
            .order_by(Decision.created_at.desc(), Decision.id.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)


class PostRepository:
    """The publishable/published post queue."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        *,
        article_id: int,
        text: str,
        image_path: str | None = None,
        scheduled_at: datetime | None = None,
    ) -> Post:
        """Create a ``queued`` post (min-gap scheduling handled in Phase 10)."""
        post = Post(
            article_id=article_id,
            text=text,
            image_path=image_path,
            status=PostStatus.QUEUED,
            scheduled_at=scheduled_at,
        )
        self._session.add(post)
        self._session.flush()
        return post

    def get_by_id(self, post_id: int) -> Post | None:
        """Return the post with ``post_id`` or ``None``."""
        return self._session.get(Post, post_id)

    def next_publishable_post(self, *, now: datetime | None = None) -> Post | None:
        """Return the next queued post whose ``scheduled_at`` is due.

        Ordering: posts with no schedule first (treated as immediately due),
        then by ``scheduled_at`` ascending, then by insertion order — so the
        queue drains fairly and deterministically.
        """
        current = now or utcnow()
        stmt = (
            select(Post)
            .where(Post.status == PostStatus.QUEUED)
            .where((Post.scheduled_at.is_(None)) | (Post.scheduled_at <= current))
            .order_by(Post.scheduled_at.is_(None).desc(), Post.scheduled_at.asc(), Post.id.asc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def latest_published_at(self) -> datetime | None:
        """Return the timestamp of the most recently published post, if any.

        The min-gap scheduler (Phase 10) uses this to space consecutive posts.
        """
        stmt = (
            select(Post.published_at)
            .where(Post.status == PostStatus.PUBLISHED)
            .where(Post.published_at.is_not(None))
            .order_by(Post.published_at.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def mark_published(
        self,
        post_id: int,
        *,
        telegram_message_id: int | None = None,
        when: datetime | None = None,
    ) -> Post | None:
        """Mark a post published (idempotent) and record its message id."""
        post = self.get_by_id(post_id)
        if post is None:
            return None
        # Idempotency guard: never re-stamp an already-published post.
        if post.status is PostStatus.PUBLISHED:
            return post
        post.status = PostStatus.PUBLISHED
        post.published_at = when or utcnow()
        if telegram_message_id is not None:
            post.telegram_message_id = telegram_message_id
        self._session.flush()
        return post

    def mark_failed(self, post_id: int) -> Post | None:
        """Mark a post as failed to publish; returns it or ``None``."""
        post = self.get_by_id(post_id)
        if post is None:
            return None
        post.status = PostStatus.FAILED
        self._session.flush()
        return post


class PostLogRepository:
    """Append-only audit of individual publish attempts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        post_id: int,
        result: str,
        attempt: int = 1,
        error: str | None = None,
    ) -> PostLog:
        """Append a publish-attempt log entry for ``post_id``."""
        entry = PostLog(post_id=post_id, attempt=attempt, result=result, error=error)
        self._session.add(entry)
        self._session.flush()
        return entry


class KVStateRepository:
    """Tiny key/value store for runtime flags (``paused``, ``last_post_at`` ...)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored value for ``key`` or ``default`` if absent."""
        row = self._session.get(KVState, key)
        return row.value if row is not None else default

    def set(self, key: str, value: str | None) -> KVState:
        """Insert or update ``key`` and return the row (``updated_at`` refreshed)."""
        row = self._session.get(KVState, key)
        if row is None:
            row = KVState(key=key, value=value)
            self._session.add(row)
        else:
            row.value = value
            # Touch updated_at even when the value is unchanged.
            row.updated_at = utcnow()
        self._session.flush()
        return row

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return a boolean flag (stored as ``"true"``/``"false"``)."""
        raw = self.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in ("1", "true", "yes", "on")

    def set_bool(self, key: str, value: bool) -> KVState:
        """Store a boolean flag as a canonical ``"true"``/``"false"`` string."""
        return self.set(key, "true" if value else "false")
