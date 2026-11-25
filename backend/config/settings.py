"""Application settings loaded via pydantic-settings.

Zero import-time side effects: no file creation, no monkey-patching.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Bookinistic Studio"
    app_version: str = "2.0.0"
    port: int = 8095
    host: str = "127.0.0.1"

    # Base directory of the repository
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent
    )

    # Gemini Vision API Key & Cascade
    gemini_api_key: Optional[str] = None
    gemini_models: List[str] = Field(
        default_factory=lambda: [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]
    )
    gemini_temperature: float = 0.2

    # Yandex S3 Object Storage Configuration
    s3_bucket: Optional[str] = None
    s3_key_id: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_endpoint_url: str = "https://storage.yandexcloud.net"
    s3_region_name: str = "ru-central1"

    # Cloudflare Quick Tunnel Configuration
    tunnel_enabled: bool = False
    tunnel_hostname: Optional[str] = None

    def get_effective_gemini_key(self) -> str:
        """Resolve Gemini key from settings, then fallback to credential files."""
        if self.gemini_api_key and self.gemini_api_key.strip():
            return self.gemini_api_key.strip()

        candidates = [
            self.base_dir / "credentials" / ".gemini_api_key",
            self.base_dir / "credentials" / "gemini.key",
            self.base_dir / ".gemini_api_key",
        ]
        for path in candidates:
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    if content and not content.startswith("#"):
                        return content
                except OSError:
                    pass
        return ""

    def get_masked_gemini_key(self) -> dict:
        """Return masked key representation safe for frontend consumption."""
        key = self.get_effective_gemini_key()
        if not key:
            return {"configured": False, "masked": ""}
        if len(key) <= 8:
            masked = "***"
        else:
            masked = f"{key[:4]}...{key[-4:]}"
        return {"configured": True, "masked": masked}

    def get_effective_s3_config(self) -> Optional[dict]:
        """Resolve S3 configuration from settings or credentials file."""
        if self.s3_bucket and self.s3_key_id and self.s3_secret_key:
            return {
                "bucket": self.s3_bucket.strip(),
                "key_id": self.s3_key_id.strip(),
                "secret_key": self.s3_secret_key.strip(),
                "endpoint_url": self.s3_endpoint_url.strip(),
                "region_name": self.s3_region_name.strip(),
            }

        candidates = [
            self.base_dir / "credentials" / ".yandex_s3_credentials",
            self.base_dir / "credentials" / "yandex_s3.json",
            self.base_dir / ".yandex_s3_credentials",
        ]
        for path in candidates:
            if path.is_file():
                try:
                    import json

                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("bucket"):
                        return {
                            "bucket": data.get("bucket", "").strip(),
                            "key_id": data.get("key_id", "").strip(),
                            "secret_key": data.get("secret_key", "").strip(),
                            "endpoint_url": data.get(
                                "endpoint_url", "https://storage.yandexcloud.net"
                            ).strip(),
                            "region_name": data.get("region_name", "ru-central1").strip(),
                        }
                except (json.JSONDecodeError, OSError):
                    pass
        return None

