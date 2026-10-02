# coding=utf-8
"""报告渲染 + 多渠道投递测试(mock 发送器,不触网)"""

import asyncio
import os
import uuid

import pytest

import app.adapters.pipeline_runner as pr
import app.adapters.report_renderer as rr
import trendradar.notification.dispatcher as dispatcher_mod
from app.adapters import delivery
from app.adapters.delivery import deliver_report_for_user
from app.db import AsyncSessionLocal, Base, engine

STATS = [
    {
        "word": "AI 应用",
        "count": 2,
        "titles": [
            {
                "title": "标题A:AI 应用加速",
                "source_name": "微博",
                "time_display": "09:00",
                "count": 1,
                "ranks": [1],
                "rank_threshold": 3,
                "url": "https://a.ex/1",
                "mobile_url": "",
            },
            {
                "title": "标题B:AI 应用监管",
                "source_name": "知乎",
                "time_display": "09:05",
                "count": 1,
                "ranks": [2],
                "rank_threshold": 3,
                "url": "https://a.ex/2",
                "mobile_url": "",
            },
        ],
    }
]


@pytest.fixture(autouse=True)
def _prepare():
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield


async def _create_user(
    channels: list[tuple[str, dict]] | None = None,
    channel_filter: dict | None = None,
) -> int:
    from app.models.delivery_channel import DeliveryChannel
    from app.models.user import User
    from app.models.user_schedule import UserSchedule
    from app.services.crypto import encrypt_credential

    async with AsyncSessionLocal() as s:
        u = User(email=f"d{uuid.uuid4().hex[:8]}@t.local", password_hash="x")
        s.add(u)
        await s.flush()
        uid = u.id
        for idx, (channel, credential) in enumerate(channels or []):
            s.add(
                DeliveryChannel(
                    user_id=uid,
                    channel=channel,
                    label=f"测试渠道{idx}",
                    credential_encrypted=encrypt_credential(credential),
                    priority=0,
                    enabled=True,
                )
            )
        if channel_filter is not None:
            s.add(UserSchedule(user_id=uid, channel_filter=channel_filter))
        await s.commit()
    return uid


async def _create_user_with_channel(channel: str, credential: dict) -> int:
    return await _create_user([(channel, credential)])


def _run_delivery(uid: int, stats: list[dict] | None = None) -> dict:
    async def _inner():
        async with AsyncSessionLocal() as s:
            user = await pr._load_user_ctx(uid, s)
            out = await deliver_report_for_user(user, STATS if stats is None else stats, None, db=s)
            await s.commit()  # 对齐 app.db.db_session 的提交语义
            return out

    return asyncio.run(_inner())


def _log_status(uid: int) -> str | None:
    async def _inner():
        from sqlalchemy import select

        from app.models.notification_log import NotificationLog

        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    select(NotificationLog).where(NotificationLog.user_id == uid)
                )
            ).scalar_one_or_none()
            return row.status if row else None

    return asyncio.run(_inner())


# ── 渲染 ─────────────────────────────────────────────────────


def test_build_report_data_and_render_content():
    report_data = rr.build_report_data(STATS, mode="daily")
    assert report_data["stats"][0]["word"] == "AI 应用"
    # 标题被 prepare_report_data 规范化,url 保留
    assert report_data["stats"][0]["titles"][0]["url"] == "https://a.ex/1"

    batches = rr.render_channel_content(
        report_data, "feishu", mode="daily", report_type="全天汇总"
    )
    text = "\n".join(batches)
    assert "AI 应用" in text
    assert "标题A" in text and "标题B" in text


