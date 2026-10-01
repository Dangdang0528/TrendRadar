"""Pipeline Runner — 阶段 2 流水线编排

职责:把"用户上下文 → 抓取筛选 → 正文级 AI 深度总结 → 投递"串成一条流水线。

当前实现进度:
- ✅ 加载用户上下文(_load_user_ctx)
- ✅ 正文级 AI 深度总结(run_ai_deep_summary_for_user,接入 ContentExtractor)
- ⬜ 抓取+筛选(crawl_and_filter_for_user,待实现)
- ⬜ 报告渲染与多渠道投递(待实现)
"""

import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.config_provider import (
    UserChannelSpec,
    UserCtx,
    UserScheduleSpec,
    UserSubscriptionSpec,
    build_config_for_user,
)
from app.adapters.content_extractor import ContentExtractor
from app.adapters.deep_summary import DeepSummaryResult, run_content_deep_summary
from app.config import get_settings
from app.db import AsyncSessionLocal, db_session

# ══════════════════════════════════════════════════════════════
# 阶段 0 验证用(保留)
# ══════════════════════════════════════════════════════════════


def run_pipeline_once_for_test() -> dict[str, Any]:
    """阶段 0 验证用:硬编码一个 UserCtx,调用 trendradar 跑一次

    用法:
      docker compose run --rm api python -c \\
        "from app.adapters.pipeline_runner import run_pipeline_once_for_test; \\
         run_pipeline_once_for_test()"

    Returns:
        运行结果摘要
    """

    # 构造测试用户(暂不查 DB)
    user = UserCtx(
        user_id=0,
        email="test@local",
        timezone="Asia/Shanghai",
        language="zh",
        subscriptions=[],  # 空 → trendradar 不抓平台
        channels=[],
        schedule=type("S", (), {
            "cron_expr": "0 9 * * *",
            "report_mode": "incremental",
            "enable_ai_summary": False,
            "ai_language": "zh",
            "ai_max_news": 30,
        })(),
    )

    # 切换工作目录到 trendradar 期望的位置(config/、output/ 在这里)
    settings = get_settings()
    os.chdir(settings.TRENDRADAR_WORK_DIR)

    # 构造 trendradar config
    config = build_config_for_user(user)

    try:
        # 仅验证 import 与 config 组装能跑通,不真正调抓取(防止外部网络问题)
        from trendradar.context import AppContext

        ctx = AppContext(config)
        return {
            "ok": True,
            "config_keys": sorted(config.keys()),
            "ctx_class": ctx.__class__.__name__,
            "user_email": user.email,
        }
    except Exception as e:  # noqa: BLE001 - 验证辅助函数,任何异常都转摘要返回
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ══════════════════════════════════════════════════════════════
# 阶段 2:加载用户上下文
# ══════════════════════════════════════════════════════════════


async def _load_user_ctx(user_id: int, db: AsyncSession) -> UserCtx | None:
    """从 DB 加载用户的订阅/渠道/调度,组装为 UserCtx(渠道凭证解密)"""
    from app.models.delivery_channel import DeliveryChannel
    from app.models.subscription import Subscription
    from app.models.user import User
    from app.models.user_schedule import UserSchedule
    from app.services.crypto import decrypt_credential

    user = await db.get(User, user_id)
    if not user:
        return None

    subs = (
        await db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id, Subscription.enabled.is_(True)
            )
        )
    ).scalars().all()
    subs_spec = [
        UserSubscriptionSpec(type=s.type, target=s.target, name=s.name, config=s.config or {})
        for s in subs
    ]

    chans = (
        await db.execute(
            select(DeliveryChannel).where(
                DeliveryChannel.user_id == user_id, DeliveryChannel.enabled.is_(True)
            )
        )
    ).scalars().all()
    chan_spec = [
        UserChannelSpec(
            channel=c.channel,
            label=c.label,
            credential=decrypt_credential(c.credential_encrypted),
        )
        for c in chans
    ]

    sched_row = await db.get(UserSchedule, user_id)
    if sched_row:
        schedule = UserScheduleSpec(
            cron_expr=sched_row.cron_expr,
            report_mode=sched_row.report_mode,
            enable_ai_summary=sched_row.enable_ai_summary,
            ai_language=sched_row.ai_language,
            ai_max_news=sched_row.ai_max_news,
        )
    else:
        schedule = UserScheduleSpec()

    return UserCtx(
        user_id=user.id,
        email=getattr(user, "email", "") or "",
        timezone=getattr(user, "timezone", "Asia/Shanghai") or "Asia/Shanghai",
        language=getattr(user, "language", "zh") or "zh",
        subscriptions=subs_spec,
        channels=chan_spec,
        schedule=schedule,
    )


# ══════════════════════════════════════════════════════════════
# 阶段 2:正文级 AI 深度总结(ContentExtractor 接入点)
# ══════════════════════════════════════════════════════════════


async def _record_ai_usage(
    db: AsyncSession,
    *,
    user_id: int,
    model: str,
    purpose: str,
    success: bool,
    error: str = "",
) -> None:
    """写入一条 AI 用量记录(阶段 3 起用于计费)"""
    from app.models.ai_usage import AIUsage

    db.add(
        AIUsage(
            user_id=user_id,
            model=model,
            prompt_tokens=None,
            completion_tokens=None,
            cost_cents=0,
            purpose=purpose,
            success=success,
            error=error or None,
        )
    )
    await db.flush()


