"""Unit tests for configuration and StoreContext (Step 1.2)."""

from pathlib import Path

import pytest

from backend.config.settings import AppSettings
from backend.config.store_context import (
    StoreProfile,
    StoreRegistry,
    safe_path,
)


def test_safe_path_valid(tmp_path: Path) -> None:
    """safe_path correctly resolves paths inside the base directory."""
    target = safe_path(tmp_path, "sub/dir/file.txt")
    assert target.is_relative_to(tmp_path.resolve())
    assert target == (tmp_path / "sub" / "dir" / "file.txt").resolve()


def test_safe_path_traversal_blocked(tmp_path: Path) -> None:
    """safe_path raises ValueError when attempting path traversal."""
    with pytest.raises(ValueError, match="Path traversal detected"):
        safe_path(tmp_path, "../outside.txt")

    with pytest.raises(ValueError, match="Path traversal detected"):
        safe_path(tmp_path, "sub/../../outside.txt")


def test_safe_path_absolute_blocked(tmp_path: Path) -> None:
    """safe_path raises ValueError when relative path is absolute."""
    with pytest.raises(ValueError, match="Expected relative path"):
        safe_path(tmp_path, "/etc/passwd")


def test_store_profile_id_validation() -> None:
    """StoreProfile enforces regex ^[A-Za-z0-9_-]{1,32}$ on store_id."""
    # Valid IDs
    valid_ids = ["store_1", "store-2", "870997", "TEST", "a" * 32]
    for sid in valid_ids:
        profile = StoreProfile(store_id=sid, name="Store", client_id=sid, api_key="secret")
        assert profile.store_id == sid

    # Invalid IDs
    invalid_ids = ["", "store/1", "../escape", "store name", "a" * 33, "store@id", "store$"]
    for sid in invalid_ids:
        with pytest.raises(ValueError, match="Invalid store_id"):
            StoreProfile(store_id=sid, name="Store", client_id="cid", api_key="secret")


def test_store_profile_masked_dict() -> None:
    """StoreProfile.to_masked_dict does not leak raw API key."""
    profile = StoreProfile(
        store_id="store_main",
        name="Main Store",
        client_id="12345",
        api_key="very-secret-api-key-12345",
        is_test=False,
    )
    masked = profile.to_masked_dict()
    assert masked["api_key_masked"] == "very...2345"
    assert "very-secret-api-key-12345" not in str(masked)


def test_store_registry_switching(tmp_path: Path) -> None:
    """Switching profiles updates all derived paths in StoreContext."""
    registry = StoreRegistry(base_dir=tmp_path)

    # Register two distinct profiles
    p1 = StoreProfile(
        store_id="store_primary",
        name="Primary Store",
        client_id="870997",
        api_key="key_primary",
        is_test=False,
    )
    p2 = StoreProfile(
        store_id="store_secondary",
        name="Secondary Store",
        client_id="2727930",
        api_key="key_secondary",
        is_test=True,
    )
    registry.register_profile(p1)
    registry.register_profile(p2)

    # Switch to p1
    ctx1 = registry.switch_profile("store_primary")
    assert ctx1.store_id == "store_primary"
    assert ctx1.name == "Primary Store"
    assert ctx1.client_id == "870997"
    assert not ctx1.is_test
    assert ctx1.db_path == tmp_path / "storage" / "stores" / "store_primary" / "catalog.db"
    assert ctx1.excel_pre2011_dir == tmp_path / "ready_tables" / "store_primary" / "1942-2010"
    assert ctx1.excel_post2011_dir == tmp_path / "ready_tables" / "store_primary" / "с_2011"

    # Switch to p2
    ctx2 = registry.switch_profile("store_secondary")
    assert ctx2.store_id == "store_secondary"
    assert ctx2.name == "Secondary Store"
    assert ctx2.client_id == "2727930"
    assert ctx2.is_test
    assert ctx2.db_path == tmp_path / "storage" / "stores" / "store_secondary" / "catalog.db"
    assert ctx2.excel_pre2011_dir == tmp_path / "ready_tables" / "store_secondary" / "1942-2010"
    assert ctx2.excel_post2011_dir == tmp_path / "ready_tables" / "store_secondary" / "с_2011"


def test_env_does_not_block_profile_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit switch_profile must override any environment variable defaults."""
    monkeypatch.setenv("OZON_CLIENT_ID", "fixed_env_client_id")

    registry = StoreRegistry(base_dir=tmp_path)
    p1 = StoreProfile(store_id="store_a", name="Store A", client_id="client_a", api_key="key_a")
    p2 = StoreProfile(store_id="store_b", name="Store B", client_id="client_b", api_key="key_b")
    registry.register_profile(p1)
    registry.register_profile(p2)

    ctx_b = registry.switch_profile("store_b")
    assert ctx_b.store_id == "store_b"
    assert ctx_b.client_id == "client_b"

    ctx_a = registry.switch_profile("store_a")
    assert ctx_a.store_id == "store_a"
    assert ctx_a.client_id == "client_a"


def test_app_settings_zero_side_effects() -> None:
    """AppSettings initializes without monkey-patching socket or side effects."""
    import socket

    orig_getaddrinfo = socket.getaddrinfo
    settings = AppSettings()
    assert settings.port == 8095
    assert socket.getaddrinfo is orig_getaddrinfo
    assert isinstance(settings.gemini_models, list)
    assert len(settings.gemini_models) > 0
