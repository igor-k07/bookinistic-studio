# 🏛️ Bookinistic Studio 2.0 — Финальный пошаговый план реализации (Русская версия)

> **Статус:** Утверждён (по итогам архитектурного аудита и `/grill-me`)  
> **Рабочая ветка:** `v2-architecture` (создаётся от `main`; текущий код в `main` не трогаем до финального переключения)  
> **Примечание:** Этот файл — полная русская версия для вашего контроля и понимания. Для запуска шагов простыми ИИ-моделями используйте английский оригинал [MASTER_IMPLEMENTATION_PLAN_2.0.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/MASTER_IMPLEMENTATION_PLAN_2.0.md).

---

## 📌 1. Утверждённые архитектурные решения (ADR — не менять без согласования)

| # | Область | Что утвердили |
| :-: | :--- | :--- |
| **ADR-1** | **Backend стек** | **Python 3.10+ · FastAPI · Uvicorn (ASGI) · Pydantic v2 · SSE (`/api/events/stream`) · `httpx` · `tenacity` · `lxml` · `boto3` · `Pillow` · `rembg` · `opencv-python-headless` · `SQLite 3 (WAL + FTS5)`**. Запуск одной командой `./run.sh` / `start.command` (без Docker, Redis и Celery). |
| **ADR-2** | **Frontend стек** | **Vite · TypeScript (strict) · React 19 · Zustand · локальный Tailwind CSS** (собранный `frontend/dist/` отдаёт FastAPI; для работы на Mac Node.js в рантайме не нужен). Типы API автоматически генерируются из `/openapi.json`. |
| **ADR-3** | **Архитектура** | **Гексагональная архитектура (Ports & Adapters / Clean Architecture)** с явной сборкой зависимостей (`AppContainer` + `StoreContext`). Без глобальных мутируемых синглтонов и без monkey-patching. |
| **ADR-4** | **Граница эпох (SSOT)** | Единое правило во всех слоях (Домен, БД, Excel, Ozon API, UI): **`year <= 2010` или `year is None` → `PRE2011`** (букинистика `1942-2010`, Ozon `200001485`, ISBN необязателен; `<= 1941` → антиквариат Ozon `200001486`); **`year >= 2011` → `POST2011`** (современные `с 2011`, Ozon `200001483`, ISBN обязателен). |
| **ADR-5** | **Физика ГОСТ (SSOT)** | Единственная формула габаритов и веса в `domain/rules.py` с учётом плотности бумаги (мелованная `115`, офсет `80`, типографская/пухлая `65`, газетная `50` г/м²) и таблицы 12 советских форматов. Ручные размеры защищены через `FieldProvenance`. |
| **ADR-6** | **Yandex S3 (2 уровня)** | Упреждающая загрузка в `staging/{store_id}/{asset_id}_{sha8}.jpg` (автоудаление в S3 через 7 дней) → при сохранении книги мгновенное внутриоблачное копирование (`CopyObject`) в `books/{store_id}/{article}/01_cover_front_{sha8}.jpg` + `archive/info_page_{n}_{sha8}.jpg` + лёгкий `meta.json` (без Base64). Промо-карточка — одна общая `static/99_card.jpg`. Старые ссылки в БД остаются рабочими без миграции. |
| **ADR-7** | **Сохранение и Ozon** | **Одна кнопка «💾 Сохранить»**: (1) мгновенная проверка правил Ozon (~5 мс) → (2) атомарная запись за <0.2 сек в SQLite + `books_vault/{article}/` + S3 `CopyObject` + Excel → (3) автоматическая постановка в очередь `marketplace_outbox` с фоновой отправкой в Ozon API (`/v3/product/import`, `/v1/product/attributes/update`, `/v1/product/pictures/import`, `/v1/product/import/prices`), отслеживанием `task_id` и живыми статусами через SSE. |
| **ADR-8** | **ИИ + FantLab + Приоритеты** | Приоритет источников (`FieldProvenance`): `ПУСТО(0) < ДЕФОЛТ(1) < GEMINI(2) < СПРАВОЧНИК_БД(3) < FANTLAB_ТОЧНЫЙ(4) < РУЧНОЙ_ВВОД(5)`. Локальный скан штрихкода по `catalog.db` → сжатие инфо-фото до `1200px` + `exif_transpose` → Gemini Vision (`x-goog-api-key`) → FantLab (кэш в SQLite на 30 дней): **точное совпадение** (ISBN или Название+Автор+Год+Издательство) задаёт эталонные паспортные поля, а Gemini дополняет остальное и физику экземпляра (`annotation`, `condition`, `age_limit`); **неточное совпадение** выводится бейджем-подсказкой без перезаписи. |
| **ADR-9** | **Черновики и Assets V3** | Вкладки-черновики (`books.status = 'DRAFT'` + `workspace_tabs`) и единый реестр фото (`assets` с `version` и `render_hash`) хранятся в **SQLite**. Старые `storage/inbox/`, `storage/session_photos/` и `session_draft.json` **удаляются**. Кнопка «🧹 Завершить сессию и очистить кэш» удаляет временные файлы только тех фото, которые уже в статусе `ARCHIVED` и имеют `s3_final_url`. |
| **ADR-10** | **Безопасность (Zero-Trust)** | Cloudflare Quick Tunnel открывает **ТОЛЬКО** `/mobile` и `/api/mobile/*` по секретному токену из QR-кода + запасной режим локального Wi-Fi. Десктоп, админка, БД, ключи и команды Mac доступны **строго с `127.0.0.1`**. *(В бэклоге: Yandex S3 Cloud Relay без `cloudflared` через порт `IMobileTransport`.)* |
| **ADR-11** | **Расширяемость** | Ядро `Book` универсально и содержит поле `storage_location` («Полка/Ячейка», печатается на термоэтикетке 58×40 мм). Вся специфика Ozon вынесена в `backend/channels/ozon/` (порт `IMarketplaceChannel`), чтобы легко добавлять Авито, Яндекс Маркет, Мешок или Telegram. |

