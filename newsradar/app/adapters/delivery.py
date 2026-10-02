"""多渠道投递(阶段 2)

把渲染好的报告真正投递到用户的各渠道,并写入 notification_logs。
投递范围由 schedule.channel_filter(include 白名单 / exclude 黑名单)决定。

复用 trendradar 的 NotificationDispatcher + senders(零上游改动):
将 per-user 渠道凭证翻译成 trendradar 的通知配置,交由 dispatcher 分发,
因此飞书 / 邮件 / Telegram / 通用 Webhook 的鉴权、分批、重试逻辑全部沿用上游实现。
"""

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.config_provider import UserCtx
from app.adapters.report_renderer import (
    build_report_data,
    render_html_report,
    report_type_for_mode,
)
from app.config import get_settings

# 支持的投递渠道
CHANNEL_NAMES = ("feishu", "email", "telegram", "webhook")

# dispatcher.dispatch_all 返回的 key → 我方渠道名
_DISPATCH_KEY_TO_CHANNEL = {
    "feishu": "feishu",
    "email": "email",
    "telegram": "telegram",
    "generic_webhook": "webhook",
}


def _as_channel_set(value: Any) -> set[str]:
    """把 channel_filter 的 include/exclude 值规范成小写渠道名集合"""
    if not isinstance(value, (list, tuple)):
        return set()
    return {str(x).strip().lower() for x in value if str(x).strip()}


def selected_channels(
    channel_filter: dict[str, Any] | None,
    available: list[str],
) -> list[str]:
    """按 schedule.channel_filter 从已配置渠道中挑出本次要投递的渠道。

    规则:
    - channel_filter 为 None/{} 或两个键都为空 → 不过滤,返回全部
    - include 非空 → 白名单,只保留其中的渠道
    - exclude → 黑名单,优先级高于 include
    - 过滤结果可能为空(表示"没有渠道该收到"),由调用方决定如何处理
    """
    if not isinstance(channel_filter, dict):
        return list(available)

    include = _as_channel_set(channel_filter.get("include"))
    exclude = _as_channel_set(channel_filter.get("exclude"))
    if not include and not exclude:
        return list(available)

    return [
        c for c in available
        if (not include or c in include) and c not in exclude
    ]


def _email_fragment(cred: dict[str, Any]) -> dict[str, Any]:
    """邮箱渠道凭证 → trendradar 邮件配置(渠道自带 SMTP 优先,否则用全局 SMTP)"""
    settings = get_settings()
    from_email = cred.get("smtp_user") or settings.SMTP_USER
    password = cred.get("smtp_pass") or settings.SMTP_PASSWORD
    if not from_email or not password:
        return {}

    frag: dict[str, Any] = {
        "EMAIL_FROM": from_email,
        "EMAIL_PASSWORD": password,
        "EMAIL_TO": cred["to_email"],
    }
    if cred.get("smtp_host"):
        frag["EMAIL_SMTP_SERVER"] = cred["smtp_host"]
    if cred.get("smtp_port"):
        frag["EMAIL_SMTP_PORT"] = int(cred["smtp_port"])
    return frag


def build_notification_config(
    user: UserCtx,
    allowed: list[str] | None = None,
) -> dict[str, Any]:
    """把用户的投递渠道翻译成 trendradar 通知配置;凭证不完整的渠道会被跳过。

    allowed 为 None 时不过滤;否则只翻译其中的渠道(来自 channel_filter)。
    """
    config: dict[str, Any] = {
        "MAX_ACCOUNTS_PER_CHANNEL": 1,
        "BATCH_SEND_INTERVAL": 1.0,
    }

    for ch in user.channels:
        if allowed is not None and ch.channel not in allowed:
            continue
        cred = ch.credential or {}
        if ch.channel == "feishu":
            if cred.get("webhook_url"):
                config["FEISHU_WEBHOOK_URL"] = cred["webhook_url"]
        elif ch.channel == "telegram":
            if cred.get("bot_token") and cred.get("chat_id"):
                config["TELEGRAM_BOT_TOKEN"] = cred["bot_token"]
                config["TELEGRAM_CHAT_ID"] = cred["chat_id"]
        elif ch.channel == "webhook":
            if cred.get("url"):
                config["GENERIC_WEBHOOK_URL"] = cred["url"]
                if cred.get("payload_template"):
                    config["GENERIC_WEBHOOK_TEMPLATE"] = cred["payload_template"]
        elif ch.channel == "email":
            if cred.get("to_email"):
                config.update(_email_fragment(cred))

    return config


