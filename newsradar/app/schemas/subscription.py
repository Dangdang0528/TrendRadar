# coding=utf-8
"""Pydantic schemas:订阅"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SubscriptionBase(BaseModel):
    type: str = Field(description="platform / rss / keyword / ai_interest")
    target: str
    name: str | None = Field(default=None, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class SubscriptionOut(SubscriptionBase):
    id: int
    user_id: int
    enabled: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PlatformInfo(BaseModel):
    """trendradar 内置平台清单项"""

    id: str
    name: str
    enabled: bool = True


class PlatformList(BaseModel):
    """平台清单响应"""

    platforms: list[PlatformInfo]
    source: str = "trendradar"
