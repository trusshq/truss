"""AI routes: BYOK key vault management + agent chat endpoint."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.ai import agent as agent_mod
from truss_kernel.ai import client as ai_client
from truss_kernel.ai.vault import decrypt_secret, encrypt_secret, mask
from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member
from truss_kernel.models.ai import AiKey

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---------- schemas ----------

class KeyIn(BaseModel):
    name: str = Field(default="default", max_length=80)
    provider: str = Field(default="openai-compatible", max_length=80)
    base_url: str = Field(max_length=500)
    model: str = Field(max_length=120)
    api_key: str = Field(default="", max_length=1000)
    is_default: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    key_id: uuid.UUID | None = None
    history: list[ChatMessage] = Field(default_factory=list)


def key_to_dict(k: AiKey, api_key_plain: str | None = None) -> dict:
    return {
        "id": str(k.id),
        "name": k.name,
        "provider": k.provider,
        "base_url": k.base_url,
        "model": k.model,
        "api_key_masked": mask(api_key_plain) if api_key_plain else None,
        "is_default": k.is_default,
        "created_at": k.created_at.isoformat() if k.created_at else None,
    }


async def _get_key(db: AsyncSession, tenant_id: uuid.UUID, key_id: uuid.UUID | None) -> AiKey:
    if key_id is not None:
        k = (await db.execute(select(AiKey).where(
            AiKey.id == key_id, AiKey.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if k is None:
            raise HTTPException(404, "AI key not found")
        return k
    # default key
    k = (await db.execute(select(AiKey).where(
        AiKey.tenant_id == tenant_id, AiKey.is_default.is_(True)
    ))).scalars().first()
    if k is None:
        k = (await db.execute(select(AiKey).where(
            AiKey.tenant_id == tenant_id
        ).order_by(AiKey.created_at))).scalars().first()
    if k is None:
        raise HTTPException(400, "no AI key configured — add one in AI Keys first")
    return k


# ---------- key management (admin) ----------

@router.get("/keys")
async def list_keys(auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(AiKey).where(AiKey.tenant_id == auth.tenant_id).order_by(AiKey.created_at)
    )).scalars().all()
    out = []
    for k in rows:
        plain = None
        if k.api_key_enc:
            try:
                plain = decrypt_secret(k.api_key_enc)
            except ValueError:
                plain = None
        out.append(key_to_dict(k, plain))
    return out


@router.post("/keys", status_code=201)
async def create_key(body: KeyIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(select(AiKey).where(
        AiKey.tenant_id == auth.tenant_id, AiKey.name == body.name
    ))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"key named '{body.name}' already exists")

    if body.is_default:
        for k in (await db.execute(select(AiKey).where(
            AiKey.tenant_id == auth.tenant_id, AiKey.is_default.is_(True)
        ))).scalars().all():
            k.is_default = False

    k = AiKey(
        tenant_id=auth.tenant_id,
        name=body.name,
        provider=body.provider,
        base_url=body.base_url.rstrip("/"),
        model=body.model,
        api_key_enc=encrypt_secret(body.api_key) if body.api_key else "",
        is_default=body.is_default,
    )
    db.add(k)
    await db.commit()
    await db.refresh(k)
    return key_to_dict(k, body.api_key or None)


@router.delete("/keys/{key_id}", status_code=204)
async def delete_key(key_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    k = (await db.execute(select(AiKey).where(
        AiKey.id == key_id, AiKey.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if k is None:
        raise HTTPException(404, "AI key not found")
    await db.delete(k)
    await db.commit()


# ---------- agent chat ----------

@router.post("/chat")
async def chat(body: ChatIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    key = await _get_key(db, auth.tenant_id, body.key_id)
    history = [{"role": m.role, "content": m.content} for m in body.history[-10:]]
    try:
        result = await agent_mod.run_agent(
            db, auth.tenant_id, auth.user_id, key, body.message, history=history
        )
    except ai_client.ProviderError as e:
        raise HTTPException(502, str(e)) from e
    return result
