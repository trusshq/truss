"""API key routes: create/list/revoke programmatic access keys (Phase A4).

The plaintext key is returned ONLY on creation. After that only a prefix
is shown. Keys act as their owner but are capped by scopes.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin
from truss_kernel.models.apikey import KEY_PREFIX, KNOWN_SCOPES, ApiKey

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: ["records:read", "records:write", "objects:read"])


def key_to_dict(k: ApiKey) -> dict:
    return {
        "id": str(k.id),
        "name": k.name,
        "key_prefix": k.key_prefix,
        "scopes": k.scopes,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        "created_at": k.created_at.isoformat() if k.created_at else None,
    }


@router.get("")
async def list_keys(auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ApiKey).where(ApiKey.tenant_id == auth.tenant_id).order_by(ApiKey.created_at.desc())
    )).scalars().all()
    return [key_to_dict(k) for k in rows]


@router.post("", status_code=201)
async def create_key(body: KeyIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    unknown = [s for s in body.scopes if s not in KNOWN_SCOPES]
    if unknown:
        raise HTTPException(422, f"unknown scopes: {unknown}. Known: {KNOWN_SCOPES}")
    plaintext = KEY_PREFIX + secrets.token_hex(16)
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    row = ApiKey(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        name=body.name,
        key_prefix=plaintext[:12] + "…",
        key_hash=key_hash,
        scopes=body.scopes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    out = key_to_dict(row)
    out["key"] = plaintext  # shown once
    return out


@router.delete("/{key_id}", status_code=204)
async def revoke_key(key_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(ApiKey).where(
        ApiKey.id == key_id, ApiKey.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "key not found")
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()
