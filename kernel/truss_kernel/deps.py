"""FastAPI dependencies: current user, tenant scoping, RBAC."""
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truss_kernel.db import get_db
from truss_kernel.models.tenant import Membership, TenantRole, User
from truss_kernel.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: TenantRole
    email: str


async def get_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    payload = decode_access_token(creds.credentials)
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
