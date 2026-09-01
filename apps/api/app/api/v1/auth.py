"""Owner-only authentication. One user. Login wall for the dashboard."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import BootstrapOut, Token, UserCreate, UserLogin, UserResponse
from app.services.auth import (
    authenticate_user,
    count_users,
    create_user,
    get_user_by_email,
    login_user,
)

router = APIRouter()

_FAILS: dict[str, list[datetime]] = defaultdict(list)
_LOCK = Lock()
_WINDOW = timedelta(minutes=15)
_MAX_FAILS = 8


def _client_ip(request: Request) -> str:
    # X-Real-IP is set (overwritten, not appended) by our nginx config from
    # $remote_addr, so a client can't spoof it to dodge the login lockout.
    # X-Forwarded-For is client-controllable unless every hop in front of us
    # is trusted to overwrite it too, so it's only a fallback for deployments
    # without our nginx in front (e.g. local dev).
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _prune(ip: str, now: datetime) -> list[datetime]:
    with _LOCK:
        hits = [t for t in _FAILS[ip] if now - t < _WINDOW]
        _FAILS[ip] = hits
        return hits


def _locked(ip: str) -> tuple[bool, int]:
    now = datetime.now(timezone.utc)
    hits = _prune(ip, now)
    remain = max(0, _MAX_FAILS - len(hits))
    return len(hits) >= _MAX_FAILS, remain


def _record_fail(ip: str) -> None:
    now = datetime.now(timezone.utc)
    with _LOCK:
        _FAILS[ip].append(now)


@router.get("/bootstrap", response_model=BootstrapOut)
async def bootstrap(db: AsyncSession = Depends(get_db)):
    n = await count_users(db)
    return BootstrapOut(owner_exists=n > 0, owner_count=n)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    locked, remain = _locked(ip)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="تلاش زیاد. ۱۵ دقیقه صبر کن.",
        )
    existing_count = await count_users(db)
    if existing_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="فقط یک مالک مجاز است. ثبت‌نام بسته است.",
        )
    existing = await get_user_by_email(db, user_in.email)
    if existing:
        _record_fail(ip)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="این ایمیل قبلا ثبت شده")
    user = await create_user(db, user_in)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    locked, remain = _locked(ip)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="تلاش زیاد. ۱۵ دقیقه صبر کن.",
        )
    user = await authenticate_user(db, user_in.email, user_in.password)
    if not user:
        _record_fail(ip)
        _, remain = _locked(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"ایمیل یا رمز اشتباه است. باقی‌مانده: {remain}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    previous = user.last_login_at
    user_agent = request.headers.get("user-agent")
    access_token = await login_user(db, user, ip=ip, user_agent=user_agent)
    await db.commit()
    return Token(
        access_token=access_token,
        email=user.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        full_name=user.full_name,
        last_login_at=previous,
        session_ip=ip,
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(require_admin)):
    return user
