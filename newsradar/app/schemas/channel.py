# coding=utf-8
"""Pydantic schemas:投递渠道"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ChannelBase(BaseModel):
    channel: str = Field(description="feishu / email / telegram / webhook")
    label: str | None = Field(default=None, max_length=64)
    priority: int = Field(default=0, ge=0, le=999)


class ChannelCreate(ChannelBase):
    """渠道创建:credential 字段为明文,入库前由 service 加密"""

    credential: dict[str, Any]

    @model_validator(mode="after")
    def validate_credential(self) -> "ChannelCreate":
        ch = self.channel
        cred = self.credential or {}
        if ch == "feishu":
            if "webhook_url" not in cred:
                raise ValueError("feishu 渠道需要 credential.webhook_url")
        elif ch == "email":
            if "to_email" not in cred:
                raise ValueError("email 渠道需要 credential.to_email")
            # smtp_user / smtp_pass 可选(为空时使用全局 SMTP 配置)
        elif ch == "telegram":
            if not all(k in cred for k in ("bot_token", "chat_id")):
                raise ValueError("telegram 渠道需要 credential.bot_token 与 chat_id")
        elif ch == "webhook":
            if "url" not in cred:
                raise ValueError("webhook 渠道需要 credential.url")
        else:
            raise ValueError(f"不支持的渠道类型: {ch}")
        return self


class ChannelUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    credential: dict[str, Any] | None = None
    priority: int | None = Field(default=None, ge=0, le=999)
    enabled: bool | None = None


class ChannelOut(BaseModel):
    """对外脱敏:不含 credential"""

    id: int
    user_id: int
    channel: str
    label: str | None = None
    priority: int
    enabled: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChannelTestResult(BaseModel):
    """渠道测试结果"""

    success: bool
    message: str
    channel: str
    sent_at: datetime
