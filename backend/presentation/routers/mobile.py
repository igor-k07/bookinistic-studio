"""Mobile studio PWA capture and chunked uploader router."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from backend.presentation.dto import MobileCommitDTO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mobile", tags=["Mobile Studio"])


@router.post("/upload-chunk")
async def upload_mobile_chunk(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    chunk_index: int = Form(...),
    role: str = Form("cover_front"),
    book_index: int = Form(0),
) -> Any:
    """Idempotently receive binary photo chunk from mobile camera/gallery."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload chunk")

    app_state = request.app.state
    # Local session buffer directory
    buffer_dir = Path("storage/mobile_sessions") / session_id / f"book_{book_index}"
    buffer_dir.mkdir(parents=True, exist_ok=True)

    chunk_filename = f"chunk_{chunk_index}_{role}.jpg"
    chunk_path = buffer_dir / chunk_filename
    chunk_path.write_bytes(data)

    # Real-time SSE dispatch for desktop pool live update
    if hasattr(app_state, "event_broker") and app_state.event_broker:
        app_state.event_broker.publish(
            "mobile.batch_received",
            {
                "session_id": session_id,
                "chunk_index": chunk_index,
                "role": role,
                "book_index": book_index,
                "file_size": len(data),
            },
        )

    return {
        "status": "ok",
        "session_id": session_id,
        "chunk_index": chunk_index,
        "bytes_received": len(data),
    }


@router.post("/commit")
def commit_mobile_session(req: MobileCommitDTO, request: Request) -> Any:
    """Commit mobile upload session: create assets in the active store photo pool."""
    app_state = request.app.state

    session_dir = Path("storage/mobile_sessions") / req.session_id
    if not session_dir.is_dir():
        return {"status": "ok", "session_id": req.session_id, "assets_count": 0}

    created_assets = []
    # Ingest buffered photos into asset pipeline
    use_case = app_state.asset_pipeline_use_case
    for book_folder in sorted(session_dir.iterdir()):
        if not book_folder.is_dir():
            continue
        for chunk_file in sorted(book_folder.iterdir()):
            if chunk_file.suffix.lower() in (".jpg", ".jpeg", ".png"):
                raw_bytes = chunk_file.read_bytes()
                # Parse role from filename e.g. chunk_0_cover_front.jpg
                parts = chunk_file.stem.split("_", 2)
                slot = parts[2] if len(parts) >= 3 else "cover_front"
                asset = use_case.create_asset(
                    book_article=req.book_article,
                    raw_data=raw_bytes,
                    original_filename=chunk_file.name,
                    slot=slot,
                )
                created_assets.append(asset.id)

    if hasattr(app_state, "event_broker") and app_state.event_broker:
        app_state.event_broker.publish(
            "mobile.committed",
            {"session_id": req.session_id, "assets_created": len(created_assets)},
        )

    return {
        "status": "committed",
        "session_id": req.session_id,
        "assets_count": len(created_assets),
        "asset_ids": created_assets,
    }
