"""
Authentication service.
"""

from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.user import User, UserRole
from app.models.system import AuditLog, AuditAction
from app.schemas.auth import UserCreate


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def count_users(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar_one() or 0)


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    existing = await count_users(db)
    role = UserRole.ADMIN if existing == 0 else UserRole.OBSERVER
    user = User(
        email=user_in.email.lower().strip(),
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email.lower().strip())
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def login_user(db: AsyncSession, user: User, ip: str | None = None, user_agent: str | None = None) -> str:
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    audit = AuditLog(
        user_id=user.id,
        action=AuditAction.LOGIN,
        source="dashboard",
        ip_address=ip,
        user_agent=user_agent,
        details=f"User {user.email} logged in",
    )
    db.add(audit)

    token = create_access_token(subject=user.id)
    return token
