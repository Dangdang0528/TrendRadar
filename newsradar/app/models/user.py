# coding=utf-8
"""用户 ORM 模型"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    """用户表"""

    __tablename__ = "users"

    # BigInteger().with_variant(Integer, "sqlite"):
    # PostgreSQL 上是 BIGINT,SQLite 上是 INTEGER PRIMARY KEY(可自增)
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True,
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="zh")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"

    def to_public_dict(self) -> dict:
        """对外暴露的脱敏字段"""
        return {
            "id": self.id,
            "email": self.email,
            "nickname": self.nickname,
            "timezone": self.timezone,
            "language": self.language,
            "email_verified": self.email_verified,
            "is_active": self.is_active,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat()
            if self.created_at
            else None,
        }
