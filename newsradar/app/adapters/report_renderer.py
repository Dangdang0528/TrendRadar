"""报告渲染(阶段 2)

把抓取阶段产出的 热榜 stats / RSS stats 渲染成可投递的内容:
- build_report_data      → trendradar 通知层认识的 report_data 结构
- render_channel_content → 指定渠道的分批消息文本(飞书卡片 markdown / Telegram / 通用 webhook)
- render_html_report     → 落盘的 HTML 报告文件(邮件渠道的正文)

全部复用 trendradar 的报告/通知模块,零上游改动。
"""

import os
from datetime import datetime
from typing import Any, Callable

from app.config import get_settings

# 报告模式 → 报告类型标签(与 trendradar MODE_STRATEGIES 的 report_type 对齐)
REPORT_TYPE_BY_MODE = {
    "daily": "全天汇总",
    "current": "当前榜单",
    "incremental": "增量分析",
}

# 我方渠道名 → trendradar split_content_into_batches 的 format_type
# (邮件走 HTML,不参与文本分批;通用 webhook 用 markdown 风格)
CHANNEL_FORMAT_TYPE = {
    "feishu": "feishu",
    "telegram": "telegram",
    "webhook": "wework",
    "email": "wework",
}


def report_type_for_mode(mode: str) -> str:
    """报告模式 → 报告类型标签"""
    return REPORT_TYPE_BY_MODE.get(mode, "全天汇总")


def build_report_data(
    stats: list[dict],
    *,
    mode: str = "daily",
    new_titles: dict | None = None,
    id_to_name: dict | None = None,
    failed_ids: list | None = None,
) -> dict:
    """把 stats 转成通知/HTML 渲染所需的 report_data"""
    from trendradar.report.generator import prepare_report_data

    return prepare_report_data(
        stats=stats or [],
        failed_ids=failed_ids,
        new_titles=new_titles,
        id_to_name=id_to_name,
        mode=mode,
    )


def render_channel_content(
    report_data: dict,
    channel: str,
    *,
    mode: str = "daily",
    report_type: str = "",
    rss_items: list[dict] | None = None,
    get_time_func: Callable[[], Any] | None = None,
) -> list[str]:
    """渲染指定渠道的推送内容,返回按渠道上限分批后的消息列表"""
    from trendradar.notification.splitter import split_content_into_batches

    fmt = CHANNEL_FORMAT_TYPE.get(channel)
    if not fmt:
        raise ValueError(f"不支持的渠道渲染: {channel}")

    return split_content_into_batches(
        report_data=report_data,
        format_type=fmt,
        mode=mode,
        rss_items=rss_items,
        get_time_func=get_time_func or datetime.now,
        report_type=report_type or report_type_for_mode(mode),
    )


def render_html_report(
    stats: list[dict],
    *,
    user_id: int,
    mode: str = "daily",
    rss_items: list[dict] | None = None,
    report_metadata: dict | None = None,
    get_time_func: Callable[[], Any] | None = None,
) -> str:
    """渲染 HTML 报告并落盘,返回文件路径(供邮件渠道作为正文)"""
    from trendradar.report.generator import prepare_report_data
    from trendradar.report.html import render_html_content

    now = get_time_func() if get_time_func else datetime.now()
    report_data = prepare_report_data(stats=stats or [], mode=mode)
    if report_metadata:
        report_data.update(report_metadata)

    html = render_html_content(
        report_data=report_data,
        total_titles=sum(len(s.get("titles", [])) for s in (stats or [])),
        mode=mode,
        get_time_func=lambda: now,
        rss_items=rss_items,
    )

    out_dir = os.path.join(get_settings().TRENDRADAR_WORK_DIR, "output", "newsradar_reports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"u{user_id}-{mode}-{now.strftime('%Y%m%d%H%M%S')}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path