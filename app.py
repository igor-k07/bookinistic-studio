"""Bookinistic Studio 2.0 — Server Entrypoint.

Starts high-performance asynchronous ASGI application powered by Uvicorn and FastAPI.
All background workers, Cloudflare tunnel, and lifespan hooks run through backend.main:app.
"""

from __future__ import annotations

import logging
import os

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bookinistic")


def main() -> None:
    port = int(os.environ.get("BOOKINISTIC_PORT", "8095"))
    logger.info("Starting Bookinistic Studio 2.0 on 0.0.0.0:%d (Desktop: http://localhost:%d)...", port, port)

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
