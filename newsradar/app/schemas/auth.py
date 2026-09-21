# coding=utf-8
"""Pydantic schemas:用户与认证"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """注册请求"""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    language: str = Field(default="zh", max_length=8)


class UserLogin(BaseModel):
    """登录请求"""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT 响应"""

    access_token: str
    token_type: str = "bearer"
    user_id: int
    expires_in: int  # 秒


class UserPublic(BaseModel):
    """用户对外信息(脱敏)"""

    id: int
    email: str
    nickname: str | None = None
    timezone: str
    language: str
    email_verified: bool
    is_active: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class VerifyEmail(BaseModel):
    """邮箱验证请求"""

    token: str
