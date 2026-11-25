"""Secure streaming image proxy with domain allowlist, SSRF defenses, and 20MB limit."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from backend.presentation.middleware.security import is_private_or_forbidden_host

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Proxy"])

ALLOWED_DOMAINS = (
    "storage.yandexcloud.net",
    "ozone.ru",
    "ozon.ru",
    "ozonusercontent.com",
)
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB cap


@router.get("/image-proxy")
async def proxy_image(url: str = Query(...)) -> Response:
    """Stream remote image securely to UI without CORS or SSRF vulnerabilities."""
    # 1. SSRF and Private Subnet Check
    if is_private_or_forbidden_host(url):
        raise HTTPException(status_code=403, detail="Forbidden target address")

    # 2. Domain Allowlist Check
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    domain_allowed = any(
        hostname == allowed or hostname.endswith(f".{allowed}")
        for allowed in ALLOWED_DOMAINS
    )
    if not domain_allowed:
        logger.warning("Attempted proxy to non-allowlisted domain: %s", hostname)
        raise HTTPException(status_code=403, detail="Domain not permitted for proxying")

    # 3. Stream Remote Image via httpx with 20MB Limit
    try:
        client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        req = client.build_request("GET", url)
        r = await client.send(req, stream=True)

        if r.status_code != 200:
            await client.aclose()
            raise HTTPException(status_code=r.status_code, detail="Remote server error")

        content_type = r.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            await client.aclose()
            raise HTTPException(status_code=400, detail="Target is not an image")

        content_length = r.headers.get("content-length")
        if content_length and int(content_length) > MAX_IMAGE_SIZE_BYTES:
            await client.aclose()
            raise HTTPException(status_code=413, detail="Image exceeds 20MB limit")

        async def stream_generator():
            total_read = 0
            try:
                async for chunk in r.aiter_bytes(chunk_size=65536):
                    total_read += len(chunk)
                    if total_read > MAX_IMAGE_SIZE_BYTES:
                        raise HTTPException(status_code=413, detail="Image exceeded 20MB cap during stream")
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_generator(),
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Type": content_type,
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Image proxy error for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Failed to fetch remote image")
