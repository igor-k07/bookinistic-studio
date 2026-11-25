# 🏛️ Bookinistic Studio 2.0 — Master Implementation Plan

> **Status:** Approved (Architecture Audit & `/grill-me` Sign-Off)  
> **Target Branch:** `v2-architecture` (branched from `main`; keep `main` untouched until final cutover)  
> **Purpose:** Self-contained engineering specification and step-by-step execution checklist. Every step is atomic (2–5 small files, max 400 LOC per file) with explicit contracts, invariants, and verification commands so it can be executed reliably by fast/lightweight AI models.

---

## 📌 1. Approved Architecture Decision Records (ADRs — Do Not Alter Without Approval)

| # | Area | Approved Decision |
| :-: | :--- | :--- |
| **ADR-1** | **Backend Stack** | **Python 3.10+ · FastAPI · Uvicorn (ASGI) · Pydantic v2 · SSE (`/api/events/stream`) · `httpx` · `tenacity` · `lxml` · `boto3` · `Pillow` · `rembg` · `opencv-python-headless` · `SQLite 3 (WAL + FTS5)`**. Single-command launch via `./run.sh` / `start.command` (no Docker, Redis, or Celery). |
| **ADR-2** | **Frontend Stack** | **Vite · TypeScript (strict) · React 19 · Zustand · local Tailwind CSS** (`frontend/dist/` served by FastAPI; Node.js is NOT required at runtime). Auto-generate TS types from `/openapi.json` (`openapi-typescript`). |
| **ADR-3** | **Architecture** | **Hexagonal Architecture (Ports & Adapters / Clean Architecture)** with an explicit Composition Root (`AppContainer` + `StoreContext`). Zero global mutable singletons and zero monkey-patching. |
| **ADR-4** | **Era Boundary (SSOT)** | Single unified rule across Domain, DB, Excel, Ozon API, and UI: **`year <= 2010` or `year is None` → `PRE2011`** (bukinistic `1942-2010`, Ozon category `200001485`, ISBN optional; `<= 1941` → antique Ozon `200001486`); **`year >= 2011` → `POST2011`** (modern `с 2011`, Ozon category `200001483`, ISBN required). |
| **ADR-5** | **GOST Physics (SSOT)** | Single dimension & weight formula in `domain/rules.py` using paper density (coated `115`, offset `80`, typographic/bulky `65`, newsprint `50` g/m²) and the 12 Soviet book format lookup table. Manual user dimensions are protected via `FieldProvenance`. |
| **ADR-6** | **Yandex S3 (Two-Tier)** | Proactive upload to `staging/{store_id}/{asset_id}_{sha8}.jpg` (7-day S3 Lifecycle rule) → on book save, instant server-side `CopyObject` to `books/{store_id}/{article}/01_cover_front_{sha8}.jpg` + `archive/info_page_{n}_{sha8}.jpg` + lightweight `meta.json` (no Base64). Promo card is a single shared `static/99_card.jpg`. Existing legacy URLs in `catalog.db` remain valid without migration. |
| **ADR-7** | **Save & Ozon Flow** | **Single "💾 Сохранить" button**: (1) instant Ozon pre-validation (~5 ms) → (2) atomic local persistence (<0.2s) to SQLite + `books_vault/{article}/` + S3 `CopyObject` + Excel → (3) automatic enqueue to `marketplace_outbox` with background Ozon API sync (`/v3/product/import`, `/v1/product/attributes/update`, `/v1/product/pictures/import`, `/v1/product/import/prices`), `task_id` polling (`/v1/product/import/info`, `/v2/product/pictures/info`), and live SSE status badges. |
| **ADR-8** | **AI + FantLab + Provenance** | Strict `FieldProvenance` priority: `EMPTY(0) < DEFAULT(1) < AI_GEMINI(2) < DB_CANONICAL(3) < FANTLAB_EXACT(4) < USER_MANUAL(5)`. Local barcode scan against `catalog.db` → resize info photos to `1200px` + `exif_transpose` → Gemini Vision (`x-goog-api-key` header) → FantLab (30-day SQLite cache): **exact match** (ISBN or Title+Author+Year+Publisher) sets authoritative bibliographic fields while Gemini fills missing fields and physical exemplar fields (`annotation`, `condition`, `age_limit`); **fuzzy match** appears as a non-destructive suggestion badge. |
| **ADR-9** | **Drafts & Assets V3** | Draft tabs (`books.status = 'DRAFT'` + `workspace_tabs`) and the unified photo registry (`assets` with `version` Optimistic Lock and `render_hash`) live in **SQLite**. Legacy `storage/inbox/`, `storage/session_photos/`, and `session_draft.json` are **removed**. The "🧹 Завершить сессию и очистить кэш" button deletes temp files only for `ARCHIVED` assets with a confirmed `s3_final_url`. |
| **ADR-10** | **Security (Zero-Trust)** | Cloudflare Quick Tunnel exposes **ONLY** `/mobile` and `/api/mobile/*` with a valid QR secret token (`?token=...` or `X-Mobile-Token` header) + local Wi-Fi fallback. Desktop UI, admin endpoints, DB, keys, and macOS host commands are restricted **strictly to `127.0.0.1`**. *(Backlog: Yandex S3 Cloud Relay without `cloudflared` via `IMobileTransport`.)* |
| **ADR-11** | **Extensibility** | Core `Book` is marketplace-agnostic and includes `storage_location` (shelf/box/bin, printed on 58×40 mm thermal labels). All Ozon specifics live in `backend/channels/ozon/` behind `IMarketplaceChannel`, enabling future channels (Avito, Yandex Market, Meshok, Telegram) without touching core or UI. |

---

## 🚫 2. Strict Engineering Guardrails (Mandatory for Every Step)

1. ❌ **NO monkey-patching** (`socket.getaddrinfo`, `urllib3.create_connection`, etc.).
2. ❌ **NO raw `with sqlite3.connect(...) as conn:`** — always use `SqliteUnitOfWork` which guarantees `conn.close()` in `finally`.
3. ❌ **NO `init_db()` / DDL inside `SELECT`/`INSERT`/`UPDATE`** — migrations run strictly once during `StoreContainer` startup.
4. ❌ **NO `re.sub` on XML** in the Excel exporter — use `lxml.etree` DOM + XML 1.0 control-char sanitization.
5. ❌ **NO bare `except Exception: pass`** — catch specific exceptions and log via structured `logging`.
6. ❌ **NO `os.path.join` with user-controlled paths without `safe_path()`** (`resolved.is_relative_to(base.resolve())`) and strict regex validation on `asset_id` / `store_id` / `article`.
7. ❌ **NO secrets in URLs or API responses** — Gemini key goes in `x-goog-api-key` header; `GET /api/system/keys` returns only `{configured: bool, masked: str}`.
8. ❌ **NO Base64 in DOM, `localStorage`, or S3 `meta.json`** — use `/api/assets/{id}/preview` URLs and `URL.createObjectURL` (with `revokeObjectURL`).
9. ❌ **NO source files > 400 LOC** (enforced by automated architecture guard test!).
10. ❌ **In React Photo Studio:** `Cropper.js` must be encapsulated in `StudioEngine` with guaranteed `cropper.destroy()` in `useEffect` cleanup; Undo/Redo stores **JSON parameter diffs only** (~200 bytes), never image blobs.

---

## 📁 3. Target Project Structure

