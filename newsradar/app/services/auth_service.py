# coding=utf-8
"""认证与用户业务服务"""

from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> tuple[str, int]:
    """生成 JWT,返回 (token, expires_in_seconds)"""
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": str(user_id), "exp": expire}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token, int(expires_delta.total_seconds())


async def create_email_verify_token(user_id: int) -> str:
    """生成邮箱验证 token(短有效期 24h)"""
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {"sub": str(user_id), "exp": expire, "purpose": "email_verify"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def register_user(
    db: AsyncSession, email: str, password: str,
    nickname: str | None, timezone: str, language: str,
) -> tuple[User, str]:
    """注册用户,返回 (user, verify_token)"""
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        nickname=nickname or email.split("@")[0],
        timezone=timezone,
        language=language,
        email_verified=False,
        is_active=True,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("该邮箱已注册")
    token = await create_email_verify_token(user.id)
    return user, token


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    stmt = select(User).where(User.email == email.lower().strip())
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        raise ValueError("账号已禁用")
    return user


async def verify_email_by_token(db: AsyncSession, token: str) -> User:
    """用 token 验证邮箱"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != "email_verify":
            raise ValueError("token 类型错误")
        user_id = int(payload["sub"])
    except Exception as e:
        raise ValueError(f"token 无效: {e}")
    user = await db.get(User, user_id)
    if not user:
        raise ValueError("用户不存在")
    user.email_verified = True
    await db.flush()
    return user
