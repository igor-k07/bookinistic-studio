"""Multi-store isolation, StoreContext and safe path validation.

Implements ADR-3 (Composition Root & StoreContext) and ADR-10 (Zero-Trust Security).
Guarantees 0 import-time side effects.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

STORE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def safe_path(base: Union[str, Path], rel: Union[str, Path]) -> Path:
    """Resolve a relative path against base and ensure it cannot escape base directory.

    Raises:
        ValueError: If path traversal (e.g. '../') or absolute path is detected.
    """
    base_resolved = Path(base).resolve()
    rel_path = Path(rel)

    if rel_path.is_absolute():
        raise ValueError(f"Expected relative path, got absolute: {rel}")

    target = (base_resolved / rel_path).resolve()
    if not target.is_relative_to(base_resolved):
        raise ValueError(f"Path traversal detected: {rel} escapes {base_resolved}")

    return target


@dataclass(frozen=True)
class StoreProfile:
    """Immutable representation of a store's credentials and metadata."""

    store_id: str
    name: str
    client_id: str
    api_key: str
    is_test: bool = False

    def __post_init__(self) -> None:
        if not STORE_ID_REGEX.match(self.store_id):
            raise ValueError(
                f"Invalid store_id '{self.store_id}': must match pattern ^[A-Za-z0-9_-]{{1,32}}$"
            )

    def to_masked_dict(self) -> dict:
        """Safe dictionary representation for UI / logs with masked secrets."""
        masked_key = (
            f"{self.api_key[:4]}...{self.api_key[-4:]}"
            if len(self.api_key) > 8
            else "***"
        )
        return {
            "store_id": self.store_id,
            "name": self.name,
            "client_id": self.client_id,
            "api_key_masked": masked_key,
            "is_test": self.is_test,
        }


