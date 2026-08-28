"""
Authentication endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import UserCreate, UserLogin, Token, UserResponse
from app.services.auth import get_user_by_email, create_user, authenticate_user, login_user

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user.
    """
    existing = await get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = await create_user(db, user_in)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    user_in: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Login and receive JWT access token.
    """
    user = await authenticate_user(db, user_in.email, user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    access_token = await login_user(db, user, ip=ip, user_agent=user_agent)
    await db.commit()

    return Token(access_token=access_token)
