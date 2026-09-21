# coding=utf-8
"""投递渠道 ORM 模型

channel:
    - feishu    飞书 webhook,credential = {"webhook_url": "..."}
    - email     邮箱,credential = {"to_email": "...", "smtp_user": "...", "smtp_pass": "..."}
    - telegram  Telegram bot,credential = {"bot_token": "...", "chat_id": "..."}
    - webhook   通用 webhook,credential = {"url": "...", "method": "POST"}
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DeliveryChannel(Base):
    """用户投递渠道"""

    __tablename__ = "delivery_channels"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(String(64))
    credential_encrypted: Mapped[dict] = mapped_column(
        "credential", JSON, nullable=False
    )  # 字段名保持 credential 对外,列存的是密文 dict
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def to_public_dict(self) -> dict:
        """对外脱敏:不返回 credential"""
        return {
            "id": self.id,
            "channel": self.channel,
            "label": self.label,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
