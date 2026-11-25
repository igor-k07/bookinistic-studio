# Bookinistic Studio 2.0 — Execution State

> Target Branch: `v2-architecture`  
> Started: 2026-11-25  
> Status: In Progress  

## Execution Checklist

- [x] **Step 1.1 — Git branch & `pyproject.toml`**
- [x] **Step 1.2 — Configuration & Multi-Store `StoreContext`**
- [x] **Step 1.3 — Domain Enums, Value Objects & Exceptions**
- [x] **Step 1.4 — Unified Domain Rules (`domain/rules.py`), Models (`domain/models.py`) & Ports (`domain/ports.py`)**
- [x] **Step 2.1 — `SqliteUnitOfWork` & Versioned Migrations**
- [x] **Step 2.2 — Repositories (`book_repo.py`, `asset_repo.py`, `reference_repo.py`)**
- [ ] **Step 2.3 — Store-Scoped Cloud Backup & WAL-Safe Restore**
- [ ] **Step 3.1 — `ImageRenderPipeline`, `RembgImageProcessor` & `BarcodeScanner`**
- [ ] **Step 3.2 — Local Archive `VaultStore` (`books_vault/{article}/`)**
- [ ] **Step 3.3 — Two-Tier `YandexS3Adapter`**
- [ ] **Step 4.1 — `GeminiVisionClient` & `EnrichmentClients`**
- [ ] **Step 4.2 — Ozon Channel Module (`backend/channels/ozon/`)**
- [ ] **Step 4.3 — Pure `OpenXmlDomExporter` (Zero Regex!)**
- [ ] **Step 5.1 — `SSEBroker`, `JobManager` & `OzonOutboxWorker`**
- [ ] **Step 5.2 — 6 Pure Use Cases (Depending ONLY on `domain/ports.py`)**
- [ ] **Step 6.1 — `CloudflareTunnelManager` & `SecurityMiddleware`**
- [ ] **Step 6.2 — FastAPI Routers, Pydantic DTOs, SSE & Composition Root (`backend/main.py`)**
- [ ] **Step 7.1 — Initialize `frontend/` & Generate OpenAPI Types**
- [ ] **Step 7.2 — Mobile Capture PWA (`frontend/src/mobile/`)**
- [ ] **Step 7.3 — Desktop Core Store, Tabs, Photo Pool & Book Form**
- [ ] **Step 7.4 — Modular Photo Studio (`features/photo-studio/`), Catalog & Settings**
- [ ] **Step 8.1 — Full Automated Verification Suite**
- [ ] **Step 8.2 — Live Smoke Check & Cutover**

## Step Execution Log
*(Entries added upon step completion)*
- 2026-11-25: Step 1.1 completed — Created branch `v2-architecture`, configured `pyproject.toml`, updated `requirements.txt`, installed dependencies into Python 3.12 venv, verified ruff/mypy/pytest.
- 2026-11-25: Step 1.2 completed — Implemented AppSettings, StoreContext, StoreRegistry, and safe_path with zero side effects; verified by unit tests, ruff, and mypy.
- 2026-11-25: Step 1.3 completed — Implemented domain enums (PhotoRole, BookCondition, AssetStatus, BookEra, OzonSyncStatus, FieldSource), value objects (Article, Isbn, Ean13, Dimensions, Price), and domain exceptions; verified by unit tests, ruff, and mypy.
- 2026-11-25: Step 1.4 completed — Implemented domain rules (era boundary, GOST physics, dust-jacket fix, publisher/author/slot normalization), models (Book, Asset, WorkspaceTab, OutboxItem, EnrichmentCandidate), ports Protocol interfaces, and automated architecture guard tests (LOC <= 400, 0 external imports); verified by unit tests, ruff, and mypy.
- 2026-11-25: Step 2.1 completed — Implemented SqliteUnitOfWork with guaranteed conn.close() in finally, WAL mode, foreign keys, and versioned non-destructive migrations preserving 2,378 existing books, FTS5 sync, and sequences; verified by integration tests, ruff, and mypy.
- 2026-11-25: Step 2.2 completed — Implemented SqliteBookRepository (FTS5 search, workspace tabs, atomic sequences without 10000 ceiling), SqliteAssetRepository (Optimistic Locking via version), and SqliteReferenceRepository (fast normalized brand autocomplete); verified by integration tests, ruff, and mypy.

