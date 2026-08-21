"""Metadata objects + fields routes (tenant-scoped)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member
from truss_kernel.events import bus
from truss_kernel.models.metadata import FieldDef, FieldType, ObjectDef

router = APIRouter(prefix="/api/objects", tags=["objects"])


class FieldIn(BaseModel):
    slug: str
    name: str
    type: FieldType = FieldType.text
    required: bool = False
    position: int = 0
    options: dict = Field(default_factory=dict)


class ObjectIn(BaseModel):
    slug: str
    name: str
    name_plural: str = ""
    description: str = ""
    icon: str = "📦"
    fields: list[FieldIn] = Field(default_factory=list)


def obj_to_dict(o: ObjectDef) -> dict:
    return {
        "id": str(o.id),
        "slug": o.slug,
        "name": o.name,
        "name_plural": o.name_plural,
        "description": o.description,
        "icon": o.icon,
        "plugin_id": o.plugin_id,
        "is_builtin": o.is_builtin,
        "fields": [
            {
                "id": str(f.id),
                "slug": f.slug,
                "name": f.name,
                "type": f.type.value,
                "required": f.required,
                "position": f.position,
                "options": f.options,
            }
            for f in o.fields
        ],
    }


@router.get("")
async def list_objects(auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ObjectDef)
        .where(ObjectDef.tenant_id == auth.tenant_id)
        .options(selectinload(ObjectDef.fields))
        .order_by(ObjectDef.created_at)
    )
    return [obj_to_dict(o) for o in (await db.execute(stmt)).scalars().all()]


@router.post("", status_code=201)
async def create_object(body: ObjectIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(
        select(ObjectDef).where(ObjectDef.tenant_id == auth.tenant_id, ObjectDef.slug == body.slug)
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"object '{body.slug}' already exists")

    obj = ObjectDef(
        tenant_id=auth.tenant_id, slug=body.slug, name=body.name,
        name_plural=body.name_plural or body.name + "s",
        description=body.description, icon=body.icon, plugin_id="", is_builtin=False,
    )
    db.add(obj)
    await db.flush()
    for f in body.fields:
        db.add(FieldDef(object_id=obj.id, slug=f.slug, name=f.name, type=f.type,
                        required=f.required, position=f.position, options=f.options))
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="object.created",
                   payload={"object": body.slug}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(obj, attribute_names=["fields"])
    return obj_to_dict(obj)


@router.get("/{object_slug}")
async def get_object(object_slug: str, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    obj = (await db.execute(
        select(ObjectDef)
        .where(ObjectDef.tenant_id == auth.tenant_id, ObjectDef.slug == object_slug)
        .options(selectinload(ObjectDef.fields))
    )).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, "object not found")
    return obj_to_dict(obj)


@router.post("/{object_slug}/fields", status_code=201)
async def add_field(object_slug: str, body: FieldIn, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    obj = (await db.execute(
        select(ObjectDef)
        .where(ObjectDef.tenant_id == auth.tenant_id, ObjectDef.slug == object_slug)
        .options(selectinload(ObjectDef.fields))
    )).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, "object not found")
    if any(f.slug == body.slug for f in obj.fields):
        raise HTTPException(409, "field slug already exists")
    db.add(FieldDef(object_id=obj.id, slug=body.slug, name=body.name, type=body.type,
                    required=body.required, position=body.position, options=body.options))
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="object.field_added",
                   payload={"object": object_slug, "field": body.slug}, actor_id=auth.user_id)
    await db.commit()
    return {"ok": True}


@router.delete("/{object_slug}", status_code=204)
async def delete_object(object_slug: str, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    obj = (await db.execute(
        select(ObjectDef).where(ObjectDef.tenant_id == auth.tenant_id, ObjectDef.slug == object_slug)
    )).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, "object not found")
    if obj.is_builtin:
        raise HTTPException(400, "builtin plugin objects cannot be deleted (disable the plugin instead)")
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="object.deleted",
                   payload={"object": object_slug}, actor_id=auth.user_id)
    await db.delete(obj)
    await db.commit()
