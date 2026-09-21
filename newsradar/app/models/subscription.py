# coding=utf-8
"""订阅 ORM 模型

订阅类型 type:
    - platform    平台热榜,target = platform_id(如 zhihu / weibo / bilibili)
    - rss         RSS 源,target = rss url
    - keyword     关键词订阅,target = 关键词文本
    - ai_interest AI 兴趣描述,target = 自然语言描述
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Subscription(Base):
    """用户订阅"""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "target", name="uq_subscriptions_user_type_target"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(String(128))
    config: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "target": self.target,
            "name": self.name,
            "config": self.config or {},
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
