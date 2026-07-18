"""SQLAlchemy 2.x ORM models — the database schema (Phase 2).

These tables implement the data model from the roadmap (§6) and are written to
run **unchanged on SQLite and PostgreSQL**. To that end:

* All models inherit from a single declarative :class:`Base` with typed
  ``Mapped[...]`` columns (SQLAlchemy 2.x style).
* Timestamps default to a timezone-aware UTC "now" computed in Python, which
  behaves identically across backends (no reliance on backend-specific
  ``CURRENT_TIMESTAMP`` semantics).
* Free-form structured data uses the backend-neutral ``JSON`` type.
* Enumerated states are stored as strings via SQLAlchemy's native ``Enum``
  bound to Python :class:`enum.StrEnum` classes, so values are validated and
  self-documenting.
* Hash columns that dedup relies on (``url_hash``, ``content_hash``) are
  indexed; ``url_hash`` is additionally ``UNIQUE`` to make ingestion
  idempotent.

Status lifecycle for an article:
``fetched -> deduped -> scored -> (rejected | rewritten) -> posted``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

__all__ = [
    "Article",
    "ArticleStatus",
    "Base",
    "Decision",
    "KVState",
    "Post",
    "PostLog",
    "PostStatus",
    "Source",
    "SourceType",
    "utcnow",
]


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``.

    Used as the default for ``created_at``/``updated_at`` columns so behavior
    is identical on SQLite and PostgreSQL (both store what we hand them).
    """
    return datetime.now(UTC)


class SourceType(StrEnum):
    """How a source is fetched."""

    RSS = "rss"
    HTML = "html"
    API = "api"


class ArticleStatus(StrEnum):
    """Lifecycle state of an ingested article."""

    FETCHED = "fetched"
    DEDUPED = "deduped"
    SCORED = "scored"
    REJECTED = "rejected"
    REWRITTEN = "rewritten"
    POSTED = "posted"


class PostStatus(StrEnum):
    """Lifecycle state of a publishable post."""

    QUEUED = "queued"
    PUBLISHED = "published"
    FAILED = "failed"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Source(Base):
    """A trusted news source (RSS feed, HTML page, or API endpoint)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, native_enum=False, length=16),
        nullable=False,
        default=SourceType.RSS,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Relative influence when several sources cover the same story (>= 0).
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    articles: Mapped[list[Article]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<Source id={self.id} name={self.name!r} type={self.type}>"


class Article(Base):
    """A fetched and normalized news item."""

    __tablename__ = "articles"
    __table_args__ = (
        # Fast, unique idempotency key for ingestion.
        UniqueConstraint("url_hash", name="uq_articles_url_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    # Stable hash of the canonical URL — indexed + unique (see __table_args__).
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    image_url: Mapped[str | None] = mapped_column(String(2000), default=None)
    # Hash of the normalized body — near-duplicate detection.
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    # SimHash fingerprint (stored as text for backend neutrality).
    simhash: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, native_enum=False, length=16),
        nullable=False,
        default=ArticleStatus.FETCHED,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    source: Mapped[Source] = relationship(back_populates="articles")
    decisions: Mapped[list[Decision]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )
    posts: Mapped[list[Post]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<Article id={self.id} status={self.status} title={self.title!r}>"


class Decision(Base):
    """An AI (or rule-based) decision about a single article."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_breaking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    model: Mapped[str | None] = mapped_column(String(120), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(40), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    article: Mapped[Article] = relationship(back_populates="decisions")

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            f"<Decision id={self.id} article_id={self.article_id} "
            f"score={self.importance_score} breaking={self.is_breaking}>"
        )


class Post(Base):
    """A publishable/published unit derived from an article."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(2000), default=None)
    status: Mapped[PostStatus] = mapped_column(
        SAEnum(PostStatus, native_enum=False, length=16),
        nullable=False,
        default=PostStatus.QUEUED,
        index=True,
    )
    # When the post becomes eligible to publish (min-gap scheduling, Phase 10).
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    article: Mapped[Article] = relationship(back_populates="posts")
    logs: Mapped[list[PostLog]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<Post id={self.id} status={self.status} scheduled_at={self.scheduled_at}>"


class PostLog(Base):
    """An audit record of a single publish attempt for a post."""

    __tablename__ = "post_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    post: Mapped[Post] = relationship(back_populates="logs")

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<PostLog id={self.id} post_id={self.post_id} attempt={self.attempt} result={self.result!r}>"


class KVState(Base):
    """A tiny key/value store for runtime flags (e.g. ``paused``, ``last_post_at``)."""

    __tablename__ = "kv_state"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<KVState key={self.key!r} value={self.value!r}>"
