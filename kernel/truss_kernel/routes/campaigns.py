"""Campaigns routes (Phase AC): CRUD, lifecycle, and performance tracking."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, require_admin, require_member, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.campaigns import Campaign

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

VALID_STATUS = {"draft", "scheduled", "sent", "completed"}
VALID_CHANNEL = {"email", "sms", "social", "ads"}


class CampaignIn(BaseModel):
    name: str
    channel: str = "email"
    subject: str = ""
    content: str = ""
    audience: str = ""
    audience_size: int = Field(default=0, ge=0)
    scheduled_for: str = ""


class CampaignPatch(BaseModel):
    name: str | None = None
    channel: str | None = None
    subject: str | None = None
    content: str | None = None
    audience: str | None = None
    audience_size: int | None = Field(default=None, ge=0)
    scheduled_for: str | None = None


class PerfIn(BaseModel):
    opened: int = Field(default=0, ge=0)
    clicked: int = Field(default=0, ge=0)


def _rates(c: Campaign) -> tuple[float, float]:
    if c.sent_count <= 0:
        return 0.0, 0.0
    return round(c.opened_count / c.sent_count * 100, 2), round(c.clicked_count / c.sent_count * 100, 2)


def _serialize(c: Campaign) -> dict:
    open_rate, click_rate = _rates(c)
    return {
        "id": str(c.id),
        "name": c.name,
        "channel": c.channel,
        "subject": c.subject,
        "content": c.content,
        "audience": c.audience,
        "audience_size": c.audience_size,
        "status": c.status,
        "scheduled_for": c.scheduled_for,
        "sent_at": c.sent_at,
        "sent_count": c.sent_count,
        "opened_count": c.opened_count,
        "clicked_count": c.clicked_count,
        "open_rate": open_rate,
        "click_rate": click_rate,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def _get_campaign(db: AsyncSession, tenant_id, cid: uuid.UUID) -> Campaign:
    c = (await db.execute(select(Campaign).where(
        Campaign.tenant_id == tenant_id, Campaign.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Campaign not found")
    return c


@router.post("", status_code=201)
async def create_campaign(body: CampaignIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    if body.channel not in VALID_CHANNEL:
        raise HTTPException(400, f"Invalid channel. Valid: {', '.join(sorted(VALID_CHANNEL))}")
    c = Campaign(
        tenant_id=auth.tenant_id,
        name=body.name,
        channel=body.channel,
        subject=body.subject,
        content=body.content,
        audience=body.audience,
        audience_size=body.audience_size,
        status="draft",
        scheduled_for=body.scheduled_for,
        created_by=auth.user_id,
    )
    db.add(c)
    await db.flush()
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="campaign.created",
                   payload={"campaign_id": str(c.id), "name": c.name, "channel": c.channel},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.get("")
async def list_campaigns(status: str | None = None, channel: str | None = None,
                         auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    stmt = select(Campaign).where(Campaign.tenant_id == auth.tenant_id)
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(400, f"Invalid status. Valid: {', '.join(sorted(VALID_STATUS))}")
        stmt = stmt.where(Campaign.status == status)
    if channel:
        if channel not in VALID_CHANNEL:
            raise HTTPException(400, f"Invalid channel. Valid: {', '.join(sorted(VALID_CHANNEL))}")
        stmt = stmt.where(Campaign.channel == channel)
    rows = (await db.execute(stmt.order_by(Campaign.created_at.desc()))).scalars().all()
    return {"items": [_serialize(c) for c in rows], "total": len(rows)}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: uuid.UUID, auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    return _serialize(await _get_campaign(db, auth.tenant_id, campaign_id))


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: uuid.UUID, body: CampaignPatch, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_campaign(db, auth.tenant_id, campaign_id)
    if c.status != "draft":
        raise HTTPException(409, f"Campaign is {c.status}; only draft campaigns can be edited")
    if body.name is not None:
        c.name = body.name
    if body.channel is not None:
        if body.channel not in VALID_CHANNEL:
            raise HTTPException(400, f"Invalid channel. Valid: {', '.join(sorted(VALID_CHANNEL))}")
        c.channel = body.channel
    if body.subject is not None:
        c.subject = body.subject
    if body.content is not None:
        c.content = body.content
    if body.audience is not None:
        c.audience = body.audience
    if body.audience_size is not None:
        c.audience_size = body.audience_size
    if body.scheduled_for is not None:
        c.scheduled_for = body.scheduled_for
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="campaign.updated",
                   payload={"campaign_id": str(c.id), "name": c.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.delete("/{campaign_id}", status_code=200)
async def delete_campaign(campaign_id: uuid.UUID, auth: AuthContext = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    c = await _get_campaign(db, auth.tenant_id, campaign_id)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="campaign.deleted",
                   payload={"campaign_id": str(c.id), "name": c.name}, actor_id=auth.user_id)
    await db.delete(c)
    await db.commit()
    return {"deleted": True}


@router.post("/{campaign_id}/schedule")
async def schedule_campaign(campaign_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_campaign(db, auth.tenant_id, campaign_id)
    if c.status != "draft":
        raise HTTPException(409, f"Campaign is {c.status}; only draft campaigns can be scheduled")
    if not c.scheduled_for:
        raise HTTPException(400, "Set scheduled_for before scheduling")
    c.status = "scheduled"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="campaign.scheduled",
                   payload={"campaign_id": str(c.id), "name": c.name, "scheduled_for": c.scheduled_for},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.post("/{campaign_id}/send")
async def send_campaign(campaign_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_campaign(db, auth.tenant_id, campaign_id)
    if c.status not in ("draft", "scheduled"):
        raise HTTPException(409, f"Campaign is {c.status}; only draft/scheduled campaigns can be sent")
    c.status = "sent"
    c.sent_at = datetime.now(timezone.utc).isoformat()
    # self-hosted mock send: delivered to the whole estimated audience
    c.sent_count = c.audience_size
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="campaign.sent",
                   payload={"campaign_id": str(c.id), "name": c.name, "sent_count": c.sent_count},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.post("/{campaign_id}/complete")
async def complete_campaign(campaign_id: uuid.UUID, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    c = await _get_campaign(db, auth.tenant_id, campaign_id)
    if c.status != "sent":
        raise HTTPException(409, f"Campaign is {c.status}; only sent campaigns can be completed")
    c.status = "completed"
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="campaign.completed",
                   payload={"campaign_id": str(c.id), "name": c.name}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.post("/{campaign_id}/performance")
async def record_performance(campaign_id: uuid.UUID, body: PerfIn, auth: AuthContext = Depends(require_member), db: AsyncSession = Depends(get_db)):
    """Increment open/click counters for a sent campaign."""
    c = await _get_campaign(db, auth.tenant_id, campaign_id)
    if c.status not in ("sent", "completed"):
        raise HTTPException(409, f"Campaign is {c.status}; performance can only be recorded once sent")
    c.opened_count += body.opened
    c.clicked_count += body.clicked
    if c.opened_count > c.sent_count:
        c.opened_count = c.sent_count
    if c.clicked_count > c.opened_count:
        c.clicked_count = c.opened_count
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="campaign.performance",
                   payload={"campaign_id": str(c.id), "name": c.name,
                            "opened": c.opened_count, "clicked": c.clicked_count},
                   actor_id=auth.user_id)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)
