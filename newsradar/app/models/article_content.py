"""正文缓存 ORM 模型

存储"链接 → 正文"的抓取结果,供正文级 AI 深度总结使用。
查询时优先命中缓存,避免对同一热搜链接重复抓取;并按 TTL 定期清理过期记录。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ArticleContent(Base):
    """正文缓存:一条记录 = 一个 url 的抓取正文"""

    __tablename__ = "article_contents"
    # 命中缓存:同 url 快速查;过期清理:按 created_at 批量删
    __table_args__ = (
        Index("ix_article_contents_fetched_at", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True,
    )
    # url 唯一索引,用于 upsert 命中缓存
    url: Mapped[str] = mapped_column(Text, unique=True, index=True)
    # 抓取到的正文(纯文本)
    content: Mapped[str | None] = mapped_column(Text)
    # 正文来源站点域名(便于统计)
    domain: Mapped[str | None] = mapped_column(String(255))
    # 抓取是否成功;失败时 content 可为空,避免反复失败重抓
    success: Mapped[bool] = mapped_column(default=False, nullable=False)
    # 抓取用时(ms),供调优
    elapsed_ms: Mapped[int | None] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )