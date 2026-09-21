# coding=utf-8
"""Pydantic schemas:调度"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ScheduleBase(BaseModel):
    cron_expr: str = Field(default="0 9 * * *", max_length=64)
    report_mode: str = Field(default="incremental")  # daily / current / incremental
    enable_ai_summary: bool = False
    ai_language: str = Field(default="zh", max_length=8)
    ai_max_news: int = Field(default=30, ge=1, le=200)
    channel_filter: dict[str, Any] | None = None
    enabled: bool = True

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
