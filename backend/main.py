"""Bookinistic Studio 2.0 — FastAPI Composition Root & Application Entrypoint.

Architectural Guarantees:
- Composition root wiring domain ports to concrete adapters (FastAPI + SQLite + S3 + Ozon + SSE).
- Non-destructive startup migrations executed strictly once during startup.
- Full lifespan management: Rembg warmup, JobManager CPU/IO pools, Outbox worker, Cloudflare tunnel.
- Zero-Trust security perimeter middleware with CSPRNG token rotation.
- Modular sub-routers strictly decoupled by domain entity.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.application.jobs.job_manager import JobManager
from backend.application.jobs.sse_broker import SSEBroker
from backend.application.use_cases.asset_pipeline import AssetPipelineUseCase
from backend.application.use_cases.cleanup_storage import CleanupStorageUseCase
from backend.application.use_cases.recognize_book import RecognizeBookUseCase
from backend.application.use_cases.reopen_book import ReopenBookUseCase
from backend.application.use_cases.save_book import SaveBookUseCase
from backend.application.use_cases.sync_catalog import SyncCatalogUseCase
from backend.channels.ozon.excel_exporter import OpenXmlDomExporter
from backend.channels.ozon.outbox_worker import OzonOutboxWorker
from backend.config.settings import AppSettings
from backend.config.store_context import StoreRegistry
from backend.infrastructure.ai.enrichment_clients import UnifiedEnrichmentClient
from backend.infrastructure.ai.gemini_client import GeminiVisionClient
from backend.infrastructure.cloud.yandex_s3 import YandexS3Adapter
from backend.infrastructure.media.rembg_processor import RembgImageProcessor
from backend.infrastructure.media.render_pipeline import ImageRenderPipeline
from backend.infrastructure.network.tunnel_manager import CloudflareTunnelManager
from backend.infrastructure.persistence.sqlite_uow import run_migrations
from backend.presentation.middleware.security import SecurityMiddleware, SessionTokenManager
from backend.presentation.routers import (
    ai_router,
    assets_router,
    books_router,
    bootstrap_router,
    events_router,
    mobile_router,
    ozon_router,
    proxy_router,
    system_router,
    tabs_router,
)

logger = logging.getLogger(__name__)


def init_store_components(registry: StoreRegistry, app: FastAPI, cfg: AppSettings) -> None:
    """Wire concrete adapters and use cases for active store."""
    ctx = registry.get_active_context()
    ctx.ensure_dirs()

    # 1. Persistence & Migrations
    run_migrations(ctx.db_path)

    uow = ctx.uow
    book_repo = ctx.book_repo
    asset_repo = ctx.asset_repo
    ref_repo = ctx.reference_repo

    # 2. Media Vault & Cloud Adapters (using effective credentials from env/files)
    vault_store = ctx.vault_store
    s3_cfg = cfg.get_effective_s3_config() or {}
    s3_adapter = YandexS3Adapter(
        bucket=str(s3_cfg.get("bucket") or "another-piter-books1"),
        key_id=str(s3_cfg.get("key_id") or ""),
        secret_key=str(s3_cfg.get("secret_key") or ""),
        endpoint_url=str(s3_cfg.get("endpoint_url") or cfg.s3_endpoint_url),
        region_name=str(s3_cfg.get("region_name") or cfg.s3_region_name),
    )

    # 3. AI & Enrichment
    ai_client = GeminiVisionClient(api_key=cfg.get_effective_gemini_key())
    enrichment_client = UnifiedEnrichmentClient(uow=uow)

    # 4. Marketplace Channels & Exporters
    ozon_gateway = ctx.ozon_gateway
    ozon_channel = ctx.ozon_channel
    ready_dir = Path("ready_tables") if ctx.store_id == "870997" else (Path("ready_tables") / "stores" / ctx.store_id)
    excel_exporter = OpenXmlDomExporter(
        templates_dir=Path("templates"),
        ready_tables_dir=ready_dir,
        book_repo=book_repo,
    )

    # 5. Background Outbox Worker
    outbox_worker = OzonOutboxWorker(
        uow=uow,
        book_repo=book_repo,
        channel=ozon_channel,
        event_broker=app.state.event_broker,
    )

    # 6. Use Cases instantiation
    app.state.excel_exporter = excel_exporter
    app.state.asset_pipeline_use_case = AssetPipelineUseCase(
        asset_repo=asset_repo,
        media_storage=vault_store,
        cloud_storage=s3_adapter,
        event_broker=app.state.event_broker,
        render_pipeline=ImageRenderPipeline,
        rembg_processor=RembgImageProcessor,
    )
    app.state.recognize_book_use_case = RecognizeBookUseCase(
        book_repo=book_repo,
        ai_client=ai_client,
        enrichment_client=enrichment_client,
        reference_repo=ref_repo,
        event_broker=app.state.event_broker,
    )
    app.state.save_book_use_case = SaveBookUseCase(
        uow=uow,
        book_repo=book_repo,
        channel=ozon_channel,
        vault_store=vault_store,
        cloud_storage=s3_adapter,
        excel_exporter=excel_exporter,
        event_broker=app.state.event_broker,
        asset_repo=asset_repo,
        outbox_worker=outbox_worker,
    )
    app.state.reopen_book_use_case = ReopenBookUseCase(
        uow=uow,
        book_repo=book_repo,
        vault_store=vault_store,
        event_broker=app.state.event_broker,
    )
    app.state.sync_catalog_use_case = SyncCatalogUseCase(
        uow=uow,
        book_repo=book_repo,
        gateway=ozon_gateway,
        event_broker=app.state.event_broker,
    )
    app.state.cleanup_storage_use_case = CleanupStorageUseCase(
        uow=uow,
        asset_repo=asset_repo,
        book_repo=book_repo,
        media_storage=vault_store,
        event_broker=app.state.event_broker,
    )
    app.state.outbox_worker = outbox_worker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle manager."""
    logger.info("Initializing Bookinistic Studio 2.0 engine...")

    # Start background workers
    if hasattr(app.state, "outbox_worker") and app.state.outbox_worker:
        app.state.outbox_worker.start()

    if hasattr(app.state, "tunnel_manager") and app.state.tunnel_manager:
        app.state.tunnel_manager.start_tunnel()

    yield

    # Graceful shutdown
    logger.info("Shutting down Bookinistic Studio 2.0 engine...")
    if hasattr(app.state, "outbox_worker") and app.state.outbox_worker:
        app.state.outbox_worker.stop()

    if hasattr(app.state, "tunnel_manager") and app.state.tunnel_manager:
        app.state.tunnel_manager.stop_tunnel()

    if hasattr(app.state, "job_manager") and app.state.job_manager:
        app.state.job_manager.shutdown(wait=True)