---

## 🚫 2. Жёсткие запреты для исполнителей (чтобы баги не возвращались)

1. ❌ **Никакого monkey-patching** (`socket.getaddrinfo`, `urllib3.create_connection` и т.п.).
2. ❌ **Никаких голых `with sqlite3.connect(...) as conn:`** — только через `SqliteUnitOfWork`, который гарантированно закрывает соединение в `finally`.
3. ❌ **Никаких `init_db()` / создания таблиц внутри `SELECT`/`INSERT`/`UPDATE`** — миграции выполняются ровно 1 раз при запуске.
4. ❌ **Никаких регулярных выражений `re.sub` по XML** в экспорте Excel — только чистый `lxml.etree` DOM.
5. ❌ **Никаких пустых `except Exception: pass`** — только явная обработка и логирование.
6. ❌ **Никаких путей к файлам без `safe_path()`** и проверки ID регулярными выражениями.
7. ❌ **Никаких секретов в URL или ответах API** — ключ Gemini передаётся в заголовке `x-goog-api-key`, в UI отдаётся только маска ключа.
8. ❌ **Никаких Base64-строк в DOM, `localStorage` или `meta.json` на S3** — только серверные URL и `URL.createObjectURL` с очисткой.
9. ❌ **Никаких файлов длиннее 400 строк кода** (контролируется автотестом!).
10. ❌ **В React Фотостудии:** `Cropper.js` обёрнут в `StudioEngine` с обязательным `cropper.destroy()` при размонтировании; Undo/Redo хранит **только JSON-диффы параметров** (~200 байт), а не сами картинки.

---

## 📁 3. Целевая структура проекта