def test_render_html_report_writes_file(work_dir):
    path = rr.render_html_report(STATS, user_id=1, mode="daily")
    assert os.path.exists(path)
    assert path.endswith(".html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    assert "<html" in html.lower()
    assert "AI 应用" in html


# ── 投递 ─────────────────────────────────────────────────────


def test_deliver_report_dispatches_and_logs(monkeypatch):
    sent = []

    def _fake_feishu(webhook_url, report_data, report_type, **kwargs):
        sent.append({"url": webhook_url, "type": report_type, "stats": report_data["stats"]})
        return True

    monkeypatch.setattr(dispatcher_mod, "send_to_feishu", _fake_feishu)

    uid = asyncio.run(
        _create_user_with_channel("feishu", {"webhook_url": "https://hook.ex/f"})
    )

    out = _run_delivery(uid)
    assert out["enabled"] and not out["skipped"], out
    assert out["results"] == {"feishu": True}
    assert sent and sent[0]["url"] == "https://hook.ex/f"
    assert sent[0]["stats"], "应把渲染后的 stats 传给发送器"

    assert _log_status(uid) == "success"


def test_deliver_records_failed_status(monkeypatch):
    monkeypatch.setattr(
        dispatcher_mod, "send_to_feishu", lambda *a, **kw: False
    )
    uid = asyncio.run(
        _create_user_with_channel("feishu", {"webhook_url": "https://hook.ex/bad"})
    )

    out = _run_delivery(uid)
    assert out["results"] == {"feishu": False}

    assert _log_status(uid) == "failed"


def test_deliver_skips_without_channels(monkeypatch):
    uid = asyncio.run(_create_user())

    out = _run_delivery(uid)
    assert out["skipped"] and out["reason"] == "未配置投递渠道"
    assert out["results"] == {}


def test_deliver_skips_without_content(monkeypatch):
    called = []
    monkeypatch.setattr(
        dispatcher_mod, "send_to_feishu", lambda *a, **kw: called.append(1) or True
    )
    uid = asyncio.run(
        _create_user_with_channel("feishu", {"webhook_url": "https://hook.ex/f"})
    )

    out = _run_delivery(uid, stats=[])
    assert out["skipped"] and "无匹配内容" in out["reason"]
    assert not called, "无内容时不应发起投递"


# ── channel_filter ───────────────────────────────────────────


def test_selected_channels_rules():
    avail = ["feishu", "email", "telegram"]

    # 不过滤
    assert delivery.selected_channels(None, avail) == avail
    assert delivery.selected_channels({}, avail) == avail
    assert delivery.selected_channels({"include": []}, avail) == avail

    # 白名单(忽略大小写与空白)
    assert delivery.selected_channels({"include": ["Feishu "]}, avail) == ["feishu"]

    # 黑名单
    assert delivery.selected_channels({"exclude": ["email"]}, avail) == ["feishu", "telegram"]

    # exclude 优先级高于 include
    assert delivery.selected_channels(
        {"include": ["feishu", "email"], "exclude": ["email"]}, avail
    ) == ["feishu"]

    # 过滤为空 → 空列表(调用方按"无人接收"处理)
    assert delivery.selected_channels({"include": ["webhook"]}, avail) == []


def _stub_senders(monkeypatch, sent: list[str]):
    monkeypatch.setattr(
        dispatcher_mod, "send_to_feishu", lambda *a, **kw: sent.append("feishu") or True
    )
    monkeypatch.setattr(
        dispatcher_mod, "send_to_telegram", lambda *a, **kw: sent.append("telegram") or True
    )


TWO_CHANNELS = [
    ("feishu", {"webhook_url": "https://hook.ex/f"}),
    ("telegram", {"bot_token": "bot-token", "chat_id": "123"}),
]


def test_channel_filter_include_limits_delivery(monkeypatch):
    sent: list[str] = []
    _stub_senders(monkeypatch, sent)
    uid = asyncio.run(_create_user(TWO_CHANNELS, channel_filter={"include": ["feishu"]}))

    out = _run_delivery(uid)
    assert out["results"] == {"feishu": True}
    assert sent == ["feishu"]
    assert _log_status(uid) == "success"


def test_channel_filter_exclude_wins(monkeypatch):
    sent: list[str] = []
    _stub_senders(monkeypatch, sent)
    uid = asyncio.run(
        _create_user(
            TWO_CHANNELS,
            channel_filter={"include": ["feishu", "telegram"], "exclude": ["telegram"]},
        )
    )

    out = _run_delivery(uid)
    assert out["results"] == {"feishu": True}
    assert sent == ["feishu"]


def test_channel_filter_excluding_all_skips(monkeypatch):
    sent: list[str] = []
    _stub_senders(monkeypatch, sent)
    # 只允许 webhook,但用户没配 webhook
    uid = asyncio.run(_create_user(TWO_CHANNELS, channel_filter={"include": ["webhook"]}))

    out = _run_delivery(uid)
    assert out["skipped"] and "channel_filter" in out["reason"]
    assert sent == [], "被筛掉的渠道不应发起投递"