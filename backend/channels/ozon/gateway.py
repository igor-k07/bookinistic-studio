"""Ozon Seller API Gateway with Token Bucket rate limiter and resilient retries.

Architectural Guarantees:
- Resilient httpx client with tenacity exponential backoff on 429/500/503.
- Thread-safe Token Bucket rate limiter preventing 429 throttling.
- Strictly uses current API endpoints:
  - POST /v3/product/list
  - POST /v3/product/info/list (replacing removed /v2/product/info)
  - POST /v4/product/info/attributes (strictly chunked by 50!)
  - POST /v3/product/import
  - POST /v1/product/attributes/update
  - POST /v1/product/pictures/import
  - POST /v2/product/pictures/info
  - POST /v1/product/import/prices
  - POST /v1/product/import/info
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.domain.exceptions import AuthenticationError, ExternalServiceError

logger = logging.getLogger(__name__)

OZON_BASE_URL = "https://api-seller.ozon.ru"


class TokenBucket:
    """Thread-safe Token Bucket rate limiter."""

    def __init__(self, rate: float = 10.0, capacity: float = 10.0) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                needed = tokens - self.tokens
                sleep_time = needed / self.rate
            time.sleep(sleep_time)


def is_retryable_ozon_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exc, httpx.TransportError):
        return True
    return False


class OzonGateway:
    """Gateway communicating with Ozon Seller API."""

    def __init__(
        self,
        client_id: str,
        api_key: str,
        http_client: Optional[httpx.Client] = None,
        rate_limit: float = 10.0,
    ) -> None:
        self.client_id = client_id.strip()
        self.api_key = api_key.strip()
        self._client = http_client or httpx.Client(base_url=OZON_BASE_URL, timeout=30.0)
        self.limiter = TokenBucket(rate=rate_limit, capacity=rate_limit)

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.api_key)

    def _require_auth(self) -> Dict[str, str]:
        if not self.is_configured:
            raise AuthenticationError("Ozon credentials (client_id / api_key) not configured")
        return {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    @retry(
        retry=retry_if_exception(is_retryable_ozon_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=8),
        reraise=True,
    )
    def post(self, endpoint: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send authenticated POST request with rate-limiting and retry."""
        headers = self._require_auth()
        self.limiter.acquire()
        url = endpoint if endpoint.startswith("http") else f"{OZON_BASE_URL}{endpoint}"
        resp = self._client.post(url, headers=headers, json=payload or {})

        if resp.status_code in (401, 403):
            raise AuthenticationError(f"Ozon API authentication failed: {resp.text}")

        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ExternalServiceError(f"Unexpected non-dict response from Ozon {endpoint}: {resp.text}")
        return data

    def check_connection(self) -> Dict[str, Any]:
        """Verify API keys by fetching category attribute list."""
        try:
            res = self.post("/v1/description-category/attribute/values", {
                "description_category_id": 17038167,
                "type_id": 971445087,
                "attribute_id": 8229,
                "limit": 1,
            })
            return {"connected": True, "details": res}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def import_products(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit items for import via POST /v3/product/import."""
        return self.post("/v3/product/import", payload)

    def update_attributes(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing product attributes via POST /v1/product/attributes/update."""
        return self.post("/v1/product/attributes/update", payload)

    def update_prices(self, prices_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update product prices via POST /v1/product/import/prices."""
        return self.post("/v1/product/import/prices", prices_payload)

    def get_import_info(self, task_id: int) -> Dict[str, Any]:
        """Get product import task status via POST /v1/product/import/info."""
        return self.post("/v1/product/import/info", {"task_id": task_id})

    def list_products(self, limit: int = 1000, last_id: str = "") -> Dict[str, Any]:
        """List products via POST /v3/product/list."""
        payload: Dict[str, Any] = {"limit": limit, "filter": {"visibility": "ALL"}}
        if last_id:
            payload["last_id"] = last_id
        return self.post("/v3/product/list", payload)

    def get_products_info(
        self, product_ids: Optional[List[int]] = None, offer_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch basic product info via POST /v3/product/info/list (chunked by 100)."""
        all_results: List[Dict[str, Any]] = []
        if offer_ids:
            for i in range(0, len(offer_ids), 100):
                chunk = offer_ids[i : i + 100]
                res = self.post("/v3/product/info/list", {"offer_id": chunk})
                items = res.get("result", {}).get("items", [])
                all_results.extend(items)
        elif product_ids:
            for i in range(0, len(product_ids), 100):
                chunk_ids = product_ids[i : i + 100]
                res = self.post("/v3/product/info/list", {"product_id": chunk_ids})
                items = res.get("result", {}).get("items", [])
                all_results.extend(items)
        return all_results

    def get_products_attributes(
        self, product_ids: Optional[List[int]] = None, offer_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch product attributes via POST /v4/product/info/attributes (strictly chunked by 50!)."""
        all_results: List[Dict[str, Any]] = []
        filter_dict: Dict[str, Any] = {"visibility": "ALL"}

        if offer_ids:
            for i in range(0, len(offer_ids), 50):
                chunk = offer_ids[i : i + 50]
                filter_copy = dict(filter_dict)
                filter_copy["offer_id"] = chunk
                res = self.post("/v4/product/info/attributes", {
                    "filter": filter_copy,
                    "limit": 50,
                })
                items = res.get("result", [])
                all_results.extend(items)
        elif product_ids:
            for i in range(0, len(product_ids), 50):
                chunk_ids = product_ids[i : i + 50]
                filter_copy = dict(filter_dict)
                filter_copy["product_id"] = chunk_ids
                res = self.post("/v4/product/info/attributes", {
                    "filter": filter_copy,
                    "limit": 50,
                })
                items = res.get("result", [])
                all_results.extend(items)
        return all_results

    def update_pictures(self, product_id: int, photo_urls: List[str]) -> Dict[str, Any]:
        """Update photos via POST /v1/product/pictures/import."""
        payload = {
            "product_id": product_id,
            "images": photo_urls,
        }
        return self.post("/v1/product/pictures/import", payload)

    def get_picture_import_status(self, task_id: int) -> Dict[str, Any]:
        """Get photo import status via POST /v2/product/pictures/info."""
        return self.post("/v2/product/pictures/info", {"task_id": task_id})
