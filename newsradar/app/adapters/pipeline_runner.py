"""Pipeline Runner — 阶段 2 流水线编排

职责:把"用户上下文 → 抓取筛选 → 正文级 AI 深度总结 → 投递"串成一条流水线。

当前实现进度:
- ✅ 加载用户上下文(_load_user_ctx)
- ✅ 抓取+筛选(crawl_and_filter_for_user,复用 trendradar)
- ✅ 正文级 AI 深度总结(run_ai_deep_summary_for_user,接入 ContentExtractor)
- ✅ 报告渲染与多渠道投递(deliver_report_for_user,复用 trendradar 通知层)
"""

import asyncio
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
from app.adapters.delivery import deliver_report_for_user
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
            channel_filter=sched_row.channel_filter,
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
# 阶段 2:抓取 + 关键词筛选
# ══════════════════════════════════════════════════════════════


def _merge_crawl_config(base: dict, user: UserCtx) -> dict:
    """把 per-user 偏好叠加到 trendradar 的完整默认配置上(抓取阶段用)

    base 来自 trendradar.load_config():提供 REQUEST_INTERVAL / USE_PROXY /
    WEIGHT_CONFIG / RANK_THRESHOLD 等抓取与统计所需的默认键;
    per-user 覆盖平台、RSS、AI、报告模式、时区等。
    """
    per = build_config_for_user(user)

    cfg = dict(base)
    for key in ("PLATFORMS", "REPORT_MODE", "TIMEZONE", "LANGUAGE", "DEBUG"):
        cfg[key] = per[key]

    # 存储:用绝对路径 + 仅 SQLite(OR 引擎侧不需要 txt/html 快照)
    cfg["STORAGE"] = per["STORAGE"]

    # RSS:保留 base 的抓取参数(超时/间隔/新鲜度),仅覆盖开关与源列表
    cfg["RSS"] = {
        **base.get("RSS", {}),
        "ENABLED": per["RSS"]["ENABLED"],
        "FEEDS": per["RSS"]["FEEDS"],
    }

    # 筛选策略:统一走关键词(MVP 不启用 AI 筛选)
    cfg["FILTER"] = {"METHOD": "keyword", "PRIORITY_SORT_ENABLED": False}

    # AI:模型配置用全局 key;关闭 trendradar 内置 AI 分析(深度总结由我们自己做)
    cfg["AI"] = per["AI"]
    cfg["AI_ANALYSIS"] = {**base.get("AI_ANALYSIS", {}), "ENABLED": False}

    return cfg


def _write_user_frequency_file(user: UserCtx) -> str:
    """把用户的 keyword 订阅写成一个 trendradar 频率词文件

    每个关键词独占一个词组(空行分隔);无关键词时写入空文件 → 统计层
    会退化为"全部新闻",避免无谓过滤。
    """
    work_dir = get_settings().TRENDRADAR_WORK_DIR
    out_dir = os.path.join(work_dir, "output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f".user_freq_{user.user_id}.txt")

    keywords = [s.target.strip() for s in user.subscriptions if s.type == "keyword" and s.target.strip()]
    content = "\n\n".join(keywords) + ("\n" if keywords else "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _crawl_sync(user: UserCtx) -> tuple[list[dict], list[dict]]:
    """同步抓取 + 筛选(供 asyncio.to_thread 调用)

    复用 trendradar 的 NewsAnalyzer 抓取/存储/统计方法,但不触发通知。
    """
    from trendradar.__main__ import NewsAnalyzer
    from trendradar.core import load_config

    settings = get_settings()
    config_path = os.path.join(settings.TRENDRADAR_WORK_DIR, "config", "config.yaml")
    base_cfg = load_config(config_path)
    cfg = _merge_crawl_config(base_cfg, user)

    analyzer = NewsAnalyzer(cfg)
    freq_file = _write_user_frequency_file(user)
    analyzer.frequency_file = freq_file

    try:
        # 1. 抓取热榜(写入 storage,供跨批次累积)
        analyzer._crawl_data()
        # 2. 抓取 RSS(未配置时内部直接返回空)
        rss_stats, _rss_new, _raw, _urls = analyzer._crawl_rss_data()
        # 3. 读取当天累积数据 → 关键词筛选 → stats
        stats: list[dict] = []
        analysis = analyzer._load_analysis_data(quiet=True)
        if analysis:
            (
                all_results,
                id_to_name,
                title_info,
                new_titles,
                word_groups,
                filter_words,
                global_filters,
            ) = analysis
            stats, _total = analyzer.ctx.count_frequency(
                all_results,
                word_groups,
                filter_words,
                id_to_name,
                title_info,
                new_titles,
                mode=user.schedule.report_mode,
                global_filters=global_filters,
                quiet=True,
            )
        return stats, (rss_stats or [])
    finally:
        if os.path.exists(freq_file):
            os.remove(freq_file)
        analyzer.ctx.cleanup()


async def crawl_and_filter_for_user(user: UserCtx) -> tuple[list[dict], list[dict]]:
    """抓取平台热榜 + RSS,并按用户关键词筛选,产出 (stats, rss_stats)。

    复用 trendradar 的抓取/存储/统计能力(零上游改动)。抓取为阻塞 I/O,
    放到线程池执行;过程中临时切换工作目录以兼容 trendradar 的相对路径约定。
    """
    settings = get_settings()
    work_dir = settings.TRENDRADAR_WORK_DIR
    prev_cwd = os.getcwd()
    os.chdir(work_dir)
    try:
        return await asyncio.to_thread(_crawl_sync, user)
    finally:
        os.chdir(prev_cwd)


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
    """按 user_id 执行流水线:加载上下文 → 抓取筛选 → AI 深度总结 → 报告投递。

    抓取/渲染/投递可通过 stats 注入已抓取数据以单独验证后续阶段(测试用)。

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

    # 4. 报告渲染 + 多渠道投递
    delivery = await deliver_report_for_user(user, stats or [], rss_stats, db=db)
    result["steps"]["delivery"] = {
        "enabled": delivery["enabled"],
        "skipped": delivery["skipped"],
        "reason": delivery["reason"],
        "report_type": delivery["report_type"],
        "results": delivery["results"],
    }

    result["ok"] = True
    return result