"""Assets management router for binary uploads, non-destructive transforms, and previews."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from backend.domain.exceptions import ConcurrencyError, EntityNotFoundError
from backend.presentation.dto import AssetDTO, AssignAssetSlotRequest, TransformAssetRequest

router = APIRouter(prefix="/api/assets", tags=["Assets"])


@router.get("/pool", response_model=List[AssetDTO])
def list_pool_assets(request: Request, book_article: Optional[str] = None) -> Any:
    """List unassigned pool assets and optionally assets for the active book."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        assets = ctx.asset_repo.list_pool(article=book_article)
    return [AssetDTO(**a.to_dict()) for a in assets]


@router.post("/upload", response_model=AssetDTO)
async def upload_asset(
    request: Request,
    file: UploadFile = File(...),
    book_article: Optional[str] = Form(None),
    slot: Optional[str] = Form(None),
) -> Any:
    """Upload binary photo, create Asset with deterministic hash and auto-classify slot."""
    app_state = request.app.state
    use_case = app_state.asset_pipeline_use_case
    raw_data = await file.read()
    if not raw_data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    asset = use_case.create_asset(
        book_article=book_article,
        raw_data=raw_data,
        original_filename=file.filename or "",
        slot=slot,
    )
    return AssetDTO(**asset.to_dict())


@router.post("/{asset_id}/assign", response_model=AssetDTO)
def assign_asset_slot(asset_id: str, req: AssignAssetSlotRequest, request: Request) -> Any:
    """Assign or unassign asset to a semantic photo slot."""
    use_case = request.app.state.asset_pipeline_use_case
    try:
        asset = use_case.assign_slot(
            asset_id,
            req.slot,
            req.slot_order,
            book_article=req.book_article,
        )
        return AssetDTO(**asset.to_dict())
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{asset_id}/transform", response_model=AssetDTO)
def transform_asset(asset_id: str, req: TransformAssetRequest, request: Request) -> Any:
    """Apply non-destructive crop/rotation/filters with Optimistic Locking."""
    use_case = request.app.state.asset_pipeline_use_case
    try:
        asset = use_case.apply_transform(asset_id, req.transformations, req.expected_version)
        return AssetDTO(**asset.to_dict())
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConcurrencyError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{asset_id}/run-ai", response_model=AssetDTO)
def run_ai_rembg(asset_id: str, request: Request, force: bool = True) -> Any:
    """Trigger background removal via rembg (supports force=True from Photo Studio)."""
    use_case = request.app.state.asset_pipeline_use_case
    try:
        asset = use_case.trigger_rembg(asset_id, force=force)
        return AssetDTO(**asset.to_dict())
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{asset_id}")
def delete_asset(asset_id: str, request: Request) -> Any:
    """Delete an asset from workspace and media storage."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        deleted = ctx.asset_repo.delete(asset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return {"success": True, "asset_id": asset_id}


@router.get("/{asset_id}/preview")
def get_asset_preview(asset_id: str, request: Request) -> Response:
    """Serve fast preview image (avoids Base64 in DOM/manifest)."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        asset = ctx.asset_repo.get_by_id(asset_id)
    if not asset or not asset.preview_path:
        raise HTTPException(status_code=404, detail="Preview not found")

    path = Path(asset.preview_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File on disk not found")
    return FileResponse(str(path), media_type="image/jpeg")


@router.get("/{asset_id}/full")
def get_asset_full(asset_id: str, request: Request) -> Response:
    """Serve full resolution original photo."""
    ctx = request.app.state.store_registry.get_active_context()
    with ctx.uow:
        asset = ctx.asset_repo.get_by_id(asset_id)
    if not asset or not asset.original_path:
        raise HTTPException(status_code=404, detail="Original photo not found")

    path = Path(asset.original_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File on disk not found")
    return FileResponse(str(path), media_type="image/jpeg")
