"""FastAPI dependencies: current user, tenant scoping, RBAC.

Two credential types are accepted on the Authorization: Bearer header:
1. JWT access tokens (interactive users)
2. API keys (truss_sk_…) — act as their owner, capped by scopes (Phase A4)
"""
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.models.apikey import KEY_PREFIX, ApiKey
from truss_kernel.models.tenant import Membership, TenantRole, User
from truss_kernel.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: TenantRole
    email: str
    # API-key auth: scopes the key grants (empty list = full owner access via JWT)
    scopes: list[str] = field(default_factory=list)
    is_api_key: bool = False

    def has_scope(self, scope: str) -> bool:
        """JWT sessions have all scopes; API keys only their granted ones."""
        if not self.is_api_key:
            return True
        return scope in self.scopes


async def _auth_via_api_key(db: AsyncSession, key: str) -> AuthContext | None:
    """Resolve an API key to an AuthContext, or None if invalid/revoked."""
    if not key.startswith(KEY_PREFIX):
        return None
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    row = (await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    user = await db.get(User, row.user_id)
    if user is None:
        return None
    membership = (await db.execute(select(Membership).where(
        Membership.user_id == user.id, Membership.tenant_id == row.tenant_id
    ))).scalar_one_or_none()
    if membership is None:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return AuthContext(
        user_id=user.id,
        tenant_id=row.tenant_id,
        role=membership.role,
        email=user.email,
        scopes=list(row.scopes or []),
        is_api_key=True,
    )


async def get_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = creds.credentials

    # API key path
    if token.startswith(KEY_PREFIX):
        ctx = await _auth_via_api_key(db, token)
        if ctx is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key")
        return ctx

    # JWT path
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    # verify membership still exists
    stmt = select(Membership).where(
        Membership.user_id == user.id,
        Membership.tenant_id == uuid.UUID(payload["tid"]),
    )
    membership = (await db.execute(stmt)).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this tenant")

    return AuthContext(
        user_id=user.id,
        tenant_id=membership.tenant_id,
        role=membership.role,
        email=user.email,
    )


def require_roles(*roles: TenantRole):
    """Dependency factory: require one of the given roles."""

    async def checker(auth: AuthContext = Depends(get_auth)) -> AuthContext:
        if auth.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires role: {', '.join(r.value for r in roles)}",
            )
        return auth

    return checker


# Convenience presets
require_admin = require_roles(TenantRole.owner, TenantRole.admin)
require_member = require_roles(TenantRole.owner, TenantRole.admin, TenantRole.member)
# viewer is read-only: allowed on GET/list endpoints, never on mutations
require_viewer = require_roles(TenantRole.owner, TenantRole.admin, TenantRole.member, TenantRole.viewer)


def ensure_scope(auth: AuthContext, scope: str) -> None:
    """Raise 403 if an API key lacks the required scope (JWTs always pass)."""
    if not auth.has_scope(scope):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"API key missing required scope: {scope}",
        )