```text
bookinistic/
├── pyproject.toml                       # Зависимости, ruff, mypy, pytest
├── app.py                               # Точка входа (uvicorn.run)
├── run.sh / start.command               # Запуск в 1 клик
├── backend/
│   ├── main.py                          # create_app(), lifespan, сборка зависимостей
│   ├── config/
│   │   ├── settings.py                  # Настройки (Pydantic BaseSettings, без побочных эффектов)
│   │   └── store_context.py             # Изолированный контекст магазина (870997 / 2727930)
│   ├── domain/                          # 100% чистый Python (0 внешних библиотек)
│   │   ├── enums.py                     # Роли фото, состояния, статусы, эпохи, приоритет полей
│   │   ├── value_objects.py             # Article, Isbn, Ean13, Dimensions, Price
│   │   ├── models.py                    # Book, Asset, WorkspaceTab, OutboxItem, EnrichmentCandidate
│   │   ├── rules.py                     # Единая физика ГОСТ, сохранность, предупреждение, имена фото
│   │   ├── exceptions.py                # Доменные ошибки
│   │   └── ports.py                     # Интерфейсы (Protocols) для всех адаптеров
│   ├── application/                     # Сценарии использования (работают только через ports.py)
│   │   ├── jobs/
│   │   │   ├── job_manager.py           # Очереди CPU (2 воркера) + IO (8 воркеров)
│   │   │   └── sse_broker.py            # Рассылка живых событий в браузер по SSE
│   │   └── use_cases/
│   │       ├── save_book.py             # Проверка -> SQLite -> Vault -> S3 Copy -> Excel -> Outbox
│   │       ├── recognize_book.py        # Штрихкод -> Gemini 1200px -> FantLab + приоритеты полей
│   │       ├── asset_pipeline.py        # Загрузка -> выборочный rembg -> правки -> S3 staging
│   │       ├── reopen_book.py           # Открытие книги из архива обратно во вкладку
│   │       ├── sync_catalog.py          # Умная синхронизация Ozon -> S3 -> SQLite (батчи по 50)
│   │       └── cleanup_storage.py       # Безопасная очистка только завершённых фото
│   ├── channels/
│   │   ├── base.py                      # Общий интерфейс маркетплейса IMarketplaceChannel
│   │   └── ozon/
│   │       ├── gateway.py               # Клиент Ozon Seller API (актуальные методы v3/v1, retry)
│   │       ├── mapper.py                # Перевод Book <-> атрибуты Ozon + кэш словарей
│   │       ├── validator.py             # Мгновенная пред-валидация перед сохранением
│   │       ├── outbox_worker.py         # Фоновая отправка в Ozon + проверка модерации task_id
│   │       └── excel_exporter.py        # Чистый XML DOM экспортёр Excel (O(N), блокировка файла)
│   ├── infrastructure/
│   │   ├── persistence/                 # SQLite UoW, миграции, репозитории, FTS5 поиск, S3 бэкапы
│   │   ├── media/                       # Единый рендер Pillow, rembg (с Lock), сканер штрихкода, Vault
│   │   ├── cloud/                       # Two-tier Yandex S3 (staging -> CopyObject -> books/)
│   │   ├── ai/                          # Клиент Gemini (1200px) + FantLab/OpenLibrary с кэшем
│   │   └── network/                     # Менеджер Cloudflare Tunnel (по PID, без pkill -9)
│   └── presentation/                    # FastAPI middleware (Zero-Trust), Pydantic-схемы и роутеры
├── frontend/                            # Vite + React 19 + TypeScript + Zustand + локальный Tailwind
│   ├── src/shared/                      # Автогенерированные типы из OpenAPI, apiClient, sseClient
│   ├── src/desktop/                     # Store, пул фото, фотостудия (Diff-Undo), форма, каталог, QR
│   ├── src/mobile/                      # Mobile PWA: IndexedDB, камера, 5 кнопок ролей, бинарный аплоад
│   └── dist/                            # Собранная статика (отдаётся FastAPI)
└── tests/
    ├── unit/                            # Быстрые тесты домена, Use Cases и проверки архитектуры (<1с)
    ├── integration/                     # Тесты SQLite, Excel DOM, FastAPI и безопасности
    └── live/                            # Тесты живых API (строго вручную и только на тестовом магазине!)
```

---

## 🛠️ 4. Пошаговый план реализации (28 атомарных шагов)

