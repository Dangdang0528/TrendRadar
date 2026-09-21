# coding=utf-8
"""用户调度 ORM 模型

每用户一行,记录推送调度与 AI 总结开关。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserSchedule(Base):
    """per-user 调度"""

    __tablename__ = "user_schedules"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False, default="0 9 * * *")
    report_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="incremental")
    enable_ai_summary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_language: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    ai_max_news: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    channel_filter: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # {"include": ["feishu"], "exclude": ["email"]} 优先级高于 priority 字段
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "cron_expr": self.cron_expr,
            "report_mode": self.report_mode,
            "enable_ai_summary": self.enable_ai_summary,
            "ai_language": self.ai_language,
            "ai_max_news": self.ai_max_news,
            "channel_filter": self.channel_filter,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "enabled": self.enabled,
        }