@dataclass(frozen=True)
class StoreContext:
    """Immutable runtime context for the active store with all derived filesystem paths."""

    profile: StoreProfile
    base_dir: Path

    @property
    def store_id(self) -> str:
        return self.profile.store_id

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def client_id(self) -> str:
        return self.profile.client_id

    @property
    def api_key(self) -> str:
        return self.profile.api_key

    @property
    def is_test(self) -> bool:
        return self.profile.is_test

    @property
    def storage_dir(self) -> Path:
        return safe_path(self.base_dir, f"storage/stores/{self.store_id}")

    @property
    def db_path(self) -> Path:
        return self.storage_dir / "catalog.db"

    @property
    def vault_dir(self) -> Path:
        return self.base_dir / "storage" / "books_vault"

    @property
    def excel_pre2011_dir(self) -> Path:
        return self.base_dir / "ready_tables" / self.store_id / "1942-2010"

    @property
    def excel_post2011_dir(self) -> Path:
        return self.base_dir / "ready_tables" / self.store_id / "с_2011"

    @property
    def templates_dir(self) -> Path:
        return self.base_dir / "templates"

    @property
    def ready_tables_dir(self) -> Path:
        return self.base_dir / "ready_tables"

    def ensure_dirs(self) -> None:
        """Create necessary store directories at runtime (never on import)."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.excel_pre2011_dir.mkdir(parents=True, exist_ok=True)
        self.excel_post2011_dir.mkdir(parents=True, exist_ok=True)


class StoreRegistry:
    """Registry managing available store profiles and active store switching."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = (
            base_dir.resolve()
            if base_dir
            else Path(__file__).resolve().parent.parent.parent
        )
        self._profiles: Dict[str, StoreProfile] = {}
        self._active_store_id: Optional[str] = None
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Discover and load store profiles from credentials directory."""
        cred_dir = self.base_dir / "credentials"

        # 1. Check credentials/stores.json
        stores_json = cred_dir / "stores.json"
        if stores_json.is_file():
            try:
                data = json.loads(stores_json.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        self.register_profile(
                            StoreProfile(
                                store_id=str(item.get("store_id") or item.get("client_id")),
                                name=item.get("name", "Магазин"),
                                client_id=str(item.get("client_id", "")),
                                api_key=str(item.get("api_key", "")),
                                is_test=bool(item.get("is_test", False)),
                            )
                        )
                elif isinstance(data, dict):
                    for s_id, item in data.items():
                        self.register_profile(
                            StoreProfile(
                                store_id=str(item.get("store_id") or s_id),
                                name=item.get("name", "Магазин"),
                                client_id=str(item.get("client_id", "")),
                                api_key=str(item.get("api_key", "")),
                                is_test=bool(item.get("is_test", False)),
                            )
                        )
            except Exception as e:
                logger.warning(f"Failed to load {stores_json}: {e}")

        # 2. Check backwards-compatible ozon_primary.json
        primary_json = cred_dir / "ozon_primary.json"
        if primary_json.is_file():
            try:
                p_data = json.loads(primary_json.read_text(encoding="utf-8"))
                cid = str(p_data.get("client_id", "")).strip()
                s_id = cid or "primary"
                if s_id not in self._profiles and cid:
                    self.register_profile(
                        StoreProfile(
                            store_id=s_id,
                            name=p_data.get("name", "Основной магазин"),
                            client_id=cid,
                            api_key=str(p_data.get("api_key", "")).strip(),
                            is_test=bool(p_data.get("is_test", False)),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to load {primary_json}: {e}")

        # 3. Check backwards-compatible ozon_test.json
        test_json = cred_dir / "ozon_test.json"
        if test_json.is_file():
            try:
                t_data = json.loads(test_json.read_text(encoding="utf-8"))
                cid = str(t_data.get("client_id", "")).strip()
                s_id = cid or "test_store"
                if s_id not in self._profiles and cid:
                    self.register_profile(
                        StoreProfile(
                            store_id=s_id,
                            name=t_data.get("name", "Тестовый магазин"),
                            client_id=cid,
                            api_key=str(t_data.get("api_key", "")).strip(),
                            is_test=bool(t_data.get("is_test", True)),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to load {test_json}: {e}")

        # Fallback default if empty
        if not self._profiles:
            fallback = StoreProfile(
                store_id="default_store",
                name="Основной магазин",
                client_id="default_client",
                api_key="default_key",
                is_test=False,
            )
            self._profiles[fallback.store_id] = fallback

        # Default active profile is the first non-test store, or the first available
        non_test = [p for p in self._profiles.values() if not p.is_test]
        if non_test:
            self._active_store_id = non_test[0].store_id
        else:
            self._active_store_id = next(iter(self._profiles.keys()))

    def register_profile(self, profile: StoreProfile) -> None:
        """Register or update a store profile."""
        self._profiles[profile.store_id] = profile
        if self._active_store_id is None:
            self._active_store_id = profile.store_id

    def list_profiles(self) -> List[StoreProfile]:
        """List all registered store profiles."""
        return list(self._profiles.values())

    def get_profile(self, store_id: str) -> Optional[StoreProfile]:
        """Retrieve a profile by store_id."""
        return self._profiles.get(store_id)

    def switch_profile(self, store_id: str) -> StoreContext:
        """Explicitly switch the active store.

        Validates store_id and updates active context.
        Guarantees that environment variables cannot block this explicit switch.
        """
        if not STORE_ID_REGEX.match(store_id):
            raise ValueError(
                f"Invalid store_id '{store_id}': must match pattern ^[A-Za-z0-9_-]{{1,32}}$"
            )
        if store_id not in self._profiles:
            raise KeyError(f"Store '{store_id}' not found in registry")

        self._active_store_id = store_id
        return self.get_active_context()

    def get_active_context(self) -> StoreContext:
        """Return the immutable StoreContext for the currently active store."""
        if not self._active_store_id or self._active_store_id not in self._profiles:
            self._active_store_id = next(iter(self._profiles.keys()))

        profile = self._profiles[self._active_store_id]
        return StoreContext(profile=profile, base_dir=self.base_dir)

