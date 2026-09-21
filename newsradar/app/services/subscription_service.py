# coding=utf-8
"""订阅业务服务"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription


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
        sub.config = config
    if enabled is not None:
        sub.enabled = enabled
    await db.flush()
    await db.refresh(sub)
    return sub


async def delete_subscription(db: AsyncSession, user_id: int, sub_id: int) -> bool:
    stmt = (
        delete(Subscription)
        .where(Subscription.id == sub_id, Subscription.user_id == user_id)
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


def list_trendradar_platforms() -> list[dict[str, Any]]:
    """从 trendradar config.yaml 读取内置平台清单

    trendradar 的 config/config.yaml platforms.sources 里维护了全部平台;
    我们只返回 id + name + enabled,供前端勾选
    """
    import yaml
    from pathlib import Path
    from app.config import get_settings

    settings = get_settings()
    config_path = Path(settings.TRENDRADAR_WORK_DIR) / "config" / "config.yaml"
    if not config_path.exists():
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []
    sources = data.get("platforms", {}).get("sources", []) or []
    out = []
    for s in sources:
        if not s.get("id"):
            continue
        out.append({
            "id": s["id"],
            "name": s.get("name", s["id"]),
            "enabled": s.get("enabled", True),
        })
    return out
