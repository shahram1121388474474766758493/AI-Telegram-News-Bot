<!--
  PROJECT_ROADMAP.md
  AI-Telegram-News-Bot
  The complete software development roadmap — from zero to v1.0.
  This document is the single source of truth for the entire project.
-->

# 🎮 AI-Telegram-News-Bot — Complete Software Development Roadmap

> **From an empty repository to a production-ready, fully AI-powered Telegram gaming-news bot running 24/7.**

This document describes the **entire project** from its very first commit to **version 1.0**.
It is intentionally exhaustive: every phase is self-contained, independently implementable, and includes its goal, description, tasks, files, folder structure, required libraries, database changes, APIs, testing strategy, completion checklist, common mistakes, and future improvements.

Treat this roadmap as a **commercial engineering specification**, not a sketch.

---

## 📑 Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Vision & Goals](#2-product-vision--goals)
3. [High-Level System Architecture](#3-high-level-system-architecture)
4. [Technology Stack & Rationale](#4-technology-stack--rationale)
5. [Global Folder Structure (Target v1.0)](#5-global-folder-structure-target-v10)
6. [Data Model Overview](#6-data-model-overview)
7. [Development Principles & Conventions](#7-development-principles--conventions)
8. [Phase Roadmap Index](#8-phase-roadmap-index)
9. [Detailed Phases](#9-detailed-phases)
    - [Phase 0 — Project Bootstrap & Tooling](#phase-0--project-bootstrap--tooling)
    - [Phase 1 — Configuration & Secrets Management](#phase-1--configuration--secrets-management)
    - [Phase 2 — Database Layer & Migrations](#phase-2--database-layer--migrations)
    - [Phase 3 — Source Registry & Feed Fetcher](#phase-3--source-registry--feed-fetcher)
    - [Phase 4 — Article Extraction & Normalization](#phase-4--article-extraction--normalization)
    - [Phase 5 — Deduplication Engine](#phase-5--deduplication-engine)
    - [Phase 6 — AI Importance Analyzer](#phase-6--ai-importance-analyzer)
    - [Phase 7 — AI Rewriter (Telegram Style)](#phase-7--ai-rewriter-telegram-style)
    - [Phase 8 — Image Selection & Generation](#phase-8--image-selection--generation)
    - [Phase 9 — Telegram Publisher](#phase-9--telegram-publisher)
    - [Phase 10 — Scheduling, Rate-Limiting & Post Queue](#phase-10--scheduling-rate-limiting--post-queue)
    - [Phase 11 — Orchestration Pipeline & Workers](#phase-11--orchestration-pipeline--workers)
    - [Phase 12 — Admin Control (Telegram Commands)](#phase-12--admin-control-telegram-commands)
    - [Phase 13 — Logging, Monitoring & Alerting](#phase-13--logging-monitoring--alerting)
    - [Phase 14 — Testing, CI & Quality Gates](#phase-14--testing-ci--quality-gates)
    - [Phase 15 — Containerization & Deployment](#phase-15--containerization--deployment)
    - [Phase 16 — Hardening, Security & v1.0 Release](#phase-16--hardening-security--v10-release)
10. [Cross-Cutting Concerns](#10-cross-cutting-concerns)
11. [Global Testing Strategy](#11-global-testing-strategy)
12. [Security Checklist](#12-security-checklist)
13. [Release Plan & Versioning](#13-release-plan--versioning)
14. [Post-v1.0 Future Roadmap](#14-post-v10-future-roadmap)
15. [Glossary](#15-glossary)

---

## 1. Executive Summary

**AI-Telegram-News-Bot** is an autonomous content pipeline that watches trusted gaming-news sources, decides in real time which stories matter, transforms them into clean, channel-ready Telegram posts (text + image), and publishes them to a Telegram channel around the clock — with strict spacing between posts and a permanent record of everything it processes.

The system is built to be **modular** (each capability is an isolated component), **maintainable** (clear boundaries, typed interfaces, tests), **secure** (secrets never touch the repo or logs), and **scalable** (stateless workers, a durable queue, and a database that can grow from SQLite to PostgreSQL without a rewrite).

The roadmap below decomposes the build into **17 phases (Phase 0 → Phase 16)**. Each phase is small enough to be implemented and shipped independently, and each ends in a working, testable increment.

---

## 2. Product Vision & Goals

### 2.1 Vision
> A gaming channel that always feels *first* and *curated* — never spammy, never duplicated, never off-topic — running with zero manual effort.

### 2.2 Functional Goals (what it must do)
| # | Capability | Description |
|---|-----------|-------------|
| G1 | **Monitor sources** | Continuously poll trusted gaming-news sites/RSS feeds. |
| G2 | **Detect breaking news** | Recognize and prioritize time-sensitive stories immediately. |
| G3 | **Ignore noise** | Drop unimportant, low-signal, or off-topic items. |
| G4 | **Deduplicate** | Never post the same story twice, even across sources. |
| G5 | **Score importance** | Use AI to rate each article and gate publishing on a threshold. |
| G6 | **Rewrite** | Produce a clean, consistent Telegram-style post from the source. |
| G7 | **Imagery** | Select a suitable image, or generate one when none is available. |
| G8 | **Publish** | Post automatically to the configured Telegram channel. |
| G9 | **Pace posts** | Enforce a minimum gap between posts (default 20 minutes). |
| G10 | **Persist** | Store every processed item and every decision in a database. |
| G11 | **Expand** | Add sources, languages, and channels without redesign. |

### 2.3 Non-Functional Goals (how well it must do it)
- **Availability:** 24/7 operation; automatic restart on crash; graceful shutdown.
- **Reliability:** No data loss; idempotent processing; safe retries.
- **Security:** Secrets isolated; least-privilege tokens; input sanitized.
- **Scalability:** Horizontal worker scaling; swappable database backend.
- **Maintainability:** Modular packages; typed contracts; ≥80% test coverage on core logic.
- **Observability:** Structured logs, metrics, and admin alerts.
- **Cost control:** Cache AI calls, batch where possible, respect provider rate limits.

### 2.4 Explicit Non-Goals (v1.0)
- No web UI dashboard (admin control is via Telegram commands).
- No multi-tenant SaaS (single owner, single/few channels).
- No paid content scraping that violates a site's ToS.

---

## 3. High-Level System Architecture

The bot is a **pipeline of independent stages** connected by a durable queue and a shared database. Each stage is a pure, testable unit.

```
                        ┌──────────────────────────────────────────────────────┐
                        │                    SCHEDULER (cron)                    │
                        └───────────────┬──────────────────────────────────────┘
                                        │ triggers polling
                                        ▼
   Trusted Sources        ┌──────────────────────────┐
   (RSS / HTML / API) ───▶│  1. FETCHER              │  raw feed items
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  2. EXTRACTOR/NORMALIZER │  clean article {title,body,url,ts,img}
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  3. DEDUPLICATOR         │  drop seen/near-duplicate
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  4. IMPORTANCE ANALYZER  │  AI score + breaking flag
                          └────────────┬─────────────┘
                                       │ (score ≥ threshold?)
                                       ▼
                          ┌──────────────────────────┐
                          │  5. REWRITER (AI)        │  Telegram-style post text
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  6. IMAGE RESOLVER       │  pick/generate image
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  7. POST QUEUE (DB)      │  scheduled, spaced ≥ gap
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  8. PUBLISHER            │──▶ Telegram Channel
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │  DATABASE (audit + state)│  articles, decisions, posts, sources
                          └──────────────────────────┘

   Cross-cutting: CONFIG · LOGGING · METRICS · ADMIN COMMANDS · ERROR HANDLING · RETRIES
```

### 3.1 Runtime Processes
- **`worker.pipeline`** — runs the fetch→publish pipeline stages.
- **`worker.publisher`** — drains the post queue respecting the min-gap.
- **`bot.admin`** — long-polls Telegram for admin commands (`/status`, `/pause`, etc.).
- **`scheduler`** — periodic triggers (APScheduler) for polling and maintenance.

All processes are supervised (systemd / PM2 / Docker restart policy) for 24/7 uptime.

---

## 4. Technology Stack & Rationale

| Concern | Choice | Why |
|--------|--------|-----|
| Language | **Python 3.11+** | Best ecosystem for AI + scraping + Telegram; async support. |
| Telegram | **aiogram 3.x** (bot) + Bot API | Modern async Telegram framework; publishing + admin commands. |
| HTTP | **httpx** (async) | Async requests, HTTP/2, timeouts, retries. |
| Feeds | **feedparser** | Robust RSS/Atom parsing. |
| HTML extraction | **trafilatura** + **selectolax/BeautifulSoup** | Clean main-content extraction. |
| Scheduling | **APScheduler** | In-process cron without external services. |
| AI (LLM) | **OpenAI-compatible API** (pluggable provider) | Importance scoring + rewriting; provider-agnostic client. |
| Image gen | **Image API (pluggable)** | Generate images when none exist. |
| DB (dev) | **SQLite** via SQLAlchemy | Zero-setup local development. |
| DB (prod) | **PostgreSQL** via SQLAlchemy | Scales; same ORM, no rewrite. |
| ORM/Migrations | **SQLAlchemy 2.x** + **Alembic** | Typed models + versioned schema. |
| Config | **pydantic-settings** | Validated env-based config. |
| Validation | **pydantic v2** | Typed data contracts between stages. |
| Logging | **structlog** (JSON) | Structured, queryable logs. |
| Retries | **tenacity** | Declarative retry/backoff. |
| Dedup (semantic) | **rapidfuzz** + hashing (+ optional embeddings) | Fast near-duplicate detection. |
| Tests | **pytest** + **pytest-asyncio** + **respx** | Unit/integration + HTTP mocking. |
| Lint/format | **ruff** + **black** + **mypy** | Quality gates. |
| Packaging | **uv / pip + pyproject.toml** | Reproducible deps. |
| Containers | **Docker** + **docker-compose** | Reproducible deployment. |
| CI | **GitHub Actions** | Lint, type-check, test on every push. |

> **Rationale note:** All external providers (LLM, image, DB) sit behind **interfaces**, so any provider can be swapped without touching business logic.

---

## 5. Global Folder Structure (Target v1.0)

```
AI-Telegram-News-Bot/
├── PROJECT_ROADMAP.md
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── alembic.ini
│
├── config/
│   ├── sources.yaml            # trusted source registry
│   ├── prompts/                # versioned AI prompt templates
│   │   ├── importance.txt
│   │   └── rewrite.txt
│   └── logging.yaml
│
├── src/
│   └── newsbot/
│       ├── __init__.py
│       ├── main.py             # entrypoint / process launcher
│       ├── settings.py         # pydantic-settings config
│       │
│       ├── core/
│       │   ├── models.py       # pydantic data contracts (Article, Decision, Post)
│       │   ├── errors.py       # typed exceptions
│       │   ├── logging.py      # structlog setup
│       │   └── retry.py        # tenacity policies
│       │
│       ├── db/
│       │   ├── engine.py       # SQLAlchemy engine/session
│       │   ├── models.py       # ORM tables
│       │   ├── repositories.py # data-access layer
│       │   └── migrations/     # Alembic versions
│       │
│       ├── sources/
│       │   ├── registry.py     # load sources.yaml
│       │   ├── fetcher.py      # RSS/HTML/API fetchers
│       │   └── extractor.py    # normalize to Article
│       │
│       ├── processing/
│       │   ├── dedup.py        # hashing + fuzzy + (optional) embeddings
│       │   ├── importance.py   # AI importance analyzer
│       │   ├── rewriter.py     # AI Telegram-style rewriter
│       │   └── images.py       # select/generate image
│       │
│       ├── ai/
│       │   ├── client.py       # provider-agnostic LLM client
│       │   ├── image_client.py # provider-agnostic image client
│       │   └── cache.py        # response cache
│       │
│       ├── publishing/
│       │   ├── telegram.py     # aiogram publisher
│       │   ├── queue.py        # post queue + min-gap scheduler
│       │   └── formatter.py    # final Telegram message assembly
│       │
│       ├── admin/
│       │   └── commands.py     # /status /pause /resume /sources ...
│       │
│       ├── scheduler/
│       │   └── jobs.py         # APScheduler jobs
│       │
│       └── pipeline/
│           └── orchestrator.py # wires stages end-to-end
│
├── scripts/
│   ├── seed_sources.py
│   └── run_once.py             # run a single pipeline pass (debug)
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── conftest.py
│
└── .github/
    └── workflows/
        └── ci.yml
```

---

## 6. Data Model Overview

Core entities (fully specified in Phase 2). Field types shown conceptually.

- **`sources`** — registry of trusted feeds. `(id, name, url, type[rss|html|api], enabled, weight, last_polled_at, created_at)`
- **`articles`** — every fetched+normalized item. `(id, source_id, url, url_hash, title, body, published_at, image_url, content_hash, simhash, status, created_at)`
- **`decisions`** — AI outcomes per article. `(id, article_id, importance_score, is_breaking, is_duplicate, reason, model, prompt_version, created_at)`
- **`posts`** — publishable/published units. `(id, article_id, text, image_path, status[queued|published|failed], scheduled_at, published_at, telegram_message_id, created_at)`
- **`post_log`** — audit of publish attempts. `(id, post_id, attempt, result, error, created_at)`
- **`kv_state`** — small runtime flags. `(key, value, updated_at)` e.g. `paused=false`, `last_post_at=...`

**Status lifecycle for `articles`:** `fetched → deduped → scored → (rejected | rewritten) → posted`.

---

## 7. Development Principles & Conventions

1. **Checkpoint-based commits.** After every meaningful change: `git add → commit → push`. Never accumulate uncommitted work.
2. **One responsibility per module.** Stages never import each other's internals; they exchange **pydantic models** only.
3. **Providers behind interfaces.** LLM/image/DB providers are swappable.
4. **Idempotency.** Re-processing an article must never create duplicates (guarded by `url_hash`/`content_hash`).
5. **Fail safe, not silent.** Errors are logged with context and retried with backoff; poison items are quarantined, not dropped silently.
6. **Config over code.** Sources, thresholds, gaps, prompts live in config, not hardcoded.
7. **Secrets never in repo/logs.** Only `.env.example` is committed.
8. **Everything testable.** Pure functions where possible; external calls mocked in tests.
9. **Conventional commits.** `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
10. **Semantic versioning.** `MAJOR.MINOR.PATCH`.

---

## 8. Phase Roadmap Index

| Phase | Title | Ships |
|------|-------|-------|
| 0 | Project Bootstrap & Tooling | repo, deps, lint, CI skeleton |
| 1 | Configuration & Secrets | validated settings, `.env.example` |
| 2 | Database Layer & Migrations | ORM models + Alembic |
| 3 | Source Registry & Fetcher | poll RSS/HTML/API |
| 4 | Extraction & Normalization | clean `Article` objects |
| 5 | Deduplication Engine | drop duplicates |
| 6 | AI Importance Analyzer | score + breaking flag |
| 7 | AI Rewriter | Telegram-style text |
| 8 | Image Selection & Generation | image per post |
| 9 | Telegram Publisher | post to channel |
| 10 | Scheduling & Rate-Limiting | min-gap queue |
| 11 | Orchestration Pipeline | end-to-end wiring |
| 12 | Admin Commands | control via Telegram |
| 13 | Logging & Monitoring | observability |
| 14 | Testing & CI | quality gates |
| 15 | Containerization & Deploy | Docker, 24/7 |
| 16 | Hardening & v1.0 | security, release |

Each phase below follows the same template: **Goal · Description · Tasks · Files · Folder structure · Required libraries · Database changes · APIs · Testing · Completion checklist · Common mistakes · Future improvements.**

---

## 9. Detailed Phases

---

### Phase 0 — Project Bootstrap & Tooling

**Goal:** Establish a professional, reproducible Python project skeleton with quality gates before any feature code exists.

**Description:** Create the package layout, dependency manifests, formatting/linting/typing tooling, a `Makefile` for common tasks, and a minimal CI workflow. This guarantees every later phase is written under consistent standards and is CI-verified from day one.

**Tasks:**
1. Create `pyproject.toml` (project metadata, tool config for ruff/black/mypy/pytest).
2. Create `requirements.txt` (runtime) and dev extras.
3. Create the `src/newsbot/` package with `__init__.py` and a stub `main.py`.
4. Add `Makefile` targets: `install`, `lint`, `format`, `typecheck`, `test`, `run`.
5. Add `.dockerignore`, `LICENSE` (MIT).
6. Add `.github/workflows/ci.yml` running lint + typecheck + tests on push/PR.
7. Configure `ruff`, `black`, `mypy` strict mode for `src/`.

**Files:**
- `pyproject.toml`, `requirements.txt`, `Makefile`, `.dockerignore`, `LICENSE`
- `src/newsbot/__init__.py`, `src/newsbot/main.py`
- `.github/workflows/ci.yml`

**Folder structure (added this phase):**
```
src/newsbot/__init__.py
src/newsbot/main.py
.github/workflows/ci.yml
```

**Required libraries:** `ruff`, `black`, `mypy`, `pytest`, `pytest-asyncio` (dev). No runtime deps yet beyond stubs.

**Database changes:** None.

**APIs:** None.

**Testing:**
- `tests/unit/test_smoke.py` importing the package and asserting version string.
- CI must pass green on first push.

**Completion checklist:**
- [ ] `make lint`, `make typecheck`, `make test` all pass locally.
- [ ] CI green on GitHub.
- [ ] Package importable: `python -c "import newsbot"`.

**Common mistakes:**
- Forgetting `src/` layout on `PYTHONPATH` → use `pyproject.toml` `[tool.setuptools]` / editable install.
- Over-pinning deps too early; pin loosely, lock later.
- Enabling mypy strict on tests folder and drowning in noise → scope mypy to `src/`.

**Future improvements:** Pre-commit hooks; `uv` lockfile; coverage badge.

---

### Phase 1 — Configuration & Secrets Management

**Goal:** A single, validated, environment-driven configuration object; no secret ever committed.

**Description:** Use `pydantic-settings` to load all runtime configuration from environment variables (and `.env` in dev). Provide `.env.example` documenting every variable. Configuration includes tokens, database URL, thresholds, and the min-post-gap.

**Tasks:**
1. Implement `src/newsbot/settings.py` with a `Settings` class.
2. Define fields: `telegram_bot_token`, `telegram_channel_id`, `admin_user_ids`, `database_url`, `llm_api_key`, `llm_base_url`, `llm_model`, `image_api_key`, `min_post_gap_minutes` (default 20), `importance_threshold` (default 0.6), `poll_interval_minutes`, `log_level`, `environment`.
3. Add validators (e.g. token non-empty in prod, threshold in [0,1]).
4. Create `.env.example` with placeholders + comments.
5. Provide a cached `get_settings()` accessor.

**Files:** `src/newsbot/settings.py`, `.env.example`

**Folder structure:** (no new dirs)

**Required libraries:** `pydantic`, `pydantic-settings`, `python-dotenv`.

**Database changes:** None (defines `database_url`).

**APIs:** None.

**Testing:**
- Unit test loading from a monkeypatched env.
- Test validation failures raise clearly.

**Completion checklist:**
- [ ] `get_settings()` returns a validated object.
- [ ] Missing required var in `production` raises a helpful error.
- [ ] `.env.example` documents every field; real `.env` git-ignored.

**Common mistakes:**
- Reading `os.environ` directly elsewhere in code (bypasses validation) — always go through `Settings`.
- Committing a real `.env`.
- Not caching settings → repeated env parsing.

**Future improvements:** Secret managers (Vault/Doppler); per-channel config; hot reload.

---

### Phase 2 — Database Layer & Migrations

**Goal:** A durable, migratable persistence layer that works on SQLite (dev) and PostgreSQL (prod) unchanged.

**Description:** Define SQLAlchemy 2.x ORM models for all entities in §6, wire an engine/session factory, add a thin repository layer for data access, and initialize Alembic for versioned migrations.

**Tasks:**
1. `db/engine.py` — build engine from `database_url`, session factory, healthcheck.
2. `db/models.py` — ORM: `Source`, `Article`, `Decision`, `Post`, `PostLog`, `KVState`.
3. `db/repositories.py` — CRUD + queries (`get_article_by_url_hash`, `enqueue_post`, `next_publishable_post`, `record_decision`, ...).
4. `alembic.ini` + `db/migrations/` — initial migration creating all tables + indexes (`url_hash` unique, `content_hash`, `posts.status`, `scheduled_at`).
5. `scripts/seed_sources.py` — load `config/sources.yaml` into `sources`.

**Files:** `db/engine.py`, `db/models.py`, `db/repositories.py`, `alembic.ini`, `db/migrations/*`, `scripts/seed_sources.py`

**Folder structure (added):**
```
src/newsbot/db/{engine.py,models.py,repositories.py,migrations/}
alembic.ini
scripts/seed_sources.py
```

**Required libraries:** `SQLAlchemy>=2`, `alembic`, `psycopg[binary]` (prod), `aiosqlite`/`sqlite` (dev), `PyYAML`.

**Database changes:** **Initial schema** — creates `sources, articles, decisions, posts, post_log, kv_state` with indexes and FKs listed in §6.

**APIs:** None.

**Testing:**
- Spin up in-memory SQLite; run migrations; insert+query each model.
- Uniqueness constraint on `url_hash` enforced.
- Repository idempotency: inserting same `url_hash` twice is a no-op/handled.

**Completion checklist:**
- [ ] `alembic upgrade head` builds full schema on SQLite and Postgres.
- [ ] Repositories covered by unit tests.
- [ ] Seed script populates sources.

**Common mistakes:**
- SQLite/Postgres type mismatches (e.g. `JSONB` vs `JSON`) — use SQLAlchemy generic types.
- Forgetting indexes on hash columns → slow dedup lookups.
- Sessions leaking (no `with` / context manager) → connection exhaustion.

**Future improvements:** Read replicas; partitioning `articles` by date; connection pooling tuning.

---

### Phase 3 — Source Registry & Feed Fetcher

**Goal:** Reliably pull raw items from every enabled trusted source on a schedule.

**Description:** Load the source registry from `config/sources.yaml`, and implement fetchers for RSS/Atom, generic HTML index pages, and JSON APIs. Fetching is async, timeout-bounded, retried with backoff, and polite (respects `robots`, adds `User-Agent`, throttles per host).

**Tasks:**
1. `sources/registry.py` — parse+validate `sources.yaml` into `Source` models.
2. `sources/fetcher.py` — async `httpx` client; `fetch_rss`, `fetch_html_index`, `fetch_api`.
3. Per-source `last_polled_at` update; conditional GET (ETag/Last-Modified) to save bandwidth.
4. `config/sources.yaml` — seed with reputable gaming outlets' public RSS feeds.
5. Emit raw items (url, title, summary, published_at, raw_html) to the next stage.

**Files:** `sources/registry.py`, `sources/fetcher.py`, `config/sources.yaml`

**Folder structure (added):**
```
src/newsbot/sources/{registry.py,fetcher.py}
config/sources.yaml
```

**Required libraries:** `httpx`, `feedparser`, `PyYAML`, `tenacity`.

**Database changes:** Uses `sources` (read + update `last_polled_at`). No schema change.

**APIs:** Outbound HTTP to source feeds; optional third-party news APIs.

**Testing:**
- `respx`-mock RSS/HTML/API responses; assert parsed items.
- Timeout + retry behavior tested with simulated failures.
- Conditional GET returns 304 → no reprocessing.

**Completion checklist:**
- [ ] All enabled sources fetch without unhandled errors.
- [ ] Retries/backoff verified.
- [ ] `last_polled_at` updated per source.

**Common mistakes:**
- Ignoring `robots.txt`/ToS → legal/ethical risk.
- No timeout → hung workers.
- Assuming every feed has `published` date — handle missing fields.
- Hammering a host (no throttle) → IP bans.

**Future improvements:** Playwright for JS-heavy sites; per-source parsers; adaptive polling by source velocity.

---

### Phase 4 — Article Extraction & Normalization

**Goal:** Turn messy raw items into clean, uniform `Article` objects ready for AI.

**Description:** Extract the main article text (stripping nav/ads/boilerplate), normalize whitespace/encoding, detect language, extract a lead image, compute `url_hash` and `content_hash`/`simhash`, and persist as `articles` with status `fetched`.

**Tasks:**
1. `sources/extractor.py` — use `trafilatura` (fallback `BeautifulSoup`) for main content.
2. Normalize: unicode NFKC, collapse whitespace, strip tracking params from URLs.
3. Extract lead image (`og:image` / first content image).
4. Compute hashes: `url_hash = sha256(canonical_url)`, `content_hash = sha256(normalized_title+body)`, `simhash` for near-dup.
5. Map to `core/models.Article` (pydantic) and persist via repository (idempotent on `url_hash`).

**Files:** `sources/extractor.py`, `core/models.py` (define `Article`)

**Folder structure (added):**
```
src/newsbot/core/models.py
src/newsbot/sources/extractor.py
```

**Required libraries:** `trafilatura`, `beautifulsoup4`, `selectolax`, `langdetect`/`fasttext`, `w3lib` (URL canonicalization).

**Database changes:** Writes `articles` (status=`fetched`). No schema change (table from Phase 2).

**APIs:** None (may re-fetch full HTML if summary-only).

**Testing:**
- Golden-file tests: sample HTML → expected clean text.
- URL canonicalization strips `utm_*`.
- Hash stability across runs.

**Completion checklist:**
- [ ] Clean body extracted for sample pages.
- [ ] Duplicate URL not inserted twice.
- [ ] Language detected and stored.

**Common mistakes:**
- Extractor returning nav/footer noise — validate with goldens.
- Non-deterministic hashes (unstable ordering/whitespace) — normalize first.
- Losing the source's own image before Phase 8.

**Future improvements:** Readability fallbacks; boilerplate ML model; per-domain extraction rules.

---

### Phase 5 — Deduplication Engine

**Goal:** Guarantee the same story is never posted twice — even when reported by multiple outlets.

**Description:** A layered dedup: (1) **exact** by `url_hash`/`content_hash`; (2) **near-duplicate** by SimHash Hamming distance + `rapidfuzz` title similarity; (3) **optional semantic** by embedding cosine similarity for cross-source paraphrases. Duplicates are marked and skipped, with the decision recorded.

**Tasks:**
1. `processing/dedup.py` — `is_exact_duplicate`, `is_near_duplicate`, `is_semantic_duplicate`.
2. Query recent `articles`/`posts` within a time window for candidate comparison.
3. Thresholds configurable (Hamming ≤ N, fuzz ratio ≥ M, cosine ≥ C).
4. Record outcome in `decisions` (`is_duplicate`, `reason`); set article status `deduped`/`rejected`.

**Files:** `processing/dedup.py`

**Folder structure (added):**
```
src/newsbot/processing/dedup.py
```

**Required libraries:** `rapidfuzz`, `simhash`/custom, (optional) `numpy` + embeddings via `ai/client`.

**Database changes:** Writes `decisions`; updates `articles.status`. No schema change.

**APIs:** Optional embeddings endpoint (via AI client).

**Testing:**
- Identical article → exact duplicate.
- Same story, different outlet/wording → near/semantic duplicate.
- Unrelated articles → not duplicate.

**Completion checklist:**
- [ ] Exact dedup 100% reliable.
- [ ] Near-dup thresholds tuned on sample set.
- [ ] Decisions persisted with reason.

**Common mistakes:**
- Comparing against entire history (slow) — use a rolling time window + indexes.
- Over-aggressive semantic threshold → drops legitimately distinct news.
- Not handling updated/republished articles (same story, new info).

**Future improvements:** Vector DB (pgvector/Qdrant); clustering of stories; "update this post" instead of new post.
