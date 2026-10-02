# coding=utf-8
"""Pydantic schemas:调度"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# 支持的投递渠道(与 app.adapters.delivery.CHANNEL_NAMES 保持一致)
CHANNEL_TYPES = ("feishu", "email", "telegram", "webhook")


class ScheduleBase(BaseModel):
    cron_expr: str = Field(default="0 9 * * *", max_length=64)
    report_mode: str = Field(default="incremental")  # daily / current / incremental
    enable_ai_summary: bool = False
    ai_language: str = Field(default="zh", max_length=8)
    ai_max_news: int = Field(default=30, ge=1, le=200)
    # {"include": ["feishu"], "exclude": ["email"]};{} 表示不过滤
    channel_filter: dict[str, Any] | None = None
    enabled: bool = True

    @field_validator("channel_filter")
    @classmethod
    def validate_channel_filter(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError('channel_filter 必须是对象,例如 {"include": ["feishu"]}')

        unknown = set(v) - {"include", "exclude"}
        if unknown:
            raise ValueError(f"channel_filter 仅支持 include / exclude,收到:{sorted(unknown)}")

        normalized: dict[str, list[str]] = {}
        for key in ("include", "exclude"):
            raw = v.get(key)
            if raw is None:
                continue
            if not isinstance(raw, list):
                raise ValueError(f"channel_filter.{key} 必须是数组")
            names = [str(x).strip().lower() for x in raw]
            bad = [n for n in names if n not in CHANNEL_TYPES]
            if bad:
                raise ValueError(f"未知渠道:{bad},可选 {list(CHANNEL_TYPES)}")
            normalized[key] = names
        return normalized

    @field_validator("report_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("daily", "current", "incremental"):
            raise ValueError("report_mode 必须是 daily / current / incremental")
        return v

    @field_validator("cron_expr")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        # 简单校验:5 段 cron 表达式
        parts = v.split()
        if len(parts) != 5:
            raise ValueError("cron_expr 必须是 5 段 unix cron(分 时 日 月 周)")
        return v


class ScheduleUpdate(ScheduleBase):
    """更新调度:全字段 PUT"""


class ScheduleOut(ScheduleBase):
    user_id: int
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AIUsageSummary(BaseModel):
    """AI 用量摘要"""

    today_count: int
    today_cost_cents: float = 0.0
    month_count: int
    month_cost_cents: float = 0.0
