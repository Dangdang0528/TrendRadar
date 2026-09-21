# coding=utf-8
"""认证路由"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.db import db_session
from app.deps import CurrentUser
from app.schemas.auth import (
    TokenResponse,
    UserLogin,
    UserPublic,
    UserRegister,
    VerifyEmail,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister):
    """注册新用户

    MVP 阶段:不强制邮箱验证,注册即可登录(验证邮件后续阶段补)。
    """
    async with db_session() as db:
        try:
            user, _token = await auth_service.register_user(
                db,
                email=payload.email,
                password=payload.password,
                nickname=payload.nickname,
                timezone=payload.timezone,
                language=payload.language,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        return {"user_id": user.id, "email": user.email, "verify_required": False}


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    """登录,获取 JWT"""
    async with db_session() as db:
        user = await auth_service.authenticate(db, payload.email, payload.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="邮箱或密码错误",
            )
        token, expires_in = auth_service.create_access_token(user.id)
        return TokenResponse(
            access_token=token,
            user_id=user.id,
            expires_in=expires_in,
        )


@router.post("/verify-email", response_model=UserPublic)
async def verify_email(payload: VerifyEmail):
    """通过 token 验证邮箱"""
    async with db_session() as db:
        try:
            user = await auth_service.verify_email_by_token(db, payload.token)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )
        return UserPublic.model_validate(user)


@router.get("/me", response_model=UserPublic)
async def me(current: CurrentUser):
    """获取当前用户信息"""
    return UserPublic.model_validate(current)
