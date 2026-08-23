"""File storage routes (Phase O): upload, list, download, delete.

Local-disk storage under settings.storage_dir/<tenant_id>/<file_id>. Files can
optionally attach to an object + record. Downloads stream with the original
content type and a safe filename.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.config import settings
from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.files import StoredFile

router = APIRouter(prefix="/api/files", tags=["files"])


def _storage_root(tenant_id) -> Path:
    root = Path(settings.storage_dir) / str(tenant_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _serialize(f: StoredFile) -> dict:
    return {
        "id": str(f.id),
        "name": f.name,
        "content_type": f.content_type,
        "size": f.size,
        "object": f.object_slug,
        "record_id": str(f.record_id) if f.record_id else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.post("", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    object: str | None = Form(default=None),
    record_id: str | None = Form(default=None),
    auth: AuthContext = Depends(require_member),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file (multipart). Optionally attach to an object + record."""
    row = StoredFile(
        tenant_id=auth.tenant_id,
        name=file.filename or "untitled",
        content_type=file.content_type or "application/octet-stream",
        object_slug=object,
        uploaded_by=auth.user_id,
    )
    if record_id:
        try:
            row.record_id = uuid.UUID(record_id)
        except ValueError as e:
            raise HTTPException(422, "record_id must be a UUID") from e

    db.add(row)
    await db.flush()

    dest = _storage_root(auth.tenant_id) / str(row.id)
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, f"file exceeds {settings.max_upload_bytes} byte limit")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    row.size = size

    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="file.uploaded",
        payload={"file_id": str(row.id), "name": row.name, "size": size, "object": object},
        actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(row)


@router.get("")
async def list_files(
    object: str | None = None,
    record_id: str | None = None,
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(StoredFile).where(StoredFile.tenant_id == auth.tenant_id)
    if object:
        stmt = stmt.where(StoredFile.object_slug == object)
    if record_id:
        try:
            stmt = stmt.where(StoredFile.record_id == uuid.UUID(record_id))
        except ValueError as e:
            raise HTTPException(422, "record_id must be a UUID") from e
    rows = (await db.execute(stmt.order_by(StoredFile.created_at.desc()))).scalars().all()
    return {"items": [_serialize(f) for f in rows], "total": len(rows)}


async def _get_file(db: AsyncSession, tenant_id, file_id: uuid.UUID) -> StoredFile:
    row = (await db.execute(select(StoredFile).where(
        StoredFile.id == file_id, StoredFile.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "file not found")
    return row


@router.get("/{file_id}/download")
async def download_file(file_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    row = await _get_file(db, auth.tenant_id, file_id)
    path = _storage_root(auth.tenant_id) / str(row.id)
    if not path.exists():
        raise HTTPException(404, "file data missing on disk")
    return FileResponse(path, media_type=row.content_type, filename=row.name)


@router.delete("/{file_id}")
async def delete_file(file_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    row = await _get_file(db, auth.tenant_id, file_id)
    path = _storage_root(auth.tenant_id) / str(row.id)
    path.unlink(missing_ok=True)
    await db.delete(row)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="file.deleted",
        payload={"file_id": str(file_id), "name": row.name}, actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}
