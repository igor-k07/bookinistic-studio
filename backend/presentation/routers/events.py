"""Server-Sent Events (SSE) streaming router."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["Real-time Events"])


@router.get("/stream")
async def event_stream(request: Request) -> StreamingResponse:
    """Subscribe to real-time UI notifications via Server-Sent Events (W3C text/event-stream)."""
    app_state = request.app.state
    broker = app_state.event_broker
    client_q = broker.subscribe()

    async def sse_generator() -> AsyncGenerator[str, None]:
        # Send initial keepalive comment
        yield ": ping\n\n"
        try:
            while True:
                # Disconnect detection
                if await request.is_disconnected():
                    break

                try:
                    # Non-blocking get with async sleep to keep loop cooperative
                    event = client_q.get_nowait()
                    yield event.to_sse_message()
                except Exception:
                    await asyncio.sleep(0.1)

        finally:
            broker.unsubscribe(client_q)
            logger.debug("SSE client unsubscribed cleanly")

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx/proxy response buffering
        },
    )
