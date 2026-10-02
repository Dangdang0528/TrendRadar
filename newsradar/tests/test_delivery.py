# coding=utf-8
"""报告渲染 + 多渠道投递测试(mock 发送器,不触网)"""

import asyncio
import os
import uuid

import pytest

import app.adapters.pipeline_runner as pr
import app.adapters.report_renderer as rr
import trendradar.notification.dispatcher as dispatcher_mod
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


async def _create_user_with_channel(channel: str, credential: dict) -> int:
    from app.models.delivery_channel import DeliveryChannel
    from app.models.user import User
    from app.services.crypto import encrypt_credential

    async with AsyncSessionLocal() as s:
        u = User(email=f"d{uuid.uuid4().hex[:8]}@t.local", password_hash="x")
        s.add(u)
        await s.flush()
        uid = u.id
        s.add(
            DeliveryChannel(
                user_id=uid,
                channel=channel,
                label="测试渠道",
                credential_encrypted=encrypt_credential(credential),
                priority=0,
                enabled=True,
            )
        )
        await s.commit()
    return uid


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

    async def _run():
        async with AsyncSessionLocal() as s:
            user = await pr._load_user_ctx(uid, s)
            out = await deliver_report_for_user(user, STATS, None, db=s)
            await s.commit()  # 对齐 app.db.db_session 的提交语义
            return out

    out = asyncio.run(_run())
    assert out["enabled"] and not out["skipped"], out
    assert out["results"] == {"feishu": True}
    assert sent and sent[0]["url"] == "https://hook.ex/f"
    assert sent[0]["stats"], "应把渲染后的 stats 传给发送器"

    async def _log_status() -> str | None:
        from sqlalchemy import select

        from app.models.notification_log import NotificationLog

        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    select(NotificationLog).where(NotificationLog.user_id == uid)
                )
            ).scalar_one_or_none()
            return row.status if row else None

    assert asyncio.run(_log_status()) == "success"


def test_deliver_records_failed_status(monkeypatch):
    monkeypatch.setattr(
        dispatcher_mod, "send_to_feishu", lambda *a, **kw: False
    )
    uid = asyncio.run(
        _create_user_with_channel("feishu", {"webhook_url": "https://hook.ex/bad"})
    )

    async def _run():
        async with AsyncSessionLocal() as s:
            user = await pr._load_user_ctx(uid, s)
            out = await deliver_report_for_user(user, STATS, None, db=s)
            await s.commit()  # 对齐 app.db.db_session 的提交语义
            return out

    out = asyncio.run(_run())
    assert out["results"] == {"feishu": False}

    async def _log_status() -> str | None:
        from sqlalchemy import select

        from app.models.notification_log import NotificationLog

        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    select(NotificationLog).where(NotificationLog.user_id == uid)
                )
            ).scalar_one_or_none()
            return row.status if row else None

    assert asyncio.run(_log_status()) == "failed"


def test_deliver_skips_without_channels(monkeypatch):
    async def _create_user() -> int:
        from app.models.user import User

        async with AsyncSessionLocal() as s:
            u = User(email=f"n{uuid.uuid4().hex[:8]}@t.local", password_hash="x")
            s.add(u)
            await s.flush()
            uid = u.id
            await s.commit()
        return uid

    uid = asyncio.run(_create_user())

    async def _run():
        async with AsyncSessionLocal() as s:
            user = await pr._load_user_ctx(uid, s)
            return await deliver_report_for_user(user, STATS, None, db=s)

    out = asyncio.run(_run())
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

    async def _run():
        async with AsyncSessionLocal() as s:
            user = await pr._load_user_ctx(uid, s)
            return await deliver_report_for_user(user, [], None, db=s)

    out = asyncio.run(_run())
    assert out["skipped"] and "无匹配内容" in out["reason"]
    assert not called, "无内容时不应发起投递"