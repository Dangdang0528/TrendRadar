# coding=utf-8
"""订阅业务服务"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.config_provider import GLOBAL_FILTER_TARGET, load_platform_catalog
from app.models.subscription import Subscription
from app.schemas.subscription import (
    InvalidSubscriptionConfig,
    derive_keyword_target,
    parse_keyword_config,
)

# 全局过滤词的单例行类型
GLOBAL_FILTER_TYPE = "global_filter"


async def list_subscriptions(db: AsyncSession, user_id: int) -> list[Subscription]:
    stmt = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_subscription(
    db: AsyncSession, user_id: int,
    type: str, target: str, name: str | None, config: dict[str, Any],
) -> Subscription:
    if type == "keyword":
        config = parse_keyword_config(config)
        target = derive_keyword_target(config)

    sub = Subscription(
        user_id=user_id, type=type, target=target, name=name, config=config,
        enabled=True,
    )
    db.add(sub)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"已存在订阅: type={type}, target={target}")
    await db.refresh(sub)
    return sub


async def update_subscription(
    db: AsyncSession, user_id: int, sub_id: int,
    name: str | None = None, config: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> Subscription:
    sub = await db.get(Subscription, sub_id)
    if not sub or sub.user_id != user_id:
        raise ValueError("订阅不存在")
    if name is not None:
        sub.name = name
    if config is not None:
        if sub.type == "keyword":
            # 词组结构变化时同步刷新派生 target
            config = parse_keyword_config(config)
            new_target = derive_keyword_target(config)
            if new_target != sub.target:
                clash = await _target_exists(db, user_id, sub.type, new_target, exclude_id=sub.id)
                if clash:
                    raise InvalidSubscriptionConfig(f"已存在同名关键词组:{new_target}")
                sub.target = new_target
        sub.config = config
    if enabled is not None:
        sub.enabled = enabled
    await db.flush()
    await db.refresh(sub)
    return sub


async def _target_exists(
    db: AsyncSession, user_id: int, type: str, target: str, *, exclude_id: int,
) -> bool:
    stmt = select(Subscription.id).where(
        Subscription.user_id == user_id,
        Subscription.type == type,
        Subscription.target == target,
        Subscription.id != exclude_id,
    )
    return (await db.execute(stmt)).first() is not None


async def delete_subscription(db: AsyncSession, user_id: int, sub_id: int) -> bool:
    stmt = (
        delete(Subscription)
        .where(Subscription.id == sub_id, Subscription.user_id == user_id)
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


def list_trendradar_platforms() -> list[dict[str, Any]]:
    """列出 trendradar 内置平台清单,供前端勾选"""
    return load_platform_catalog()


async def replace_platforms(
    db: AsyncSession, user_id: int, platform_ids: list[str],
) -> list[str]:
    """整体替换用户的平台选择(多选语义);空列表 = 不限制 = 抓取全平台"""
    catalog = {p["id"]: p for p in load_platform_catalog()}
    ids = list(dict.fromkeys(pid.strip() for pid in platform_ids if pid.strip()))
    unknown = [pid for pid in ids if catalog and pid not in catalog]
    if unknown:
        raise InvalidSubscriptionConfig(f"未知平台:{unknown}")

    await db.execute(
        delete(Subscription).where(
            Subscription.user_id == user_id, Subscription.type == "platform"
        )
    )
    for pid in ids:
        db.add(
            Subscription(
                user_id=user_id,
                type="platform",
                target=pid,
                name=(catalog.get(pid) or {}).get("name", pid),
                config={},
                enabled=True,
            )
        )
    await db.flush()
    return ids


async def get_global_filters(db: AsyncSession, user_id: int) -> list[str]:
    """读取全局过滤词"""
    row = await _get_global_filter_row(db, user_id)
    if not row:
        return []
    return [str(w) for w in (row.config or {}).get("words") or []]


async def set_global_filters(
    db: AsyncSession, user_id: int, words: list[str],
) -> list[str]:
    """整体替换全局过滤词;空列表时删除该行"""
    row = await _get_global_filter_row(db, user_id)
    if not words:
        if row:
            await db.delete(row)
            await db.flush()
        return []
    if row:
        row.config = {"words": words}
        row.enabled = True
    else:
        db.add(
            Subscription(
                user_id=user_id,
                type=GLOBAL_FILTER_TYPE,
                target=GLOBAL_FILTER_TARGET,
                name="全局过滤",
                config={"words": words},
                enabled=True,
            )
        )
    await db.flush()
    return words


async def _get_global_filter_row(db: AsyncSession, user_id: int) -> Subscription | None:
    stmt = select(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.type == GLOBAL_FILTER_TYPE,
        Subscription.target == GLOBAL_FILTER_TARGET,
    )
    return (await db.execute(stmt)).scalar_one_or_none()
