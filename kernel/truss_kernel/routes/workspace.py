"""Workspace routes: namespace/profile settings, members, invites, roles.

Access control model:
- owner: everything, including workspace deletion and owner transfer
- admin: manage members/invites (cannot touch owner), edit workspace settings
- member: view members, no management
- viewer: view members, no management
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, get_auth, require_admin, require_viewer
from truss_kernel.events import bus
from truss_kernel.models.tenant import ROLE_RANK, Invite, Membership, Tenant, TenantRole, User

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

INVITE_TTL_DAYS = 7
VALID_ROLES = {r.value for r in TenantRole}

# ---------------------------------------------------------------------------
# Roles matrix (public capability map the UI renders)
# ---------------------------------------------------------------------------

ROLES_MATRIX = [
    {
        "role": "owner",
        "label": "Owner",
        "description": "Full control. Billing, workspace deletion, owner transfer.",
        "capabilities": {
            "view_data": True, "create_edit_records": True, "delete_records": True,
            "manage_plugins": True, "manage_connectors": True, "manage_ai_keys": True,
            "manage_automations": True, "manage_members": True, "edit_workspace": True,
            "delete_workspace": True,
        },
    },
    {
        "role": "admin",
        "label": "Admin",
        "description": "Manage everything except workspace deletion and the owner.",
        "capabilities": {
            "view_data": True, "create_edit_records": True, "delete_records": True,
            "manage_plugins": True, "manage_connectors": True, "manage_ai_keys": True,
            "manage_automations": True, "manage_members": True, "edit_workspace": True,
            "delete_workspace": False,
        },
    },
    {
        "role": "member",
        "label": "Member",
        "description": "Work with data: create and edit records, use AI and automations.",
        "capabilities": {
            "view_data": True, "create_edit_records": True, "delete_records": True,
            "manage_plugins": False, "manage_connectors": False, "manage_ai_keys": False,
            "manage_automations": True, "manage_members": False, "edit_workspace": False,
            "delete_workspace": False,
        },
    },
    {
        "role": "viewer",
        "label": "Viewer",
        "description": "Read-only. Can see data, dashboards and boards — cannot change anything.",
        "capabilities": {
            "view_data": True, "create_edit_records": False, "delete_records": False,
            "manage_plugins": False, "manage_connectors": False, "manage_ai_keys": False,
            "manage_automations": False, "manage_members": False, "edit_workspace": False,
            "delete_workspace": False,
        },
    },
]


def _serialize_user(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "title": u.title,
        "phone": u.phone,
        "avatar_url": u.avatar_url,
        "timezone": u.timezone,
        "locale": u.locale,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _serialize_tenant(t: Tenant) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "description": t.description,
        "website": t.website,
        "industry": t.industry,
        "company_size": t.company_size,
        "logo_url": t.logo_url,
        "timezone": t.timezone,
        "locale": t.locale,
        "settings": t.settings or {},
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _serialize_invite(i: Invite) -> dict:
    return {
        "id": str(i.id),
        "email": i.email,
        "role": i.role.value,
        "token": i.token,
        "status": "pending" if i.is_pending else ("accepted" if i.accepted_at else "revoked" if i.revoked_at else "expired"),
        "expires_at": i.expires_at.isoformat(),
        "accepted_at": i.accepted_at.isoformat() if i.accepted_at else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


# ---------------------------------------------------------------------------
# Workspace settings (namespace + profile)
# ---------------------------------------------------------------------------

@router.get("")
async def get_workspace(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, auth.tenant_id)
    if tenant is None:
        raise HTTPException(404, "Workspace not found")
    return _serialize_tenant(tenant)


class WorkspaceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=100)
    company_size: str | None = Field(default=None, max_length=50)
    logo_url: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=16)
    settings: dict | None = None


@router.patch("")
async def update_workspace(
    body: WorkspaceUpdateIn,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, auth.tenant_id)
    if tenant is None:
        raise HTTPException(404, "Workspace not found")
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(tenant, k, v)
    await bus.emit(db, tenant_id=tenant.id, event_type="workspace.updated",
                   payload={"fields": list(updates.keys())}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.get("/roles")
async def roles_matrix(auth: AuthContext = Depends(require_viewer)):
    """The capability matrix for every role — rendered by the UI."""
    return ROLES_MATRIX


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

@router.get("/members")
async def list_members(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(Membership.tenant_id == auth.tenant_id)
        .order_by(Membership.created_at)
    )).all()
    return [
        {
            "membership_id": str(m.id),
            "role": m.role.value,
            "joined_at": m.created_at.isoformat() if m.created_at else None,
            "user": _serialize_user(u),
        }
        for m, u in rows
    ]


class RoleChangeIn(BaseModel):
    role: str


@router.patch("/members/{membership_id}")
async def change_member_role(
    membership_id: uuid.UUID,
    body: RoleChangeIn,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Valid: {', '.join(sorted(VALID_ROLES))}")
    new_role = TenantRole(body.role)

    membership = await db.get(Membership, membership_id)
    if membership is None or membership.tenant_id != auth.tenant_id:
        raise HTTPException(404, "Membership not found")

    # cannot demote/promote the owner, and cannot change your own role
    if membership.role == TenantRole.owner:
        raise HTTPException(403, "The owner's role cannot be changed. Transfer ownership first.")
    if membership.user_id == auth.user_id:
        raise HTTPException(403, "You cannot change your own role.")
    # admins cannot grant admin/owner
    if auth.role == TenantRole.admin and ROLE_RANK[new_role] >= ROLE_RANK[TenantRole.admin]:
        raise HTTPException(403, "Admins can only assign member or viewer roles.")

    membership.role = new_role
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="member.role_changed",
                   payload={"user_id": str(membership.user_id), "role": new_role.value},
                   actor_id=auth.user_id)
    await db.commit()
    return {"membership_id": str(membership.id), "role": new_role.value}


@router.delete("/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    membership_id: uuid.UUID,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    membership = await db.get(Membership, membership_id)
    if membership is None or membership.tenant_id != auth.tenant_id:
        raise HTTPException(404, "Membership not found")
    if membership.role == TenantRole.owner:
        raise HTTPException(403, "The owner cannot be removed. Transfer ownership first.")
    if membership.user_id == auth.user_id:
        raise HTTPException(403, "You cannot remove yourself. Ask another admin or the owner.")

    await bus.emit(db, tenant_id=auth.tenant_id, event_type="member.removed",
                   payload={"user_id": str(membership.user_id)}, actor_id=auth.user_id)
    await db.delete(membership)
    await db.commit()


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------

class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"


@router.get("/invites")
async def list_invites(auth: AuthContext = Depends(require_viewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Invite)
        .where(Invite.tenant_id == auth.tenant_id)
        .order_by(Invite.created_at.desc())
    )).scalars().all()
    return [_serialize_invite(i) for i in rows]


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: InviteIn,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(400, f"Invalid role. Valid: {', '.join(sorted(VALID_ROLES))}")
    if body.role == TenantRole.owner.value:
        raise HTTPException(400, "Cannot invite someone as owner. Transfer ownership instead.")
    # admins can only invite member/viewer
    if auth.role == TenantRole.admin and body.role in (TenantRole.admin.value,):
        raise HTTPException(403, "Admins can only invite members or viewers.")

    email = body.email.lower()
    # already a member?
    existing_user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing_user:
        already = (await db.execute(
            select(Membership).where(Membership.tenant_id == auth.tenant_id, Membership.user_id == existing_user.id)
        )).scalar_one_or_none()
        if already:
            raise HTTPException(409, "That user is already a member of this workspace.")

    # replace any pending invite for the same email
    pending = (await db.execute(
        select(Invite).where(Invite.tenant_id == auth.tenant_id, Invite.email == email)
    )).scalars().all()
    for p in pending:
        if p.is_pending:
            await db.delete(p)

    invite = Invite(
        tenant_id=auth.tenant_id,
        email=email,
        role=TenantRole(body.role),
        token=secrets.token_urlsafe(32),
        invited_by=auth.user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    await bus.emit(db, tenant_id=auth.tenant_id, event_type="invite.created",
                   payload={"email": email, "role": body.role}, actor_id=auth.user_id)
    await db.commit()
    await db.refresh(invite)
    return _serialize_invite(invite)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    invite_id: uuid.UUID,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    invite = await db.get(Invite, invite_id)
    if invite is None or invite.tenant_id != auth.tenant_id:
        raise HTTPException(404, "Invite not found")
    invite.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/invites/by-token/{token}")
async def get_invite_by_token(token: str, db: AsyncSession = Depends(get_db)):
    """Public: resolve an invite token to workspace + role (for the accept screen)."""
    invite = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if invite is None or not invite.is_pending:
        raise HTTPException(404, "Invite not found, expired, or already used")
    tenant = await db.get(Tenant, invite.tenant_id)
    return {
        "email": invite.email,
        "role": invite.role.value,
        "workspace_name": tenant.name,
        "workspace_slug": tenant.slug,
        "expires_at": invite.expires_at.isoformat(),
    }


class AcceptInviteIn(BaseModel):
    token: str
    # existing user accepting: nothing else needed (uses their auth)
    # new user accepting: supply account details
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str | None = None


@router.post("/invites/accept", status_code=status.HTTP_201_CREATED)
async def accept_invite(body: AcceptInviteIn, db: AsyncSession = Depends(get_db)):
    """Accept an invite. Two paths:
    1. Logged-in user whose email matches -> joins directly.
    2. New user -> supply password (+ optional name), account is created.
    """
    from truss_kernel.security import create_access_token, hash_password

    invite = (await db.execute(select(Invite).where(Invite.token == body.token))).scalar_one_or_none()
    if invite is None or not invite.is_pending:
        raise HTTPException(404, "Invite not found, expired, or already used")

    user = (await db.execute(select(User).where(User.email == invite.email))).scalar_one_or_none()
    if user is None:
        if not body.password:
            raise HTTPException(400, "New account: password is required to accept this invite")
        user = User(
            email=invite.email,
            full_name=body.full_name or invite.email.split("@")[0],
            password_hash=hash_password(body.password),
        )
        db.add(user)
        await db.flush()

    # idempotent: if membership already exists, just mark invite accepted
    membership = (await db.execute(
        select(Membership).where(Membership.tenant_id == invite.tenant_id, Membership.user_id == user.id)
    )).scalar_one_or_none()
    if membership is None:
        membership = Membership(tenant_id=invite.tenant_id, user_id=user.id, role=invite.role)
        db.add(membership)

    invite.accepted_at = datetime.now(timezone.utc)
    user.last_login_at = datetime.now(timezone.utc)
    await bus.emit(db, tenant_id=invite.tenant_id, event_type="member.joined",
                   payload={"email": invite.email, "role": invite.role.value, "via": "invite"})
    await db.commit()

    token = create_access_token(str(user.id), str(invite.tenant_id), invite.role.value)
    tenant = await db.get(Tenant, invite.tenant_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "tenant_id": str(invite.tenant_id),
        "tenant_slug": tenant.slug,
        "role": invite.role.value,
        "user_id": str(user.id),
        "email": user.email,
    }


# ---------------------------------------------------------------------------
# Danger zone
# ---------------------------------------------------------------------------

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(auth: AuthContext = Depends(get_auth), db: AsyncSession = Depends(get_db)):
    """Owner only. Deletes the workspace and all its data."""
    if auth.role != TenantRole.owner:
        raise HTTPException(403, "Only the owner can delete a workspace")
    tenant = await db.get(Tenant, auth.tenant_id)
    if tenant is None:
        raise HTTPException(404, "Workspace not found")
    await db.delete(tenant)  # cascades to memberships + invites
    await db.commit()