def create_app(settings: Optional[AppSettings] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = settings or AppSettings()

    app = FastAPI(
        title="Bookinistic Studio 2.0 API",
        description="High-performance autonomous book cataloging engine",
        version="2.0.0",
        lifespan=lifespan,
    )

    # 1. State Container
    event_broker = SSEBroker(max_queue_size=200)
    job_manager = JobManager(cpu_workers=2, io_workers=8, event_broker=event_broker)
    token_manager = SessionTokenManager()
    tunnel_manager = CloudflareTunnelManager(
        port=cfg.port,
        pid_file=Path("storage/cloudflared.pid"),
        event_broker=event_broker,
    )
    registry = StoreRegistry(base_dir=cfg.base_dir)

    app.state.settings = cfg
    app.state.event_broker = event_broker
    app.state.job_manager = job_manager
    app.state.token_manager = token_manager
    app.state.tunnel_manager = tunnel_manager
    app.state.store_registry = registry

    # Wire domain components
    init_store_components(registry, app, cfg)

    # 2. Security Middleware
    app.add_middleware(SecurityMiddleware, token_manager=token_manager)

    # 3. Router Registration
    app.include_router(bootstrap_router)
    app.include_router(tabs_router)
    app.include_router(books_router)
    app.include_router(assets_router)
    app.include_router(ai_router)
    app.include_router(mobile_router)
    app.include_router(ozon_router)
    app.include_router(system_router)
    app.include_router(proxy_router)
    app.include_router(events_router)

    # 4. Static frontend build mount (if dist exists)
    dist_dir = Path("frontend/dist")
    if dist_dir.is_dir():
        mobile_html = dist_dir / "mobile.html"
        if mobile_html.is_file():
            from fastapi.responses import FileResponse

            @app.get("/mobile", include_in_schema=False)
            def serve_mobile_pwa() -> FileResponse:
                return FileResponse(str(mobile_html), media_type="text/html")

        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return app


# Default ASGI callable
app = create_app()
