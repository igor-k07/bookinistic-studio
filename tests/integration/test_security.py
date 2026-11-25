"""Integration tests for Zero-Trust Security Middleware and CloudflareTunnelManager (Step 6.1).

Verifies:
1. Path traversal attempts (/static/../.env, ../../) -> 403 blocked.
2. Dangerous script/command executions (.command, .sh, .env, .db) -> 403 blocked.
3. SSRF on image proxy endpoints (http://127.0.0.1, localhost, private IP) -> 403 blocked.
4. Non-loopback / Cloudflare Tunnel perimeter:
   - External requests to /api/books without token -> 403 blocked.
   - External requests to /api/books WITH token -> 403 blocked (only mobile allowed).
   - External requests to /mobile without token -> 403 blocked.
   - External requests to /mobile with valid token -> 200 allowed.
   - External requests to /api/health -> 200 allowed.
5. Token rotation via SessionTokenManager.
6. CloudflareTunnelManager PID-scoped lifecycle (zero pkill).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.infrastructure.network.tunnel_manager import CloudflareTunnelManager
from backend.presentation.middleware.security import (
    SecurityMiddleware,
    SessionTokenManager,
    is_private_or_forbidden_host,
)


@pytest.fixture
def token_manager() -> SessionTokenManager:
    return SessionTokenManager("test-secret-token-12345")


@pytest.fixture
def app_with_security(token_manager: SessionTokenManager) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityMiddleware, token_manager=token_manager)

    @app.get("/api/health")
    def health_check():
        return {"status": "ok"}

    @app.get("/api/books")
    def list_books():
        return {"books": []}

    @app.post("/api/mobile/upload")
    def mobile_upload():
        return {"status": "uploaded"}

    @app.get("/mobile")
    def mobile_index():
        return {"page": "mobile"}

    @app.get("/api/image_proxy")
    def image_proxy(url: str):
        return {"proxied": url}

    @app.get("/api/open_guide")
    def open_guide(name: str):
        return {"guide": name}

    return app


@pytest.fixture
def client(app_with_security: FastAPI) -> TestClient:
    return TestClient(app_with_security)


# --- 1. Path Traversal Tests ---


def test_path_traversal_dot_dot_blocked(client: TestClient):
    """Verify ../ patterns are rejected immediately."""
    resp = client.get("/static/../.env")
    assert resp.status_code == 403
    assert "blocked" in resp.text.lower() or "forbidden" in resp.text.lower()

    resp2 = client.get("/api/assets/delete?path=../../etc/passwd")
    assert resp2.status_code == 403


# --- 2. Dangerous Script Execution & Sensitive Files Tests ---


def test_dangerous_script_and_env_blocked(client: TestClient):
    """Verify arbitrary script and sensitive file extensions are forbidden."""
    resp = client.get("/api/open_guide?name=start.command")
    assert resp.status_code == 403

    resp2 = client.get("/scripts/run.sh")
    assert resp2.status_code == 403

    resp3 = client.get("/.env")
    assert resp3.status_code == 403

    resp4 = client.get("/data/backup.db")
    assert resp4.status_code == 403


# --- 3. SSRF Protection Tests ---


def test_image_proxy_ssrf_blocked(client: TestClient):
    """Verify loopback and private subnets are blocked on proxy endpoints."""
    # Loopback IP
    resp = client.get("/api/image_proxy?url=http://127.0.0.1:8095/secret")
    assert resp.status_code == 403
    assert "ssrf" in resp.text.lower()

    # Localhost
    resp2 = client.get("/api/image_proxy?url=http://localhost:8000/info")
    assert resp2.status_code == 403

    # Private RFC-1918 subnets
    assert is_private_or_forbidden_host("http://192.168.1.100/cam.jpg") is True
    assert is_private_or_forbidden_host("http://10.0.0.5/photo.png") is True
    assert is_private_or_forbidden_host("http://172.16.0.1:8080/data") is True
    # Public domain should pass SSRF check
    assert is_private_or_forbidden_host("https://storage.yandexcloud.net/bucket/photo.jpg") is False


# --- 4. Perimeter & Cloudflare Tunnel Lockdown Tests ---


def test_external_access_to_books_blocked(client: TestClient, token_manager: SessionTokenManager):
    """External requests (with CF-Connecting-IP header) CANNOT access desktop API."""
    external_headers = {"cf-connecting-ip": "203.0.113.195"}

    # Without token -> 403
    resp = client.get("/api/books", headers=external_headers)
    assert resp.status_code == 403

    # Even WITH valid token -> 403 (External requests are strictly restricted to mobile endpoints!)
    headers_with_token = {
        "cf-connecting-ip": "203.0.113.195",
        "x-session-token": token_manager.current_token,
    }
    resp2 = client.get("/api/books", headers=headers_with_token)
    assert resp2.status_code == 403
    assert "only access mobile" in resp2.text.lower()


def test_external_mobile_endpoint_requires_valid_token(
    client: TestClient, token_manager: SessionTokenManager
):
    """External requests to /mobile require valid CSPRNG session token."""
    external_headers = {"cf-connecting-ip": "203.0.113.195"}

    # Missing token -> 403
    resp1 = client.get("/mobile", headers=external_headers)
    assert resp1.status_code == 403

    # Invalid token -> 403
    resp2 = client.get("/mobile?token=wrong_token", headers=external_headers)
    assert resp2.status_code == 403

    # Valid token in query param -> 200
    resp3 = client.get(f"/mobile?token={token_manager.current_token}", headers=external_headers)
    assert resp3.status_code == 200

    # Valid token in x-session-token header -> 200
    valid_headers = {
        "cf-connecting-ip": "203.0.113.195",
        "x-session-token": token_manager.current_token,
    }
    resp4 = client.post("/api/mobile/upload", headers=valid_headers)
    assert resp4.status_code == 200


def test_external_health_check_allowed_without_token(client: TestClient):
    """External health check endpoint is allowed for container/tunnel health probes."""
    resp = client.get("/api/health", headers={"cf-connecting-ip": "203.0.113.195"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_session_token_rotation(token_manager: SessionTokenManager):
    """Verify CSPRNG token rotation invalidates old tokens immediately."""
    token1 = token_manager.current_token
    assert token_manager.verify_token(token1) is True

    token2 = token_manager.rotate_token()
    assert token2 != token1
    assert token_manager.verify_token(token1) is False
    assert token_manager.verify_token(token2) is True


# --- 5. CloudflareTunnelManager Lifecycle Tests ---


def test_tunnel_manager_pid_scoped_stop(tmp_path):
    """Verify CloudflareTunnelManager only manages its own spawned process (zero pkill)."""
    pid_file = tmp_path / "cloudflared.pid"
    manager = CloudflareTunnelManager(port=8095, pid_file=pid_file)

    mock_proc = MagicMock()
    mock_proc.pid = 44556
    mock_proc.poll.return_value = None
    mock_proc.stderr = MagicMock()

    manager._process = mock_proc
    manager._tunnel_url = "https://mock-test.trycloudflare.com"

    assert manager.is_running() is True
    assert manager.get_tunnel_url() == "https://mock-test.trycloudflare.com"

    # Stop tunnel
    manager.stop_tunnel()

    mock_proc.terminate.assert_called_once()
    assert manager.is_running() is False
    assert manager.get_tunnel_url() is None