async def _upsert_logs(
    db: AsyncSession,
    user_id: int,
    results: dict[str, bool],
    report_date: date,
) -> None:
    """按 (user_id, channel, report_date) 写/更新推送日志"""
    from app.models.notification_log import NotificationLog

    for dispatch_key, ok in results.items():
        channel = _DISPATCH_KEY_TO_CHANNEL.get(dispatch_key, dispatch_key)
        row = (
            await db.execute(
                select(NotificationLog).where(
                    NotificationLog.user_id == user_id,
                    NotificationLog.channel == channel,
                    NotificationLog.report_date == report_date,
                )
            )
        ).scalar_one_or_none()

        status = "success" if ok else "failed"
        if row:
            row.status = status
            row.sent_at = datetime.now(timezone.utc)
        else:
            db.add(
                NotificationLog(
                    user_id=user_id,
                    channel=channel,
                    report_date=report_date,
                    status=status,
                )
            )
    await db.flush()


def _has_content(report_data: dict, rss_stats: list[dict] | None) -> bool:
    return bool(report_data.get("stats")) or bool(rss_stats)


def _dispatch_sync(
    config: dict[str, Any],
    report_data: dict,
    *,
    report_type: str,
    mode: str,
    html_file_path: str | None,
    rss_stats: list[dict] | None,
    get_time_func,
) -> dict[str, bool]:
    """同步投递(供 asyncio.to_thread 调用)"""
    from trendradar.notification.dispatcher import NotificationDispatcher
    from trendradar.notification.splitter import split_content_into_batches

    dispatcher = NotificationDispatcher(
        config=config,
        get_time_func=get_time_func,
        split_content_func=split_content_into_batches,
    )
    return dispatcher.dispatch_all(
        report_data=report_data,
        report_type=report_type,
        mode=mode,
        html_file_path=html_file_path,
        rss_items=rss_stats,
    )


async def deliver_report_for_user(
    user: UserCtx,
    stats: list[dict],
    rss_stats: list[dict] | None = None,
    *,
    db: AsyncSession,
    new_titles: dict | None = None,
    id_to_name: dict | None = None,
    failed_ids: list | None = None,
) -> dict[str, Any]:
    """渲染报告并投递到用户在 channel_filter 允许范围内的已启用渠道。

    Returns:
        {"enabled", "skipped", "reason", "report_type", "results", "html_path"}
    """
    mode = user.schedule.report_mode
    report_type = report_type_for_mode(mode)

    if not user.channels:
        return {
            "enabled": False, "skipped": True, "reason": "未配置投递渠道",
            "report_type": report_type, "results": {},
        }

    allowed = selected_channels(
        user.schedule.channel_filter, [c.channel for c in user.channels]
    )
    if not allowed:
        return {
            "enabled": False, "skipped": True, "reason": "渠道被 channel_filter 规则排除",
            "report_type": report_type, "results": {},
        }

    config = build_notification_config(user, allowed=allowed)
    if not any(k for k in ("FEISHU_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "GENERIC_WEBHOOK_URL", "EMAIL_FROM") if config.get(k)):
        return {
            "enabled": False, "skipped": True, "reason": "渠道凭证不完整",
            "report_type": report_type, "results": {},
        }

    tz = ZoneInfo(user.timezone or "Asia/Shanghai")
    get_time_func = lambda: datetime.now(tz)  # noqa: E731 - 供上游渲染取当地时间

    report_data = build_report_data(
        stats, mode=mode, new_titles=new_titles, id_to_name=id_to_name, failed_ids=failed_ids,
    )
    if not _has_content(report_data, rss_stats):
        return {
            "enabled": True, "skipped": True, "reason": "无匹配内容,跳过投递",
            "report_type": report_type, "results": {},
        }

    html_path = None
    if config.get("EMAIL_FROM"):
        html_path = await asyncio.to_thread(
            render_html_report,
            stats,
            user_id=user.user_id,
            mode=mode,
            rss_items=rss_stats,
            get_time_func=get_time_func,
        )

    results = await asyncio.to_thread(
        _dispatch_sync,
        config,
        report_data,
        report_type=report_type,
        mode=mode,
        html_file_path=html_path,
        rss_stats=rss_stats,
        get_time_func=get_time_func,
    )

    await _upsert_logs(db, user.user_id, results, get_time_func().date())

    return {
        "enabled": True,
        "skipped": False,
        "reason": "",
        "report_type": report_type,
        "results": {_DISPATCH_KEY_TO_CHANNEL.get(k, k): v for k, v in results.items()},
        "html_path": html_path,
    }