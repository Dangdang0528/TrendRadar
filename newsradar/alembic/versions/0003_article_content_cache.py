"""正文缓存表:链接 → 抓取正文(供正文级 AI 深度总结)

Revision ID: 0003_article_content_cache
Revises: 0002_subscriptions_channels
Create Date: 2026-09-21 12:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_article_content_cache"
down_revision: str | None = "0002_subscriptions_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_contents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("elapsed_ms", sa.BigInteger(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_article_contents_url"),
    )
    op.create_index("ix_article_contents_url", "article_contents", ["url"])
    op.create_index("ix_article_contents_fetched_at", "article_contents", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_article_contents_fetched_at", table_name="article_contents")
    op.drop_index("ix_article_contents_url", table_name="article_contents")
    op.drop_table("article_contents")