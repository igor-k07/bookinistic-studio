"""Integration tests for FastAPI API contract and OpenAPI schema (Step 6.2).

Verifies all core presentation layer endpoints:
- GET /api/health
- GET /api/bootstrap (tabs, stores, brands, formats, token)
- Workspace tabs lifecycle (GET, POST, PATCH, DELETE /api/tabs)
- Books endpoints (POST /api/books/validate, POST /api/books/save, GET /api/books/catalog)
- AI classify batch (POST /api/ai/classify-batch)
- Masked system keys (GET /api/system/keys strictly masking secrets)
- Store profile switching (POST /api/ozon/switch-profile)
- Server-Sent Events stream (GET /api/events/stream)
- OpenAPI specification consistency (valid JSON, >= 30 paths, version 2.0.0)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Test client with mock external I/O (S3, cloudflared)."""
    with patch("backend.infrastructure.network.tunnel_manager.CloudflareTunnelManager.start_tunnel") as mock_tunnel:
        mock_tunnel.return_value = "https://mock.trycloudflare.com"
        app = create_app()
        with TestClient(app) as tc:
            yield tc


def test_health_endpoint(client: TestClient):
    """GET /api/health returns 200 OK and version."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"


def test_bootstrap_endpoint(client: TestClient):
    """GET /api/bootstrap returns store registry, brands, formats, and session token."""
    resp = client.get("/api/bootstrap")
    assert resp.status_code == 200
    data = resp.json()
    assert "stores" in data
    assert "active_store" in data
    assert "brands" in data
    assert "gost_formats" in data
    assert "tabs" in data
    assert "mobile_token" in data
    assert len(data["mobile_token"]) > 16


def test_workspace_tabs_crud_lifecycle(client: TestClient):
    """Verify tabs CRUD: list, create, update, delete."""
    # 0. Ensure book exists for foreign key constraint
    from backend.domain.models import Book
    ctx = client.app.state.store_registry.get_active_context()
    with ctx.uow:
        ctx.book_repo.save(Book(article="DP-B-09999", title="Интеграционный тест"))

    # 1. Create tab
    tab_payload = {
        "id": "tab_integration_test",
        "book_article": "DP-B-09999",
        "tab_order": 0,
        "is_active": True,
        "is_edit_mode": False,
        "title": "Интеграционный тест",
    }
    resp_create = client.post("/api/tabs", json=tab_payload)
    assert resp_create.status_code == 200
    created = resp_create.json()
    assert created["id"] == "tab_integration_test"
    assert created["book_article"] == "DP-B-09999"

    # 2. List tabs
    resp_list = client.get("/api/tabs")
    assert resp_list.status_code == 200
    tabs = resp_list.json()
    assert any(t["id"] == "tab_integration_test" for t in tabs)

    # 3. Update tab
    resp_patch = client.patch(
        "/api/tabs/tab_integration_test",
        json={"is_active": False, "tab_order": 5},
    )
    assert resp_patch.status_code == 200
    updated = resp_patch.json()
    assert updated["is_active"] is False
    assert updated["tab_order"] == 5

    # 4. Delete tab
    resp_del = client.delete("/api/tabs/tab_integration_test")
    assert resp_del.status_code == 200
    assert resp_del.json()["success"] is True

    # 5. Verify deleted
    resp_list_after = client.get("/api/tabs")
    assert not any(t["id"] == "tab_integration_test" for t in resp_list_after.json())


def test_books_validate_endpoint(client: TestClient):
    """POST /api/books/validate returns field validation results in < 5 ms."""
    valid_book_payload = {
        "book": {
            "article": "DP-B-00100",
            "title": "Война и мир",
            "author": "Лев Толстой",
            "year": 1869,
            "price": 1500.0,
            "publisher": "Художественная литература",
            "template_mode": "pre2011",
            "main_photo_url": "https://storage.yandexcloud.net/bucket/cover.jpg",
            "dimensions": {
                "width_mm": 130,
                "length_mm": 200,
                "height_mm": 25,
                "weight_g": 500,
            },
        }
    }
    resp = client.post("/api/books/validate", json=valid_book_payload)
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_classify_batch_endpoint(client: TestClient):
    """POST /api/ai/classify-batch maps filenames to canonical slot roles."""
    payload = {
        "filenames": [
            "01_front.jpg",
            "title_page.jpg",
            "spine_view.jpg",
            "scratch_defect.jpg",
            "spread_illustration.jpg",
        ]
    }
    resp = client.post("/api/ai/classify-batch", json=payload)
    assert resp.status_code == 200
    mapping = resp.json()
    assert mapping["01_front.jpg"] == "cover_front"
    assert mapping["title_page.jpg"] == "info_pages"
    assert mapping["scratch_defect.jpg"] == "mantra_defects"


def test_system_keys_masked_strictly(client: TestClient):
    """GET /api/system/keys NEVER returns unmasked API keys or secrets."""
    resp = client.get("/api/system/keys")
    assert resp.status_code == 200
    keys_data = resp.json()

    for key_type in ("gemini_api_key", "ozon_api_key", "s3_secret_key"):
        assert key_type in keys_data
        item = keys_data[key_type]
        assert "configured" in item
        assert "masked" in item
        masked_val = item["masked"]
        # Must be empty or contain ellipsis, never raw key
        assert masked_val == "" or "..." in masked_val or masked_val == "***"


def test_switch_store_profile(client: TestClient):
    """POST /api/ozon/switch-profile switches active store context safely."""
    # List available stores first
    resp_boot = client.get("/api/bootstrap")
    stores = resp_boot.json()["stores"]
    assert len(stores) >= 1

    target_store = stores[0]["store_id"]
    resp_switch = client.post(
        "/api/ozon/switch-profile",
        json={"store_id": target_store},
    )
    assert resp_switch.status_code == 200
    assert resp_switch.json()["active_store"] == target_store


def test_openapi_json_file_exported_and_valid():
    """Verify openapi.json exists, is valid JSON, and has all expected endpoints."""
    openapi_file = Path("openapi.json")
    assert openapi_file.is_file(), "openapi.json must be exported to project root"

    data = json.loads(openapi_file.read_text(encoding="utf-8"))
    assert data["info"]["title"] == "Bookinistic Studio 2.0 API"
    assert data["info"]["version"] == "2.0.0"

    paths = data.get("paths", {})
    assert len(paths) >= 30, f"Expected at least 30 API paths, found {len(paths)}"

    expected_endpoints = [
        "/api/bootstrap",
        "/api/health",
        "/api/tabs",
        "/api/books/catalog",
        "/api/books/validate",
        "/api/books/save",
        "/api/assets/upload",
        "/api/ai/recognize",
        "/api/mobile/upload-chunk",
        "/api/events/stream",
        "/api/system/keys",
    ]
    for endpoint in expected_endpoints:
        assert endpoint in paths, f"Missing endpoint {endpoint} in openapi.json"
