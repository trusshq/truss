"""Auth routes: signup (creates tenant + owner), login, me, profile, password."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.deps import AuthContext, get_auth
from truss_kernel.events import bus
from truss_kernel.models.tenant import Membership, Tenant, TenantRole, User
from truss_kernel.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""
    tenant_name: str = Field(min_length=2, max_length=200)
    tenant_slug: str = Field(min_length=2, max_length=60)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    tenant_slug: str
    role: str
    user_id: str
    email: str


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupIn, db: AsyncSession = Depends(get_db)):
    if not SLUG_RE.match(body.tenant_slug):
        raise HTTPException(400, "tenant_slug must be lowercase letters, digits, hyphens")

    if (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none():
        raise HTTPException(409, "Email already registered")
    if (await db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug))).scalar_one_or_none():
        raise HTTPException(409, "Tenant slug already taken")

    tenant = Tenant(name=body.tenant_name, slug=body.tenant_slug)
    user = User(email=body.email, full_name=body.full_name, password_hash=hash_password(body.password))
    db.add_all([tenant, user])
    await db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=TenantRole.owner))
    await db.flush()

    await bus.emit(db, tenant_id=tenant.id, event_type="tenant.created",
                   payload={"slug": tenant.slug}, actor_id=user.id)
    await db.commit()

    token = create_access_token(str(user.id), str(tenant.id), TenantRole.owner.value)
    return TokenOut(access_token=token, tenant_id=str(tenant.id), tenant_slug=tenant.slug,
                    role=TenantRole.owner.value, user_id=str(user.id), email=user.email)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    membership = (await db.execute(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
    )).scalars().first()
    if membership is None:
        raise HTTPException(403, "User has no tenant membership")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    tenant = await db.get(Tenant, membership.tenant_id)
    token = create_access_token(str(user.id), str(membership.tenant_id), membership.role.value)
    return TokenOut(access_token=token, tenant_id=str(membership.tenant_id),
                    tenant_slug=tenant.slug, role=membership.role.value,
                    user_id=str(user.id), email=user.email)


@router.get("/me")
async def me(auth: AuthContext = Depends(get_auth), db: AsyncSession = Depends(get_db)):
    tenant = await db.get(Tenant, auth.tenant_id)
    user = await db.get(User, auth.user_id)
    return {
        "user_id": str(auth.user_id),
        "email": auth.email,
        "full_name": user.full_name if user else "",
        "title": user.title if user else "",
        "phone": user.phone if user else "",
        "avatar_url": user.avatar_url if user else "",
        "timezone": user.timezone if user else "UTC",
        "locale": user.locale if user else "en-US",
        "last_login_at": user.last_login_at.isoformat() if user and user.last_login_at else None,
        "tenant_id": str(auth.tenant_id),
        "tenant_name": tenant.name,
        "tenant_slug": tenant.slug,
        "role": auth.role.value,
    }


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class ProfileUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=16)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdateIn,
    auth: AuthContext = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, auth.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "title": user.title,
        "phone": user.phone,
        "avatar_url": user.avatar_url,
        "timezone": user.timezone,
        "locale": user.locale,
    }


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password")
async def change_password(
    body: PasswordChangeIn,
    auth: AuthContext = Depends(get_auth),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, auth.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"status": "ok"}
