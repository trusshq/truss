"""Knowledge base routes (Phase Q): admin CRUD + publish + public help center.

Admin: /api/kb — create/list/get/patch/delete articles, publish/unpublish.
Public (no auth): /api/public/kb — list published; /api/public/kb/{slug} — read.

Slugs are unique per tenant. Publishing flips status to 'published' and makes
the article visible on the public endpoints.
"""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.kb import KBArticle
from truss_kernel.models.tenant import Tenant

router = APIRouter(prefix="/api/kb", tags=["kb"])
public_router = APIRouter(prefix="/api/public/kb", tags=["kb-public"])

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=3, max_length=80)
    body: str = ""
    category: str = ""
    tags: list[str] = []
    object: str | None = None
    record_id: str | None = None


class ArticleUpdateIn(BaseModel):
    title: str | None = None
    body: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    object: str | None = None
    record_id: str | None = None


def _serialize(a: KBArticle, include_body: bool = True) -> dict:
    out = {
        "id": str(a.id),
        "title": a.title,
        "slug": a.slug,
        "category": a.category,
        "tags": a.tags,
        "status": a.status,
        "object": a.object_slug,
        "record_id": str(a.record_id) if a.record_id else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
    if include_body:
        out["body"] = a.body
    return out


def _validate_record_id(record_id: str | None) -> uuid.UUID | None:
    if not record_id:
        return None
    try:
        return uuid.UUID(record_id)
    except ValueError as e:
        raise HTTPException(422, "record_id must be a UUID") from e


async def _unique_slug(db: AsyncSession, tenant_id, slug: str, exclude_id=None) -> None:
    stmt = select(KBArticle).where(KBArticle.tenant_id == tenant_id, KBArticle.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(KBArticle.id != exclude_id)
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(409, f"article slug '{slug}' already exists")


# ---------------- admin CRUD ----------------

@router.post("", status_code=201)
async def create_article(body: ArticleIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if not SLUG_RE.match(body.slug):
        raise HTTPException(422, "slug must be lowercase letters/digits/hyphens, 3-80 chars")
    await _unique_slug(db, auth.tenant_id, body.slug)
    article = KBArticle(
        tenant_id=auth.tenant_id,
        title=body.title,
        slug=body.slug,
        body=body.body,
        category=body.category,
        tags=body.tags,
        object_slug=body.object,
        record_id=_validate_record_id(body.record_id),
        created_by=auth.user_id,
    )
    db.add(article)
    await db.flush()
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="kb.article_created",
        payload={"slug": article.slug, "title": article.title}, actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(article)


@router.get("")
async def list_articles(
    category: str | None = None,
    status: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    auth: AuthContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(KBArticle).where(KBArticle.tenant_id == auth.tenant_id)
    if category:
        stmt = stmt.where(KBArticle.category == category)
    if status:
        stmt = stmt.where(KBArticle.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(KBArticle.title.ilike(like), KBArticle.body.ilike(like)))
    rows = (await db.execute(stmt.order_by(KBArticle.updated_at.desc()))).scalars().all()
    return {"items": [_serialize(a, include_body=False) for a in rows], "total": len(rows)}


async def _get_article(db: AsyncSession, tenant_id, article_id: uuid.UUID) -> KBArticle:
    article = (await db.execute(select(KBArticle).where(
        KBArticle.id == article_id, KBArticle.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if article is None:
        raise HTTPException(404, "article not found")
    return article


@router.get("/{article_id}")
async def get_article(article_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_article(db, auth.tenant_id, article_id))


@router.patch("/{article_id}")
async def update_article(article_id: uuid.UUID, body: ArticleUpdateIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    article = await _get_article(db, auth.tenant_id, article_id)
    if body.title is not None:
        article.title = body.title
    if body.body is not None:
        article.body = body.body
    if body.category is not None:
        article.category = body.category
    if body.tags is not None:
        article.tags = body.tags
    if body.object is not None:
        article.object_slug = body.object or None
    if body.record_id is not None:
        article.record_id = _validate_record_id(body.record_id)
    await db.commit()
    return _serialize(article)


@router.delete("/{article_id}")
async def delete_article(article_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    article = await _get_article(db, auth.tenant_id, article_id)
    await db.delete(article)
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="kb.article_deleted",
        payload={"slug": article.slug, "title": article.title}, actor_id=auth.user_id,
    )
    await db.commit()
    return {"ok": True}


@router.post("/{article_id}/publish", status_code=200)
async def publish_article(article_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    article = await _get_article(db, auth.tenant_id, article_id)
    if not article.body.strip():
        raise HTTPException(422, "cannot publish an empty article")
    article.status = "published"
    await bus.emit(
        db, tenant_id=auth.tenant_id, event_type="kb.article_published",
        payload={"slug": article.slug, "title": article.title}, actor_id=auth.user_id,
    )
    await db.commit()
    return _serialize(article, include_body=False)


@router.post("/{article_id}/unpublish", status_code=200)
async def unpublish_article(article_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    article = await _get_article(db, auth.tenant_id, article_id)
    article.status = "draft"
    await db.commit()
    return _serialize(article, include_body=False)


# ---------------- public help center (no auth) ----------------
# Scoped by tenant slug (globally unique) so one tenant can never read
# another tenant's published articles.


async def _public_tenant(db: AsyncSession, tenant_slug: str):
    tenant = (await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(404, "workspace not found")
    return tenant


@public_router.get("/{tenant_slug}")
async def public_list(tenant_slug: str, category: str | None = None, db: AsyncSession = Depends(get_db)):
    """Published articles for one workspace only (no bodies)."""
    tenant = await _public_tenant(db, tenant_slug)
    stmt = select(KBArticle).where(
        KBArticle.tenant_id == tenant.id, KBArticle.status == "published",
    )
    if category:
        stmt = stmt.where(KBArticle.category == category)
    rows = (await db.execute(stmt.order_by(KBArticle.title.asc()))).scalars().all()
    return {"items": [_serialize(a, include_body=False) for a in rows], "total": len(rows)}


@public_router.get("/{tenant_slug}/{slug}")
async def public_read(tenant_slug: str, slug: str, db: AsyncSession = Depends(get_db)):
    tenant = await _public_tenant(db, tenant_slug)
    article = (await db.execute(select(KBArticle).where(
        KBArticle.tenant_id == tenant.id,
        KBArticle.slug == slug,
        KBArticle.status == "published",
    ))).scalar_one_or_none()
    if article is None:
        raise HTTPException(404, "article not found or not published")
    return _serialize(article)
