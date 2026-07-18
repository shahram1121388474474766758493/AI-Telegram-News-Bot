# 🎮 AI-Telegram-News-Bot

> A **professional, fully AI-powered Telegram gaming-news bot** that monitors trusted gaming-news sources, detects breaking news, ignores noise & duplicates, scores importance with AI, rewrites articles into clean Telegram-style posts, generates or selects images, and **auto-publishes 24/7** — with a minimum time gap between posts and a permanent record of everything it processes.

[![Status](https://img.shields.io/badge/status-planning%20%E2%86%92%20v1.0-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()

---

## 📌 Project Overview

- **Name:** AI-Telegram-News-Bot
- **Goal:** Run a hands-off gaming-news channel that always feels *first* and *curated* — never spammy, never duplicated, never off-topic.
- **Status:** 📝 Architecture & roadmap complete → implementation in phases (see [`PROJECT_ROADMAP.md`](./PROJECT_ROADMAP.md)).

This repository currently contains the **complete engineering specification** for the project. Development follows the phased plan in the roadmap, one independently shippable increment at a time.

---

## ✨ What It Will Do

| Capability | Description |
|-----------|-------------|
| 📡 **Monitor sources** | Continuously polls trusted gaming-news sites / RSS feeds. |
| ⚡ **Detect breaking news** | Recognizes and prioritizes time-sensitive stories immediately. |
| 🧹 **Ignore noise** | Drops unimportant, low-signal, or off-topic items. |
| 🧬 **Deduplicate** | Never posts the same story twice — even across different outlets. |
| 🎯 **Score importance** | AI rates each article; a threshold gates publishing. |
| ✍️ **Rewrite** | Produces clean, consistent Telegram-style posts. |
| 🖼️ **Imagery** | Reuses the source image, finds a licensed one, or generates an original. |
| 🚀 **Publish** | Posts automatically to your Telegram channel. |
| ⏱️ **Pace posts** | Enforces a minimum gap between posts (default **20 minutes**). |
| 🗄️ **Persist** | Stores every processed item and every decision in a database. |
| 🧩 **Expand** | Add sources, languages, and channels without redesign. |

---

## 🏗️ Architecture (High Level)

```
Sources → Fetcher → Extractor → Deduplicator → Importance Analyzer (AI)
   → Rewriter (AI) → Image Resolver → Post Queue (min-gap) → Telegram Publisher
   ↳ everything audited in the Database · Config · Logging · Admin commands
```

A **pipeline of independent, testable stages** connected by a durable database and a spaced post-queue. Every external provider (LLM, image, database) sits behind a **swappable interface**. Full diagram and rationale in the [roadmap](./PROJECT_ROADMAP.md#3-high-level-system-architecture).

---

## 🧰 Technology Stack

| Concern | Choice |
|--------|--------|
| Language | Python 3.11+ |
| Telegram | aiogram 3.x (Bot API) |
| HTTP / Feeds | httpx · feedparser |
| Extraction | trafilatura · BeautifulSoup |
| AI (LLM) | OpenAI-compatible, provider-agnostic |
| Images | Pluggable image generation/search API + Pillow |
| Database | SQLite (dev) → PostgreSQL (prod) via SQLAlchemy 2.x + Alembic |
| Scheduling | APScheduler |
| Config | pydantic-settings |
| Logging | structlog (JSON) |
| Tests | pytest · pytest-asyncio · respx |
| Deploy | Docker · docker-compose · GitHub Actions CI |

Full rationale: [roadmap §4](./PROJECT_ROADMAP.md#4-technology-stack--rationale).

---

## 🗂️ Repository Structure (Target v1.0)

```
AI-Telegram-News-Bot/
├── PROJECT_ROADMAP.md      # the complete engineering spec (0 → v1.0)
├── README.md               # this file
├── LICENSE                 # MIT
├── .env.example            # documented configuration template
├── .gitignore
├── pyproject.toml          # (added in Phase 0)
├── src/newsbot/            # application package (built out per phase)
├── config/                 # sources.yaml, prompts, logging
├── scripts/                # seed / run-once / backup helpers
├── tests/                  # unit + integration
└── .github/workflows/      # CI
```

The full target tree is documented in the [roadmap §5](./PROJECT_ROADMAP.md#5-global-folder-structure-target-v10).

---

## 🧠 Data Architecture

- **Data models:** `sources`, `articles`, `decisions`, `posts`, `post_log`, `kv_state`.
- **Storage:** SQLAlchemy ORM — SQLite for local dev, PostgreSQL for production (no code change).
- **Data flow:** raw feed → normalized `Article` → dedup + AI decision → `Post` → spaced queue → published, with every step audited.

Details: [roadmap §6](./PROJECT_ROADMAP.md#6-data-model-overview).

---

## 🗺️ Development Roadmap

The project is broken into **17 independently implementable phases (Phase 0 → 16)**:

| Phase | Title |
|------|-------|
| 0 | Project Bootstrap & Tooling |
| 1 | Configuration & Secrets Management |
| 2 | Database Layer & Migrations |
| 3 | Source Registry & Feed Fetcher |
| 4 | Article Extraction & Normalization |
| 5 | Deduplication Engine |
| 6 | AI Importance Analyzer |
| 7 | AI Rewriter (Telegram Style) |
| 8 | Image Selection & Generation |
| 9 | Telegram Publisher |
| 10 | Scheduling, Rate-Limiting & Post Queue |
| 11 | Orchestration Pipeline & Workers |
| 12 | Admin Control (Telegram Commands) |
| 13 | Logging, Monitoring & Alerting |
| 14 | Testing, CI & Quality Gates |
| 15 | Containerization & Deployment (24/7) |
| 16 | Hardening, Security & v1.0 Release |

Each phase in [`PROJECT_ROADMAP.md`](./PROJECT_ROADMAP.md) includes: **Goal · Description · Tasks · Files · Folder structure · Required libraries · Database changes · APIs · Testing · Completion checklist · Common mistakes · Future improvements.**

---

## ⚙️ Configuration

All configuration is environment-driven. Copy the template and fill it in:

```bash
cp .env.example .env
```

Key variables (see [`.env.example`](./.env.example) for the full, documented list):

| Variable | Purpose | Default |
|---------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | — |
| `TELEGRAM_CHANNEL_ID` | Target channel (e.g. `@mychannel`) | — |
| `ADMIN_USER_IDS` | Comma-separated admin user IDs | — |
| `DATABASE_URL` | SQLite/PostgreSQL URL | `sqlite:///data/newsbot.db` |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | AI provider config | — |
| `MIN_POST_GAP_MINUTES` | Minimum spacing between posts | `20` |
| `IMPORTANCE_THRESHOLD` | Publish gate (0–1) | `0.6` |
| `POLL_INTERVAL_MINUTES` | Source polling cadence | `10` |

> 🔒 **Security:** never commit a real `.env`. Only `.env.example` is tracked.

---

## 🚀 Getting Started (once Phase 0+ is implemented)

```bash
# 1. Clone
git clone https://github.com/<owner>/AI-Telegram-News-Bot.git
cd AI-Telegram-News-Bot

# 2. Configure
cp .env.example .env      # fill in tokens & settings

# 3. Install
pip install -e ".[dev]"   # (added in Phase 0)

# 3b. Verify configuration (validates env; prints a secret-masked summary)
python -m newsbot config  # (added in Phase 1)

# 4. Migrate DB
alembic upgrade head      # (added in Phase 2)

# 5. Run one pipeline pass (debug)
python scripts/run_once.py

# 6. Run everything
python -m newsbot all
```

**Docker (24/7):**
```bash
docker compose up -d      # bot + PostgreSQL, auto-restart (Phase 15)
```

---

## 🧪 Testing

```bash
make test        # pytest unit + integration
make lint        # ruff
make typecheck   # mypy
```

External services (Telegram, LLM, image, HTTP) are **mocked** in tests — no real network calls. Target coverage ≥ 80% on core logic. See [roadmap §11](./PROJECT_ROADMAP.md#11-global-testing-strategy).

---

## 🔐 Security

- Secrets only via environment / secret store; never in the repo or logs.
- Least-privilege bot token; admin commands restricted to an allowlist.
- All external inputs (feeds, LLM output, admin args) validated.
- Dependency audit (`pip-audit`) + secret scanning in CI.
- Rate/cost caps on AI and Telegram.

Full checklist: [roadmap §12](./PROJECT_ROADMAP.md#12-security-checklist).

---

## 🧩 Current Status & Next Steps

- ✅ **Done:** Complete architecture, technology decisions, data model, and the full 17-phase implementation roadmap.
- ✅ **Phase 0 — Bootstrap & Tooling:** `pyproject.toml`, `requirements.txt`, the importable `newsbot` package with a stub CLI (`newsbot {pipeline,publisher,admin,all}`), `Makefile` quality-gate targets, `.dockerignore`, a passing smoke-test suite, and a GitHub Actions CI workflow (in [`ci/ci.yml`](./ci/ci.yml) — see its header to activate under `.github/workflows/`). All gates green: `ruff`, `black`, `mypy --strict`, `pytest`.
- ✅ **Phase 1 — Configuration & Secrets:** validated, environment-driven [`src/newsbot/settings.py`](./src/newsbot/settings.py) (`pydantic-settings`) covering every runtime knob — with `SecretStr` secrets, `Environment`/`LogLevel` enums, production-strict validation (real secrets required when `ENVIRONMENT=production`), and typed derived accessors (`admin_ids`, `min_post_gap`/`poll_interval` as `timedelta`). Exposed via a cached `get_settings()` and a new `newsbot config` command that validates and prints a **secret-masked** summary. Fully unit-tested (loading, parsing, range/validation, masking, caching, CLI).
- 🔜 **Next:** **Phase 2 (Database Layer & Migrations)** — SQLAlchemy 2.x ORM models + Alembic, committing each increment.

Not yet implemented: application features (built out phase by phase per the roadmap).

---

## 📈 Post-v1.0 Ideas

Multi-channel/multi-language publishing · story clustering with a vector DB · human-in-the-loop approval · analytics dashboard · distributed task queue · fine-tuned importance classifier. See [roadmap §14](./PROJECT_ROADMAP.md#14-post-v10-future-roadmap).

---

## 📄 License

Released under the **MIT License** — see [`LICENSE`](./LICENSE).

---

## 🤝 Contributing

Development is **checkpoint-based**: every meaningful change is committed and pushed immediately as a recovery point. Use conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`) and keep each phase independently shippable.

---

*Built to be modular, maintainable, secure, and scalable — from an empty repo to a production-ready v1.0.*