### ФАЗА 1. Ветка, конфигурация и чистое доменное ядро
* **Шаг 1.1 — Git-ветка и `pyproject.toml`:** создать ветку `v2-architecture`, описать все реальные зависимости (включая `fastapi`, `uvicorn`, `httpx`, `tenacity`, `lxml`, `opencv-python-headless`, `ruff`, `mypy`, `pytest`).
* **Шаг 1.2 — Настройки и `StoreContext`:** `AppSettings` на `pydantic-settings` без побочных эффектов при импорте, `StoreContext` для изоляции магазинов, `safe_path()` против выхода за пределы папок.
* **Шаг 1.3 — Перечисления и Value Objects:** `PhotoRole`, `Article`, `Isbn` (проверка контрольной суммы, запрет заглушек), `Ean13` (сохранение префикса `297847`), `Dimensions` (безопасный парсинг дробных/пустых строк), `Price`.
* **Шаг 1.4 — Единые правила (`rules.py`), модели и порты:** граница `<= 2010` / `>= 2011`, единая физика ГОСТ (исправление бага суперобложки), `clean_publisher_name` (фикс «Идея-Пресс»), `FieldProvenance`, интерфейсы `ports.py`, архитектурный тест-ограничитель (<= 400 строк, 0 внешних импортов в `domain/`).

### ФАЗА 2. Хранилище SQLite и облачные бэкапы
* **Шаг 2.1 — `SqliteUnitOfWork` и миграции:** гарантированное закрытие соединений, WAL-режим, `PRAGMA user_version` миграции (таблицы `books`, `books_fts` для мгновенного поиска, `workspace_tabs` вместо `session_draft.json`, `assets`, `sequences`, `marketplace_outbox`, `reference_brands`, `enrichment_cache`). Неразрушающее обновление текущих баз `catalog.db`.
* **Шаг 2.2 — Репозитории:** CRUD книг и вкладок, FTS5-поиск (<2 мс), атомарная выдача артикулов без потолка `10000`, Optimistic Locking (`version`) для фото-ассетов, предзаполненный справочник 397 брендов Ozon.
* **Шаг 2.3 — Бэкапы БД по магазинам:** загрузка в `backups/db/{store_id}/catalog_latest.db`, безопасное восстановление с очисткой `-wal`/`-shm` и проверкой `integrity_check`.

### ФАЗА 3. Единый фото-конвейер (Photo Engine V3) и Yandex S3
* **Шаг 3.1 — `ImageRenderPipeline`, `rembg` и скан штрихкодов:** единый Pillow-рендер (EXIF, плавный поворот с белым фоном, 8 фильтров, SHA-256 `render_hash`), потокобезопасный `rembg` без лишнего перекодирования, локальный сканер EAN-13/ISBN с задней обложки.
* **Шаг 3.2 — Локальный архив `VaultStore`:** папки строго `books_vault/{article}/` (без названия книги в пути), атомарный `manifest.json` без Base64, потоковый ZIP без утечки `raw_sources/` и титулов.
* **Шаг 3.3 — Two-Tier `YandexS3Adapter`:** предзагрузка в `staging/{store_id}/` → при сохранении мгновенный `CopyObject` в `books/{store_id}/{article}/..._{sha8}.jpg` + общая `static/99_card.jpg`, параллельная загрузка, без monkey-patching.

### ФАЗА 4. Внешние интеграции: Gemini, FantLab, Ozon и Excel
* **Шаг 4.1 — `GeminiVisionClient` и `EnrichmentClients`:** `httpx` + `tenacity`, ключ в заголовке `x-goog-api-key`, сжатие фото до `1200px`, поддержка thinking-ответов, кэш FantLab на 30 дней, точный разбор иллюстраторов, фикс бага `\bпо\b` в OpenLibrary.
* **Шаг 4.2 — Канал Ozon (`channels/ozon/`):** интерфейс `IMarketplaceChannel`, актуальные методы API (`/v3/product/info/list`, `/v1/product/pictures/import`, чанкинг атрибутов строго по 50), симметричный маппинг, без фейкового бренда «Советский писатель», мгновенная пред-валидация.
* **Шаг 4.3 — Чистый `OpenXmlDomExporter`:** переписываем работу с `.xlsx` с regex на `lxml.etree` DOM, однопроходная `O(N)` пересборка из БД, блокировка `fcntl.flock` + `RLock`, санитизация XML 1.0.

