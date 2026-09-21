# coding=utf-8
"""调度业务服务"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_schedule import UserSchedule


async def get_or_create_schedule(db: AsyncSession, user_id: int) -> UserSchedule:
    """取或创建用户调度行(默认值)"""
    schedule = await db.get(UserSchedule, user_id)
    if not schedule:
        schedule = UserSchedule(user_id=user_id)
        db.add(schedule)
        await db.flush()
    return schedule


async def update_schedule(
    db: AsyncSession, user_id: int, **fields: Any,
) -> UserSchedule:
    """更新调度字段"""
    schedule = await get_or_create_schedule(db, user_id)
    for k, v in fields.items():
        if hasattr(schedule, k) and v is not None:
            setattr(schedule, k, v)
    await db.flush()
    # 刷新以拿到 server_default 生成的字段(created_at/updated_at)
    await db.refresh(schedule)
    return schedule


async def get_schedule_dict(db: AsyncSession, user_id: int) -> dict:
    schedule = await get_or_create_schedule(db, user_id)
    return schedule.to_dict()


async def get_ai_usage_summary(db: AsyncSession, user_id: int) -> dict:
    """计算今日/本月 AI 用量摘要"""
    from app.models.ai_usage import AIUsage
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    stmt = (
        select(
            func.count().label("cnt"),
            func.coalesce(func.sum(AIUsage.cost_cents), 0).label("cost"),
        )
        .where(AIUsage.user_id == user_id, AIUsage.created_at >= today_start)
    )
    today = (await db.execute(stmt)).one()

    stmt = (
        select(
            func.count().label("cnt"),
            func.coalesce(func.sum(AIUsage.cost_cents), 0).label("cost"),
        )
        .where(AIUsage.user_id == user_id, AIUsage.created_at >= month_start)
    )
    month = (await db.execute(stmt)).one()

    return {
        "today_count": int(today.cnt or 0),
        "today_cost_cents": float(today.cost or 0),
        "month_count": int(month.cnt or 0),
        "month_cost_cents": float(month.cost or 0),
    }
