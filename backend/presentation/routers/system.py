"""System management, health checks, masked secrets, cleanup, and file downloads router."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api", tags=["System"])

ALLOWED_SYSTEM_FOLDERS = (
    "ready_tables",
    "storage",
    "books_vault",
)


@router.get("/health")
def health_check() -> Dict[str, str]:
    """Public health probe."""
    return {"status": "ok", "version": "2.0.0"}


@router.get("/system/keys")
def get_system_keys(request: Request) -> Dict[str, Any]:
    """Return masked API key statuses (strictly NO plaintext secrets)."""
    ctx = request.app.state.store_registry.get_active_context()
    prof = ctx.profile

    def mask(secret: str) -> str:
        if not secret:
            return ""
        if len(secret) <= 8:
            return "***"
        return f"{secret[:4]}...{secret[-4:]}"

    return {
        "store_id": prof.store_id,
        "gemini_api_key": {
            "configured": bool(prof.gemini_api_key),
            "masked": mask(prof.gemini_api_key),
        },
        "ozon_api_key": {
            "configured": bool(prof.ozon_api_key),
            "masked": mask(prof.ozon_api_key),
        },
        "s3_secret_key": {
            "configured": bool(prof.s3_secret_key),
            "masked": mask(prof.s3_secret_key),
        },
    }


@router.post("/system/cleanup")
def trigger_storage_cleanup(request: Request, dry_run: bool = False) -> Any:
    """Trigger transactional disk cleanup of archived assets."""
    use_case = request.app.state.cleanup_storage_use_case
    registry = request.app.state.store_registry
    return use_case.execute(store_id=registry.active_store_id, dry_run=dry_run)


@router.get("/system/excel/download")
def download_excel_catalog(request: Request, filename: str = "all_books.xlsx") -> FileResponse:
    """Download OpenXML catalog spreadsheet."""
    excel_path = Path("ready_tables") / filename
    if not excel_path.is_file():
        raise HTTPException(status_code=404, detail="Excel file not generated yet")
    return FileResponse(
        str(excel_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@router.get("/system/photos-zip")
def download_photos_zip(article: str, request: Request) -> FileResponse:
    """Download clean streaming ZIP for Ozon seller portal (excluding raw/info pages)."""
    ctx = request.app.state.store_registry.get_active_context()
    zip_path = Path("storage/exports") / f"{article}_ozon.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    count = ctx.vault_store.create_ozon_zip(article, zip_path)
    if count == 0 or not zip_path.is_file():
        raise HTTPException(status_code=404, detail=f"No valid photos to export for {article}")

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"{article}_ozon.zip",
    )


@router.post("/system/open-folder")
def open_system_folder(request: Request, folder: str = Query(...)) -> Any:
    """Open folder in native desktop file manager (127.0.0.1 and allowlist only)."""
    # 1. Strict loopback check
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="Only available on 127.0.0.1")

    # 2. Strict allowlist validation
    clean_folder = folder.strip().rstrip("/\\")
    if clean_folder not in ALLOWED_SYSTEM_FOLDERS:
        raise HTTPException(status_code=403, detail="Folder outside allowed directories")

    target_dir = Path(clean_folder).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # 3. Native OS open command
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(target_dir)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(target_dir)], check=False)
        elif sys.platform == "win32":
            os.startfile(str(target_dir))  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")

    return {"status": "opened", "folder": clean_folder}


@router.post("/system/tokens/rotate")
def rotate_session_token(request: Request) -> Dict[str, str]:
    """Rotate mobile CSPRNG token."""
    token_mgr = getattr(request.app.state, "token_manager", None)
    if not token_mgr:
        raise HTTPException(status_code=500, detail="Token manager not initialized")
    new_token = token_mgr.rotate_token()
    return {"status": "ok", "mobile_token": new_token}