### ФАЗА 5. Слой Application (Use Cases, очереди, SSE)
* **Шаг 5.1 — `SSEBroker`, `JobManager` и `OzonOutboxWorker`:** раздельные пулы CPU (2) и IO (8), дедупликация задач, фоновый воркер очереди Ozon с поллингом модерации `task_id` и рассылкой статусов в браузер.
* **Шаг 5.2 — 6 чистых Use Cases:** `AssetPipeline`, `RecognizeBook`, `SaveBook` (под одну кнопку «💾 Сохранить»), `ReopenBook`, `SyncCatalog`, `CleanupStorage` — всё через `ports.py`, с быстрыми тестами на фейках (<0.5 сек).

### ФАЗА 6. FastAPI, Zero-Trust безопасность и Cloudflare Tunnel
* **Шаг 6.1 — `CloudflareTunnelManager` и `SecurityMiddleware`:** управление туннелем по PID без `pkill -9` и блокировки на 15 сек; изоляция туннеля (снаружи доступен только `/mobile` по QR-токену, админка и Mac-команды — строго с `127.0.0.1`).
* **Шаг 6.2 — FastAPI роутеры, SSE и `app.py`:** все эндпоинты с Pydantic-валидацией, `GET /api/bootstrap`, `/api/events/stream`, безопасный `/api/image-proxy` (белый список хостов), запуск через `uvicorn.run` с чистым завершением по `SIGINT`/`SIGTERM`.

### ФАЗА 7. Новый Frontend 2.0 (Vite + React 19 + TypeScript + Zustand + Локальный Tailwind)
* **Шаг 7.1 — Инициализация и автотипы API:** multi-page сборка (`index.html` + `mobile.html`) в `frontend/dist/`, генерация типов из OpenAPI, `apiClient` с `AbortController`, `sseClient`.
* **Шаг 7.2 — Mobile Capture PWA (Шаг 6 целиком):** `IndexedDB` (кадры не теряются при сворачивании Safari), клиентское сжатие `1600px` с очисткой памяти, «+ След. книга» + тач-перенос фото между книгами, полноэкранная разметка 5 ролей в 1 тап, бинарная отправка `FormData` с ретраями и QR-токеном.
* **Шаг 7.3 — Desktop Core, вкладки, пул и форма:** Zustand-сторы, контекстный `ShortcutManager` (`1–5` не срабатывают внутри студии), форма с `storage_location` («Полка/Ячейка»), автокомплит без багов скролла, бейдж FantLab, единая кнопка «💾 Сохранить» с подсветкой ошибок Ozon и живым бейджем Outbox, SVG-этикетка 58×40 мм с полкой.
* **Шаг 7.4 — Модульная Фотостудия, Каталог и Настройки:** `StudioEngine` (`Cropper.js` с чистым `destroy()`, 4 пресета + 8 фильтров, рулетка, `3:4`, `✨`), Diff-история Undo/Redo (~200 байт/шаг), честная отмена по `Esc`, защита от гонок `runAi`, FTS5-каталог с `Re-open`, единый `SettingsModal` (без дублей ID) и кнопка «🧹 Завершить сессию и очистить кэш».

### ФАЗА 8. Финальная проверка и переключение
* **Шаг 8.1:** прогон `ruff`, `mypy`, `pytest` (unit + integration + security), `vitest` + `tsc` + `vite build` и контрольный `live`-тест на тестовом магазине `2727930`.
* **Шаг 8.2:** проверка запуска `./run.sh` / `start.command`, живая проверка съёмки с телефона через QR, обновление `README.md` и `TECH_STACK.md`, слияние `v2-architecture` в `main`.