```text
bookinistic/
├── pyproject.toml                       # Dependencies, ruff, mypy, pytest config
├── app.py                               # Entrypoint (uvicorn.run(create_app(), ...))
├── run.sh / start.command               # One-click launch scripts
├── backend/
│   ├── main.py                          # create_app(), lifespan, Composition Root
│   ├── config/
│   │   ├── settings.py                  # Pydantic BaseSettings (0 import-time side effects)
│   │   └── store_context.py             # StoreContext, StoreRegistry (credentials/stores.json)
│   ├── domain/                          # 0 external dependencies! stdlib only
│   │   ├── enums.py                     # PhotoRole, BookCondition, AssetStatus, BookEra, OzonSyncStatus, FieldSource
│   │   ├── value_objects.py             # Article, Isbn, Ean13, Dimensions, Price
│   │   ├── models.py                    # Book, Asset, WorkspaceTab, OutboxItem, EnrichmentCandidate
│   │   ├── rules.py                     # Single-source GOST physics, condition, warning, era, canonical filenames
│   │   ├── exceptions.py                # DomainError, ValidationError, ArticleConflictError, ConcurrencyError
│   │   └── ports.py                     # Protocols: IUnitOfWork, IBookRepo, IAssetRepo, IMediaStorage, ...
│   ├── application/                     # Imports ONLY from domain/
│   │   ├── jobs/
│   │   │   ├── job_manager.py           # CPU pool (2) + IO pool (8) + deduplication + cancellation
│   │   │   └── sse_broker.py            # Pub/Sub broker for SSE (/api/events/stream)
│   │   └── use_cases/
│   │       ├── save_book.py             # Pre-validate -> SQLite -> Vault -> S3 CopyObject -> Excel -> Outbox
│   │       ├── recognize_book.py        # Barcode lookup -> Gemini 1200px -> FantLab + FieldProvenance
│   │       ├── asset_pipeline.py        # Upload -> selective rembg -> transform -> S3 staging
│   │       ├── reopen_book.py           # Restore book from Vault/DB/S3 into a workspace tab
│   │       ├── sync_catalog.py          # Incremental Smart Sync (batch=50, per-item catch)
│   │       └── cleanup_storage.py       # Transactional cleanup of ARCHIVED+S3 assets only
│   ├── channels/
│   │   ├── base.py                      # Protocol IMarketplaceChannel (future Avito/YM/Meshok)
│   │   └── ozon/
│   │       ├── gateway.py               # httpx + tenacity + TokenBucket (v3/info/list, v1/pictures/import)
│   │       ├── mapper.py                # Book <-> Ozon attributes + cached Ozon dictionaries
│   │       ├── validator.py             # Instant Ozon pre-validation (5 ms)
│   │       ├── outbox_worker.py         # Background marketplace_outbox worker + task_id poller -> SSE
│   │       └── excel_exporter.py        # lxml OpenXML DOM exporter (O(N), fcntl.flock, SheetSchema)
│   ├── infrastructure/
│   │   ├── persistence/
│   │   │   ├── sqlite_uow.py            # SqliteUnitOfWork + migrations (PRAGMA user_version) + FTS5
│   │   │   ├── book_repo.py             # BookRepo + WorkspaceTabRepo + Sequences
│   │   │   ├── asset_repo.py            # AssetRepo (Optimistic Locking via version)
│   │   │   ├── reference_repo.py        # ReferenceBrands (pre-seeded 397 brands) + autocomplete
│   │   │   └── backup_service.py        # Store-scoped S3 backups/db/{store_id}/ + WAL-safe restore
│   │   ├── media/
│   │   │   ├── render_pipeline.py       # Unified Pillow render (EXIF, float rotate+white, crop, 8 filters)
│   │   │   ├── rembg_processor.py       # Locked Singleton u2net (PIL direct, alpha>24, raw_img mask)
│   │   │   ├── barcode_scanner.py       # Fast local EAN-13/ISBN detector on cover_back
│   │   │   └── vault_store.py           # books_vault/{article}/ + atomic manifest.json + Streaming ZIP
│   │   ├── cloud/
│   │   │   └── yandex_s3.py             # Two-tier S3 (staging -> CopyObject -> books/{store_id}/{article}/)
│   │   ├── ai/
│   │   │   ├── gemini_client.py         # httpx + x-goog-api-key + 1200px + thinking-safe JSON parser
│   │   │   └── enrichment_clients.py    # FantLab (30d cache, max 5 parallel) + OpenLibrary (\bпо\b fix)
│   │   └── network/
│   │       └── tunnel_manager.py        # PID-scoped cloudflared (no pkill -9, no 15s lock hold)
│   └── presentation/
│       ├── middleware/
│       │   └── security.py              # Zero-Trust (Localhost vs Tunnel+QR Token), Safe Path, CORS
│       ├── schemas/                     # Pydantic v2 Request/Response DTOs
│       └── routers/                     # books, tabs, assets, ai, ozon, mobile, system, events(SSE), proxy
├── frontend/                            # Vite + React 19 + TypeScript + Zustand + local Tailwind
│   ├── package.json
│   ├── vite.config.ts                   # Multi-page build: index.html (Desktop) + mobile.html (Mobile PWA)
│   ├── src/
│   │   ├── shared/
│   │   │   ├── api/                     # Generated OpenAPI client + typed fetch + AbortController
│   │   │   ├── sse/                     # EventSource client with auto-reconnect
│   │   │   └── types/                   # Generated from FastAPI /openapi.json
│   │   ├── desktop/
│   │   │   ├── store/                   # Zustand slices: workspaceStore, poolStore, studioStore, systemStore
│   │   │   ├── features/
│   │   │   │   ├── photo-pool/          # Pool strip, 5 slots, Drag&Drop, context-aware ShortcutManager
│   │   │   │   ├── photo-studio/        # StudioEngine (Cropper.js + Canvas + Diff-Undo + 8 filters + true Esc)
│   │   │   │   ├── book-form/           # 40-field form + Autocomplete + FantLab Diff Badge + Ozon Validation
│   │   │   │   ├── session-tabs/        # SQLite-backed tabs + instant PATCH
│   │   │   │   ├── catalog-table/       # Catalog table + FTS5 search + live Outbox badges + Re-open
│   │   │   │   ├── barcode-label/       # SVG EAN-13 + storage_location (58×40 mm thermal print)
│   │   │   │   └── settings-modals/     # Single SettingsModal (no duplicate IDs!) + QR token rotation
│   │   │   └── App.tsx
│   │   └── mobile/
│   │       ├── db/                      # IndexedDB Blob & book storage (idb)
│   │       ├── features/
│   │       │   ├── capture/             # Camera + Gallery + client resize (canvas.width=0 cleanup)
│   │       │   ├── role-tagger/         # Fullscreen 1-tap 5-role express tagger
│   │       │   ├── book-organizer/      # "+ Next Book" + Touch Drag&Drop (@dnd-kit)
│   │       │   └── uploader/            # Binary multipart/form-data + idempotent retries + QR token
│   │       └── MobileApp.tsx
│   └── dist/                            # Built static bundle served by FastAPI
└── tests/
    ├── unit/                            # Pure domain, Use Cases with fakes, architecture guard tests (<1s)
    ├── integration/                     # SQLite UoW/FTS5, OpenXML DOM, FastAPI TestClient, Security tests
    └── live/                            # Strictly pytest -m live (test_store 2727930 only!)
```

---

## 🗄️ 4. Reference SQLite Schema (`PRAGMA user_version = 1`)

Each store database (`storage/stores/{store_id}/catalog.db`) uses this unified schema:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- 1. Books (both finalized catalog and active workspace drafts with status='DRAFT')
CREATE TABLE IF NOT EXISTS books (
    article          TEXT PRIMARY KEY COLLATE NOCASE,
    title            TEXT NOT NULL DEFAULT '',
    author           TEXT NOT NULL DEFAULT 'не указан',
    year             INTEGER,
    price            REAL,
    template_mode    TEXT NOT NULL DEFAULT 'pre2011',   -- 'pre2011' | 'post2011'
    status           TEXT NOT NULL DEFAULT 'DRAFT',     -- 'DRAFT' | 'SAVED' | 'PUBLISHED' | 'MODERATION_ERROR'
    storage_location TEXT NOT NULL DEFAULT '',          -- Shelf / Box / Bin
    data_json        TEXT NOT NULL DEFAULT '{}',        -- Full Book model + field_sources + suggestions
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
CREATE INDEX IF NOT EXISTS idx_books_mode ON books(template_mode);

-- Full-text search FTS5 (< 2 ms across 50,000 books)
CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    article, title, author, publisher, series, isbn,
    content='books', content_rowid='rowid'
);