async def run_ai_deep_summary_for_user(
    user: UserCtx,
    stats: list[dict],
    rss_stats: list[dict] | None = None,
    *,
    db: AsyncSession | None = None,
) -> DeepSummaryResult | None:
    """正文级 AI 深度总结:抓取 Top-N 正文 → 交给 AI 深度解读 → 记录用量。

    仅当用户开启 AI 总结且配置了全局 AI Key 时执行;否则返回 None(跳过该阶段)。

    Args:
        user: 用户上下文(含 AI 开关与 Top-N 上限)
        stats: 热榜统计(来自 trendradar,含 url)
        rss_stats: RSS 统计(可选)
        db: 可选会话;缺省自建会话
    """
    settings = get_settings()
    if not (user.schedule.enable_ai_summary and settings.AI_API_KEY):
        return None

    async def _run(session: AsyncSession) -> DeepSummaryResult:
        extractor = ContentExtractor(AsyncSessionLocal)
        ai_config = {
            "MODEL": settings.AI_MODEL,
            "API_KEY": settings.AI_API_KEY or "",
            "API_BASE": settings.AI_API_BASE,
            "TIMEOUT": settings.AI_TIMEOUT,
            "MAX_TOKENS": settings.AI_MAX_TOKENS,
        }
        result = await run_content_deep_summary(
            stats=stats,
            rss_stats=rss_stats,
            extractor=extractor,
            max_news=user.schedule.ai_max_news,
            language=user.schedule.ai_language,
            get_time_func=lambda: datetime.now(
                ZoneInfo(user.timezone or "Asia/Shanghai")
            ).strftime("%Y-%m-%d %H:%M:%S"),
            ai_config=ai_config,
        )
        await _record_ai_usage(
            session,
            user_id=user.user_id,
            model=settings.AI_MODEL,
            purpose="deep_summary",
            success=result.success,
            error=result.error,
        )
        return result

    if db is not None:
        return await _run(db)
    async with db_session() as session:
        return await _run(session)


# ══════════════════════════════════════════════════════════════
# 阶段 2:抓取+筛选(待实现)
# ══════════════════════════════════════════════════════════════


async def crawl_and_filter_for_user(
    user: UserCtx,
) -> tuple[list[dict], list[dict]]:
    """调用 trendradar 抓取平台/RSS 并做关键词筛选,产出 stats / rss_stats。

    TODO(阶段 2):复用 trendradar.context.AppContext 的抓取 + count_frequency,
    返回 (stats, rss_stats)。当前尚未实现。
    """
    raise NotImplementedError("crawl_and_filter_for_user 待实现(阶段 2 抓取阶段)")


# ══════════════════════════════════════════════════════════════
# 阶段 2:流水线编排
# ══════════════════════════════════════════════════════════════


async def run_pipeline_for_user(
    user_id: int,
    *,
    stats: list[dict] | None = None,
    rss_stats: list[dict] | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """按 user_id 执行流水线:加载上下文 → 抓取筛选 → AI 深度总结。

    抓取/渲染/投递阶段仍在建设中;可通过 stats 注入已抓取数据以单独验证
    AI 深度总结阶段(测试用)。

    Returns:
        各阶段执行摘要
    """
    if db is not None:
        return await _run_pipeline(user_id, stats, rss_stats, db)
    async with db_session() as session:
        return await _run_pipeline(user_id, stats, rss_stats, session)


async def _run_pipeline(
    user_id: int,
    stats: list[dict] | None,
    rss_stats: list[dict] | None,
    db: AsyncSession,
) -> dict[str, Any]:
    result: dict[str, Any] = {"user_id": user_id, "ok": False, "steps": {}}

    # 1. 加载用户上下文
    user = await _load_user_ctx(user_id, db)
    if not user:
        result["error"] = "用户不存在"
        return result
    result["steps"]["load_ctx"] = {
        "subscriptions": len(user.subscriptions),
        "channels": len(user.channels),
        "ai_summary": user.schedule.enable_ai_summary,
    }

    # 2. 抓取+筛选(如未注入 stats,则调用抓取阶段)
    if stats is None:
        stats, rss_stats = await crawl_and_filter_for_user(user)
    result["steps"]["crawl"] = {"hotlist": len(stats or []), "rss": len(rss_stats or [])}

    # 3. 正文级 AI 深度总结
    ai_result = await run_ai_deep_summary_for_user(user, stats or [], rss_stats, db=db)
    if ai_result is None:
        result["steps"]["ai_deep_summary"] = {"enabled": False}
    else:
        result["steps"]["ai_deep_summary"] = {
            "enabled": True,
            "success": ai_result.success,
            "skipped": ai_result.skipped,
            "analyzed": ai_result.analyzed,
            "total_candidates": ai_result.total_candidates,
            "error": ai_result.error,
        }
        result["ai_deep_summary"] = ai_result

    result["ok"] = True
    return result