from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ...core.session_manager import get_manager
from ...core.config import config

router = APIRouter()


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    meeting_id: Optional[str] = Form(None),
):
    sm = get_manager()
    dest_dir = Path(config.FILES_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)

    mid = meeting_id or (sm.session.id if sm.session else "general")
    dest = dest_dir / f"{mid}_{file.filename}"

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        sm.context_store.add_file(str(dest), mid, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File indexed partially: {e}")

    if sm.session and sm.session.id == mid:
        sm.session.pre_meeting_files.append(str(dest))

    return {
        "ok": True,
        "filename": file.filename,
        "meeting_id": mid,
        "path": str(dest),
    }


@router.get("/files")
async def list_files(meeting_id: Optional[str] = None):
    files_dir = Path(config.FILES_DIR)
    if not files_dir.exists():
        return []
    pattern = f"{meeting_id}_*" if meeting_id else "*"
    return [
        {"filename": f.name, "size": f.stat().st_size, "meeting_id": meeting_id}
        for f in files_dir.glob(pattern)
        if f.is_file()
    ]