-- 2. Active workspace tabs (replaces session_draft.json)
CREATE TABLE IF NOT EXISTS workspace_tabs (
    id               TEXT PRIMARY KEY,                  -- tab_xxxx
    book_article     TEXT NOT NULL REFERENCES books(article) ON DELETE CASCADE,
    tab_order        INTEGER NOT NULL DEFAULT 0,
    is_active        INTEGER NOT NULL DEFAULT 0,
    is_edit_mode     INTEGER NOT NULL DEFAULT 0,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Unified Asset Registry (Photo Engine V3)
CREATE TABLE IF NOT EXISTS assets (
    id                TEXT PRIMARY KEY,                 -- ast_xxxxxxxxxx
    book_article      TEXT REFERENCES books(article) ON DELETE SET NULL,
    slot              TEXT,                             -- cover_front | cover_back | info_pages | illustrations | mantra_defects
    slot_order        INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'UPLOADED', -- UPLOADED | AI_PROCESSING | READY | S3_SYNCED | ARCHIVED | ERROR
    status_message    TEXT NOT NULL DEFAULT '',
    original_path     TEXT NOT NULL,
    preview_path      TEXT NOT NULL,
    ai_white_path     TEXT,
    transformations   TEXT NOT NULL DEFAULT '{}',       -- JSON: {crop, rotation, filters, use_ai_white}
    render_hash       TEXT NOT NULL DEFAULT '',         -- SHA-256 of current rendered output
    s3_staging_url    TEXT,
    s3_final_url      TEXT,
    s3_uploaded_hash  TEXT,                             -- Hash of last uploaded S3 version
    version           INTEGER NOT NULL DEFAULT 1,       -- Optimistic Locking
    width             INTEGER NOT NULL DEFAULT 0,
    height            INTEGER NOT NULL DEFAULT 0,
    file_size_bytes   INTEGER NOT NULL DEFAULT 0,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_assets_book ON assets(book_article);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);

-- 4. Atomic article counters (no 10000 ceiling, no TOCTOU race)
CREATE TABLE IF NOT EXISTS sequences (
    name             TEXT PRIMARY KEY,
    next_val         INTEGER NOT NULL
);

-- 5. Marketplace Transactional Outbox
CREATE TABLE IF NOT EXISTS marketplace_outbox (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    channel          TEXT NOT NULL DEFAULT 'ozon',
    book_article     TEXT NOT NULL REFERENCES books(article) ON DELETE CASCADE,
    action           TEXT NOT NULL,                     -- 'publish_or_update' | 'update_pictures' | 'update_prices'
    status           TEXT NOT NULL DEFAULT 'QUEUED',    -- QUEUED | SENDING | MODERATION | PUBLISHED | ERROR
    external_task_id TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_retry_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_error       TEXT NOT NULL DEFAULT '',
    error_fields     TEXT NOT NULL DEFAULT '[]',        -- JSON list of Ozon error fields
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON marketplace_outbox(status, next_retry_at);

-- 6. Reference brands & external enrichment cache (FantLab / OpenLibrary / Ozon dictionaries)
CREATE TABLE IF NOT EXISTS reference_brands (
    name             TEXT PRIMARY KEY COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS enrichment_cache (
    cache_key        TEXT PRIMARY KEY,
    provider         TEXT NOT NULL,                     -- 'fantlab' | 'openlibrary' | 'ozon_dict'
    payload_json     TEXT NOT NULL,
    expires_at       INTEGER NOT NULL
);
```

---

## 🛠️ 5. Step-by-Step Execution Plan (28 Atomic Steps)

> **Execution Protocol:** Execute strictly in order (`Phase 1 → Phase 8`). After each step, run its verification command and commit cleanly to `v2-architecture`.

---

### PHASE 1. Branch Setup, Config & Pure Domain Core (`backend/domain/`)

* **Step 1.1 — Git branch & `pyproject.toml`**
  * Create branch `git checkout -b v2-architecture`.
  * Create `pyproject.toml` with all actual dependencies (`fastapi`, `uvicorn[standard]`, `python-multipart`, `pydantic>=2.6`, `pydantic-settings`, `httpx`, `tenacity`, `lxml`, `boto3`, `Pillow`, `rembg`, `opencv-python-headless`, `numpy`, dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`) and update `requirements.txt`.
  * **Verify:** `pip install -e ".[dev]"` and `ruff --version && mypy --version && pytest --version`.

* **Step 1.2 — Configuration & Multi-Store `StoreContext`**
  * Implement `backend/config/settings.py` (`AppSettings` via `pydantic-settings`, 0 import-time side effects, configurable Gemini model cascade, NO monkey-patching).
  * Implement `backend/config/store_context.py`: immutable `StoreContext`, `StoreRegistry` (reads `credentials/stores.json` + backwards-compatible `ozon_primary.json`/`ozon_test.json`), strict `store_id` regex `^[A-Za-z0-9_-]{1,32}$`, and `safe_path(base, rel)`.
  * **Verify:** `pytest tests/unit/test_config.py` (profile switch updates all paths, `.env` does not block `switch_profile`, `safe_path` blocks `../`).

* **Step 1.3 — Domain Enums, Value Objects & Exceptions**
  * Create `backend/domain/enums.py` (`PhotoRole` supporting `info_pages`, `illustrations`, `mantra_defects`, `BookCondition`, `AssetStatus`, `BookEra`, `OzonSyncStatus`, `FieldSource`).
  * Create `backend/domain/value_objects.py`: `Article`, `Isbn` (ISBN-10 with `'X'` and ISBN-13 checksum validation, rejecting fake `"978-5-0000-0000-0"`), `Ean13` (preserving `297847` prefix), `Dimensions` (`Optional[int]` + safe parser for `"130.5"`/`""`), `Price`.
  * Create `backend/domain/exceptions.py`.
  * **Verify:** `pytest tests/unit/test_value_objects.py` (including all edge cases from `test_hardcore_audit.py`).

* **Step 1.4 — Unified Domain Rules (`domain/rules.py`), Models (`domain/models.py`) & Ports (`domain/ports.py`)**
  * Consolidate into `backend/domain/rules.py`:
    * `resolve_book_era(year)`: `<= 2010` or `None` → `PRE2011`, `>= 2011` → `POST2011`.
    * `calculate_physical_dimensions(...)`: **single** physics formula with paper density and all 12 Soviet format dimensions (fixing the dust-jacket `"суперобложка"` softcover bug).
    * `calculate_book_condition(...)` and `format_annotation_with_warning(...)` (handles manual `"Хорошая"`/`"Удовлетворительная"` and empty annotation).
    * `clean_publisher_name(...)` (word-boundary `\b` fix so `"Идея-Пресс"` is not mangled), `normalize_author_name(...)` (`"не указан"`), `normalize_genre(...)`, `get_canonical_photo_filename(...)`, `classify_filename_to_slot(...)` (token-boundary matching instead of raw `"card"`/`"back"` substrings).
  * Create `backend/domain/models.py` (`Book` with `field_sources: dict[str, FieldSource]`, `storage_location`, `Asset`, `WorkspaceTab`, `OutboxItem`, `EnrichmentCandidate`).
  * Create `backend/domain/ports.py` with `Protocol` interfaces for all external adapters.
  * **Verify:** `pytest tests/unit/test_domain_rules.py` + `tests/unit/test_architecture_guards.py` (verifies 0 external imports in `domain/` and <= 400 LOC per file).

---

### PHASE 2. SQLite Persistence & S3 Backup (`backend/infrastructure/persistence/`)

* **Step 2.1 — `SqliteUnitOfWork` & Versioned Migrations**
  * Implement `backend/infrastructure/persistence/sqlite_uow.py`: context manager guaranteeing `conn.close()` in `finally`, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, single-run `PRAGMA user_version` migrations (`books`, `books_fts` + sync triggers, `workspace_tabs`, `assets`, `sequences`, `marketplace_outbox`, `reference_brands`, `enrichment_cache`).
  * Support seamless non-destructive migration of existing `storage/catalog.db` and `storage/stores/*/catalog.db` (preserving all 1,796+ existing books while populating `books_fts`, `sequences`, and `reference_brands`).
  * **Verify:** `pytest tests/integration/test_sqlite_uow.py` (no FD leak after 500 queries, migration test on a copy of real DB).

* **Step 2.2 — Repositories (`book_repo.py`, `asset_repo.py`, `reference_repo.py`)**
  * `SqliteBookRepository`: CRUD, FTS5 search `< 2 ms`, `workspace_tabs` management, atomic next-article allocation from `sequences` inside `BEGIN IMMEDIATE` (no `10000` ceiling!).
  * `SqliteAssetRepository`: CRUD + **Optimistic Locking** (`UPDATE assets SET ..., version = version + 1 WHERE id = ? AND version = ?` raising `ConcurrencyError`).
  * `SqliteReferenceRepository`: pre-seeded with 397 verified Ozon brands on empty store, fast autocomplete & canonicalization without O(N²) full-table JSON scans.
  * **Verify:** `pytest tests/integration/test_repositories.py` (concurrent article allocation + Optimistic Locking race test).

* **Step 2.3 — Store-Scoped Cloud Backup & WAL-Safe Restore**
  * Implement `backend/infrastructure/persistence/backup_service.py`: debounced `sqlite3.backup()` uploaded strictly to `backups/db/{store_id}/catalog_latest.db` and `history/{date}.db`; restore cleans `-wal`/`-shm`, restores to temp file, runs `PRAGMA integrity_check`, and swaps atomically.
  * **Verify:** `pytest tests/integration/test_backup_restore.py` (verifies store isolation between `870997` and `2727930` and WAL integrity).

---

### PHASE 3. Unified Media Pipeline (Photo Engine V3) & Two-Tier Yandex S3

* **Step 3.1 — `ImageRenderPipeline`, `RembgImageProcessor` & `BarcodeScanner`**
  * `backend/infrastructure/media/render_pipeline.py`: single Pillow pipeline (`with Image.open(...)`: `exif_transpose` → `rotate(float, expand=True, fillcolor=(255,255,255))` → clamped `crop` → all 8 filters `whiten`, `brightness`, `contrast`, `saturation`, `highlights`, `shadows`, `warmth`, `sharpness` → JPEG Q90) + `render_hash` (SHA-256).
  * `backend/infrastructure/media/rembg_processor.py`: `u2net` session guarded by `threading.Lock`, direct `PIL.Image` input/output (no intermediate JPEG/PNG round-trip), `alpha > 24` noise threshold before `getbbox()`, OpenCV white-cover protection compositing from original `raw_img`.
  * `backend/infrastructure/media/barcode_scanner.py`: fast local EAN-13/ISBN scanner on `cover_back` (with graceful fallback if optional decoder is absent).
  * **Verify:** `pytest tests/integration/test_media_pipeline.py` (1.5° rotation has white corners, RGBA PNG succeeds, no PIL leaks).

* **Step 3.2 — Local Archive `VaultStore` (`books_vault/{article}/`)**
  * `backend/infrastructure/media/vault_store.py`: stores strictly under `{vault_dir}/{article}/` (no mutable `title` in path!), atomic `manifest.json` (no Base64!), canonical `raw_sources/`, streaming Ozon ZIP (excluding `info_page_*` and `raw_sources/`, no full-RAM buffering).
  * **Verify:** `pytest tests/integration/test_vault_store.py` (title rename never creates duplicate folders; ZIP excludes `raw_sources` and `info_page`).

* **Step 3.3 — Two-Tier `YandexS3Adapter`**
  * `backend/infrastructure/cloud/yandex_s3.py`: locked `boto3` client (zero monkey-patching!):
    * `upload_staging(store_id, asset_id, render_hash, data)` → `staging/{store_id}/{asset_id}_{sha8}.jpg`.
    * `promote_to_book(store_id, article, canonical_name, staging_key, sha8)` → server-side `copy_object` to `books/{store_id}/{article}/{stem}_{sha8}.jpg` (~30 ms, 0 upload bandwidth).
    * `ensure_static_card()` → single shared `static/99_card.jpg`.
    * Parallel uploads/copies via `ThreadPoolExecutor(max_workers=6)`, clean ASCII URLs.
  * **Verify:** `pytest tests/unit/test_yandex_s3.py` (mocked `boto3`, verifies `copy_object`, `render_hash` dedup, and Ozon 14-photo cap with `99_card.jpg` last).

---

### PHASE 4. External Clients: Gemini Vision, FantLab/OpenLibrary, Ozon Channel & OpenXML DOM

* **Step 4.1 — `GeminiVisionClient` & `EnrichmentClients`**
  * `backend/infrastructure/ai/gemini_client.py`: unified `httpx.Client` + `tenacity` (retry 429/503, fail-fast `API_KEY_INVALID`), key in `x-goog-api-key` header, auto-resize to `1200px` + `exif_transpose`, thinking-safe response part extraction, configurable model cascade from `AppSettings`.
  * `backend/infrastructure/ai/enrichment_clients.py`: `FantLabClient` (30-day `enrichment_cache`, max 5 parallel detail fetches, strict illustrator role check excluding cover designers, Cyrillic `'х'` in `format_mm`, `";"` author delimiter) + `OpenLibraryClient` (`\bпо\b` word-boundary fix).
  * **Verify:** `pytest tests/unit/test_ai_and_enrichment.py` (thinking parts, `RECITATION` retry, 1200px resize, Russian author `"Полевой"` skipped by OpenLibrary, exact vs fuzzy FantLab).

* **Step 4.2 — Ozon Channel Module (`backend/channels/ozon/`)**
  * `backend/channels/base.py`: `Protocol IMarketplaceChannel` (`validate`, `publish_or_update`, `check_status`, `export_file`).
  * `backend/channels/ozon/gateway.py`: `httpx` + `tenacity` + Token Bucket rate-limiter; **current endpoints**: `/v3/product/list`, `/v3/product/info/list` (replacing removed `/v2/product/info`), `/v4/product/info/attributes` (strictly chunked by **50**!), `/v3/product/import`, `/v1/product/attributes/update`, `/v1/product/pictures/import`, `/v2/product/pictures/info`, `/v1/product/import/prices`, `/v1/product/import/info`, `/v1/description-category/attribute/values`.
  * `backend/channels/ozon/mapper.py` + `validator.py`: symmetric mapping of all fields (`illustrator`, `paper_type`, `country`, `book_type`, `language`, cached Ozon genre dictionary), unified `<= 2010` / `>= 2011` boundary, **no** hardcoded `"Советский писатель"` fallback, instant pre-validation (~5 ms) returning `{field: error_msg}`.
  * **Verify:** `pytest tests/unit/test_ozon_channel.py`.

* **Step 4.3 — Pure `OpenXmlDomExporter` (Zero Regex!)**
  * `backend/channels/ozon/excel_exporter.py`: declarative `SheetSchema` for `pre2011` and `post2011`, XML parsing & serialization strictly via **`lxml.etree` DOM** preserving all template namespaces, XML 1.0 control-char stripping, strict numeric `<v>` validation, `fcntl.flock` + `RLock`, **single-pass `O(N)` rebuild** from authoritative DB state, atomic `.tmp → .xlsx`.
  * **Verify:** `pytest tests/integration/test_excel_exporter.py` (special chars `<>&\1\x07`, row delete/update, validation against real `.xlsx` templates in `templates/`).

---

### PHASE 5. Application Layer (Use Cases, `JobManager`, `OzonOutboxWorker`, `SSEBroker`)

* **Step 5.1 — `SSEBroker`, `JobManager` & `OzonOutboxWorker`**
  * `backend/application/jobs/sse_broker.py`: thread-safe pub/sub pushing typed events (`mobile.batch_received`, `asset.updated`, `ai.progress`, `ozon.status_changed`, `sync.progress`).
  * `backend/application/jobs/job_manager.py`: `cpu_pool(max_workers=2)` + `io_pool(max_workers=8)`, `job_key` deduplication, cancellation, progress tracking.
  * `backend/channels/ozon/outbox_worker.py`: background `marketplace_outbox` worker with exponential backoff and `task_id` moderation polling (`PUBLISHED` / `MODERATION_ERROR` + `error_fields`).
  * **Verify:** `pytest tests/unit/test_jobs_and_outbox.py`.

* **Step 5.2 — 6 Pure Use Cases (Depending ONLY on `domain/ports.py`)**
  1. `AssetPipelineUseCase`: binary upload → SQLite `Asset` → selective background `rembg` (covers only) → non-destructive `transform` (Optimistic Locking) → proactive S3 `staging` upload by `render_hash`.
  2. `RecognizeBookUseCase`: strict `PhotoRole.is_ai_vision_candidate` filter → local barcode DB lookup → Gemini Vision `1200px` → FantLab (`exact` fills authoritative fields, `fuzzy` goes to `suggestions`) → merge via `FieldProvenance` (never overwrites `USER_MANUAL`!) → reference canonicalization.
  3. `SaveBookUseCase`: single entrypoint for "💾 Сохранить" (Ozon pre-validation → atomic SQLite + `VaultStore` + `S3 CopyObject` + `OpenXmlDomExporter` + `marketplace_outbox` enqueue → `< 0.2s` response).
  4. `ReopenBookUseCase`: restores catalog book into `workspace_tabs` from `books_vault/{article}/manifest.json` or S3.
  5. `SyncCatalogUseCase`: incremental Ozon → S3 → SQLite sync (strictly `batch=50`, checks both `main` and `add_photo_urls`, per-item error isolation, pinned `store_id`, patches photo URLs only).
  6. `CleanupStorageUseCase`: transactional cleanup deleting temp files only for `ARCHIVED` assets with `s3_final_url` not linked to active `workspace_tabs`.
  * **Verify:** `pytest tests/unit/test_use_cases.py` (100% offline with In-Memory port fakes in `< 0.5s`).

---

### PHASE 6. FastAPI Presentation Layer, Zero-Trust Security & Cloudflare Tunnel

* **Step 6.1 — `CloudflareTunnelManager` & `SecurityMiddleware`**
  * `backend/infrastructure/network/tunnel_manager.py`: PID-scoped `cloudflared` management (no `pkill -9`!), non-blocking `_lock`, closed sockets, clean `network_watchdog`.
  * `backend/presentation/middleware/security.py`: CSPRNG session token (with QR rotation), enforces that non-loopback / `CF-Connecting-IP` requests can access **ONLY** `/mobile`, `/assets/mobile/*`, `/api/mobile/*`, and `/api/health` with a valid token (everything else → `403 Forbidden`). Strict CORS for `localhost:8095`.
  * **Verify:** `pytest tests/integration/test_security.py` (tests `/static/../.env`, `/api/assets/delete` with `../../`, `/api/open_guide?name=start.command`, `/api/image_proxy?url=http://127.0.0.1`, external `/api/books` without token → all blocked).

* **Step 6.2 — FastAPI Routers, Pydantic DTOs, SSE & Composition Root (`backend/main.py`)**
  * Implement routers in `backend/presentation/routers/`:
    * `bootstrap.py`: `GET /api/bootstrap` (references, GOST formats, defaults, active store, open tabs).
    * `tabs.py`: `GET/POST/PATCH/DELETE /api/tabs/*` (SQLite draft tabs).
    * `books.py`: `POST /api/books/save`, `POST /api/books/validate`, `POST /api/books/reopen`, `GET /api/books/catalog` (FTS5), `DELETE /api/books/{article}`.
    * `assets.py`: `POST /api/assets/upload` (binary `UploadFile`), `POST /api/assets/{id}/assign`, `PATCH /api/assets/{id}/transform`, `POST /api/assets/{id}/run-ai`, `DELETE /api/assets/{id}`, `GET /api/assets/{id}/{preview|full}`.
    * `ai.py`: `POST /api/ai/recognize`, `POST /api/ai/apply-suggestion`, `POST /api/ai/classify-batch`.
    * `mobile.py`: `POST /api/mobile/upload-chunk` (binary `multipart` + idempotent `(session_id, chunk_index)` + `role` + `book_index`), `POST /api/mobile/commit`.
    * `ozon.py`: `GET /api/ozon/status`, `POST /api/ozon/switch-profile`, `POST /api/ozon/retry/{article}`, `POST /api/ozon/import`, `POST /api/sync/smart-s3`.
    * `system.py`: `GET /api/health`, `GET /api/system/keys` (masked only!), `POST /api/system/cleanup`, `GET /api/system/excel/download`, `GET /api/system/photos-zip`, `POST /api/system/open-folder` (`127.0.0.1` + allowlist only!).
    * `proxy.py`: `GET /api/image-proxy` (domain allowlist `storage.yandexcloud.net`/`*.ozone.ru`, private IP block, `Content-Type: image/*`, 20 MB cap).
    * `events.py`: `GET /api/events/stream` (`StreamingResponse` `text/event-stream`).
  * Update `app.py` to `uvicorn.run(...)` with `lifespan` (`rembg` warmup, `OzonOutboxWorker`, `CloudflareTunnelManager`, clean `SIGINT`/`SIGTERM` shutdown).
  * **Verify:** `pytest tests/integration/test_api_contract.py` + export `openapi.json`.

---

### PHASE 7. Frontend 2.0 (Vite + React 19 + TypeScript + Zustand + Local Tailwind)

* **Step 7.1 — Initialize `frontend/` & Generate OpenAPI Types**
  * Configure `frontend/package.json` (`react`, `react-dom`, `zustand`, `tailwindcss`, `cropperjs`, `@dnd-kit/core`, `@dnd-kit/sortable`, `idb`, `qrcode`, dev: `vite`, `typescript`, `vitest`, `openapi-typescript`).
  * Configure `vite.config.ts` multi-page build (`index.html` Desktop + `mobile.html` Mobile PWA) outputting to `frontend/dist/` + dev proxy `/api` → `http://127.0.0.1:8095`.
  * Generate `src/shared/types/api.d.ts` from FastAPI `/openapi.json`; implement typed `apiClient.ts` (`AbortController`, safe header merge) and `sseClient.ts` (`EventSource`).
  * **Verify:** `npm run typecheck && npm run build`.

* **Step 7.2 — Mobile Capture PWA (`frontend/src/mobile/`)**
  * `db/mobileDb.ts`: `IndexedDB` (`idb`) persistence for books and binary `Blob` frames (survives iOS Safari tab suspension).
  * `features/capture/`: camera + gallery batch + client resize via `createImageBitmap` → `1600px` JPEG Q0.82 with `canvas.width = 0` cleanup and `URL.revokeObjectURL`.
  * `features/book-organizer/`: `"+ След. книга"` incremental flow + touch Drag&Drop between books (`@dnd-kit`).
  * `features/role-tagger/`: fullscreen 1-tap 5-role express tagger (`cover_front`, `cover_back`, `info_pages`, `mantra_defects`, `illustrations`) with instant advance.
  * `features/uploader/`: binary `FormData` (`multipart/form-data`) chunks of 2 with `X-Mobile-Token`, idempotent `(session_id, chunk_index)`, `AbortController` timeout, 3× retry, mutation lock during upload, haptic feedback, and `IndexedDB` wipe only after `commit` ack.
  * **Verify:** `npm run test` + verify offline-capable `frontend/dist/mobile.html` (zero external CDNs).

* **Step 7.3 — Desktop Core Store, Tabs, Photo Pool & Book Form**
  * Implement Zustand stores (`workspaceStore`, `poolStore`, `systemStore`) hydrated from `GET /api/bootstrap`, subscribed to `SSE`, with debounced `PATCH /api/tabs/{id}`.
  * `features/photo-pool/`: pool strip, 5 slots, auto-placement from mobile role tags, context-aware `ShortcutManager` (`POOL` / `STUDIO` / `MODAL` / `INPUT` — keys `1-5` and `Delete` never fire behind open Studio/Modals).
  * `features/book-form/`: 40-field form with granular Zustand selectors, autocomplete from `reference_brands`/`authors` (inner scroll never closes menu), `storage_location` field, FantLab comparison badge, **single "💾 Сохранить" button** with instant Ozon pre-validation highlights and live Outbox status badge.
  * `features/barcode-label/`: pure SVG EAN-13 + `storage_location` for 58×40 mm thermal printing.
  * **Verify:** `npm run typecheck && npm run test`.

* **Step 7.4 — Modular Photo Studio (`features/photo-studio/`), Catalog & Settings**
  * `StudioEngine.ts` (isolated TS class): `Cropper.js` wrapper with guaranteed `destroy()` in `useEffect` cleanup, 4 presets + 8 synchronized sliders, straighten ruler, `3:4` / free crop toggle, `✨` (`force_rembg`), Spacebar original compare.
  * **Diff-based `HistoryStack.ts`:** stores JSON parameter diffs (`{crop, rotation, filters, useAiWhite}`) only (~200 bytes/step).
  * **Honest `Esc` / Cancel:** edits mutate local `draftTransform` and persist via `PATCH /api/assets/{id}/transform` **only** on Apply (`Enter`). Race-safe `runAi` via `AbortController` + `assetId` check.
  * `features/catalog-table/`: FTS5 search (`AbortController`), live Ozon Outbox badges, `Re-open` (`POST /api/books/reopen`), Excel/ZIP download.
  * `features/settings-modals/`: unified `SettingsModal` (no duplicate DOM IDs), disk stats + "🧹 Завершить сессию и очистить кэш", Memos, QR modal with token rotation.
  * **Verify:** `npm run typecheck && npm run test && npm run build`.

---

### PHASE 8. Final Verification, E2E & Cutover

* **Step 8.1 — Full Automated Verification Suite**
  * `ruff check backend tests` — 0 errors.
  * `mypy backend` — 0 type errors.
  * `pytest tests/unit tests/integration` — 100% pass (including all 4 former `@expectedFailure` cases from `test_hardcore_audit.py` and all security tests).
  * `cd frontend && npm run typecheck && npm run test && npm run build` — 100% pass.
  * Manual `pytest -m live` strictly against test store `2727930` with `finally` cleanup.
* **Step 8.2 — Live Smoke Check & Cutover**
  * Verify `./run.sh` and `start.command` on macOS, QR scan from phone, capturing 1 test book, Gemini + FantLab recognition, Photo Studio, save, Excel export, and Ozon Outbox.
  * Update `README.md` and `docs/TECH_STACK.md` for 2.0, then merge `v2-architecture` into `main`.

---

## 🗂️ 6. Backlog (Already Supported by 2.0 Ports)

1. **☁️ Yandex S3 Cloud Relay (no `cloudflared`):** host mobile capture page in S3 and upload directly to `staging/` via presigned URLs (immune to Cloudflare blocks). Plugs in via `IMobileTransport`.
2. **🛒 Additional Sales Channels:** `backend/channels/avito/` (XML feed), `backend/channels/yandex_market/`, `backend/channels/meshok/`, `backend/channels/telegram/` — plug in via `IMarketplaceChannel` without touching core or UI.
3. **📊 Pricing Analytics:** suggest recommended price from historical sales of similar editions in `catalog.db`.
