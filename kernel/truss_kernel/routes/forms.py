"""Public forms routes (Phase N): admin CRUD + unauthenticated intake endpoints.

Admin: /api/forms — create/list/patch/delete forms bound to an object.
Public (no auth): /api/public/forms/{slug} — schema; POST — submit.

Submissions create real records through the same validated path as the API
(actor_type="form"), so automations, AI triggers, and the audit log all fire.
Fields with hidden_roles are never exposed publicly.
"""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.forms import PublicForm
from truss_kernel.models.metadata import ObjectDef
from truss_kernel.services import records as svc

router = APIRouter(prefix="/api/forms", tags=["forms"])
public_router = APIRouter(prefix="/api/public/forms", tags=["forms-public"])

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")


class FormIn(BaseModel):
    slug: str = Field(min_length=3, max_length=60)
    name: str = Field(min_length=1, max_length=150)
    description: str = ""
    object: str = Field(min_length=1, max_length=100)
    fields: list[str] = []
    active: bool = True


class FormUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[str] | None = None
    active: bool | None = None


async def _get_object(db: AsyncSession, tenant_id, slug: str) -> ObjectDef:
    try:
        return await svc.get_object(db, tenant_id, slug)
    except svc.ObjectNotFound as e:
        raise HTTPException(404, f"object '{slug}' not found") from e


def _public_fields(obj: ObjectDef, whitelist: list[str]) -> list[dict]:
    """Fields exposed on the public form: whitelisted (or all), minus hidden_roles."""
    fields = []
    for f in obj.fields:
        if whitelist and f.slug not in whitelist:
            continue
        if (f.options or {}).get("hidden_roles"):
            continue  # never expose role-hidden fields publicly
        fields.append({
            "slug": f.slug,
            "name": f.name,
            "type": f.type.value if hasattr(f.type, "value") else str(f.type),
            "required": f.required,
            "options": f.options or {},
        })
    return fields


def _serialize(form: PublicForm) -> dict:
    return {
        "id": str(form.id),
        "slug": form.slug,
        "name": form.name,
        "description": form.description,
        "object": form.object_slug,
        "fields": form.fields,
        "active": form.active,
        "submissions": form.submissions,
        "created_at": form.created_at.isoformat() if form.created_at else None,
    }


# ---------------- admin CRUD ----------------

@router.post("", status_code=201)
async def create_form(body: FormIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if not SLUG_RE.match(body.slug):
        raise HTTPException(422, "slug must be lowercase letters/digits/hyphens, 3-60 chars")
    obj = await _get_object(db, auth.tenant_id, body.object)

    existing = (await db.execute(select(PublicForm).where(PublicForm.slug == body.slug))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"form slug '{body.slug}' already exists")

    # validate whitelist against real, exposable fields
    exposable = {f.slug for f in obj.fields if not (f.options or {}).get("hidden_roles")}
    bad = [s for s in body.fields if s not in exposable]
    if bad:
        raise HTTPException(422, f"unknown or hidden fields: {', '.join(bad)}")

    form = PublicForm(
        tenant_id=auth.tenant_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        object_slug=obj.slug,
        fields=body.fields,
        active=body.active,
        created_by=auth.user_id,
    )
    db.add(form)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="form.created",
        payload={"slug": form.slug, "object": obj.slug}, actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(form)


@router.get("")
async def list_forms(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(PublicForm).where(PublicForm.tenant_id == auth.tenant_id)
        .order_by(PublicForm.created_at.desc())
    )).scalars().all()
    return {"items": [_serialize(f) for f in rows], "total": len(rows)}


async def _get_form(db: AsyncSession, tenant_id, form_id: uuid.UUID) -> PublicForm:
    form = (await db.execute(select(PublicForm).where(
        PublicForm.id == form_id, PublicForm.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if form is None:
        raise HTTPException(404, "form not found")
    return form


@router.patch("/{form_id}")
async def update_form(form_id: uuid.UUID, body: FormUpdateIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    form = await _get_form(db, auth.tenant_id, form_id)
    obj = await _get_object(db, auth.tenant_id, form.object_slug)
    if body.name is not None:
        form.name = body.name
    if body.description is not None:
        form.description = body.description
    if body.fields is not None:
        exposable = {f.slug for f in obj.fields if not (f.options or {}).get("hidden_roles")}
        bad = [s for s in body.fields if s not in exposable]
        if bad:
            raise HTTPException(422, f"unknown or hidden fields: {', '.join(bad)}")
        form.fields = body.fields
    if body.active is not None:
        form.active = body.active
    await db.commit()
    return _serialize(form)


@router.delete("/{form_id}")
async def delete_form(form_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    form = await _get_form(db, auth.tenant_id, form_id)
    await db.delete(form)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="form.deleted",
        payload={"slug": form.slug}, actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}


# ---------------- public (no auth) ----------------

@public_router.get("/{slug}")
async def public_schema(slug: str, db: AsyncSession = Depends(get_db)):
    """Unauthenticated form schema for rendering the intake page."""
    form = (await db.execute(
        select(PublicForm).where(PublicForm.slug == slug, PublicForm.active.is_(True))
    )).scalar_one_or_none()
    if form is None:
        raise HTTPException(404, "form not found or inactive")
    obj = (await db.execute(
        select(ObjectDef).where(ObjectDef.tenant_id == form.tenant_id, ObjectDef.slug == form.object_slug)
        .options(selectinload(ObjectDef.fields))
    )).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, "form's object no longer exists")
    return {
        "slug": form.slug,
        "name": form.name,
        "description": form.description,
        "fields": _public_fields(obj, form.fields),
    }


class SubmitIn(BaseModel):
    data: dict


@public_router.post("/{slug}", status_code=201)
async def public_submit(slug: str, body: SubmitIn, db: AsyncSession = Depends(get_db)):
    """Unauthenticated submission -> creates a validated record (actor_type='form')."""
    form = (await db.execute(
        select(PublicForm).where(PublicForm.slug == slug, PublicForm.active.is_(True))
    )).scalar_one_or_none()
    if form is None:
        raise HTTPException(404, "form not found or inactive")
    obj = await _get_object(db, form.tenant_id, form.object_slug)

    # only whitelisted, exposable fields are accepted
    allowed = {f["slug"] for f in _public_fields(obj, form.fields)}
    rejected = [k for k in body.data if k not in allowed]
    if rejected:
        raise HTTPException(422, f"fields not accepted by this form: {', '.join(rejected)}")

    try:
        rec = await svc.create_record(
            db, form.tenant_id, None, obj, body.data, actor_type="form",
        )
    except svc.ValidationError as e:
        raise HTTPException(422, str(e)) from e

    form.submissions += 1
    await bus.emit(
        db, tenant_id=form.tenant_id, event_type="form.submitted",
        payload={"slug": form.slug, "object": obj.slug, "record_id": str(rec.id)},
        actor_id=None, plugin_id="",
    )
    await db.commit()
    return {"ok": True, "id": str(rec.id), "form": form.slug}
