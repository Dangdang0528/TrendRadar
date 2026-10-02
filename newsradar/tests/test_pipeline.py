# coding=utf-8
"""抓取 + 流水线编排测试(mock 网络抓取与 AI,SQLite 落库)"""

import asyncio
import json
import uuid

import pytest

import app.adapters.content_extractor as ce_mod
import app.adapters.pipeline_runner as pr
import trendradar.ai.client as client_mod
import trendradar.crawler.fetcher as fetcher_mod
from app.config import get_settings
from app.db import AsyncSessionLocal, Base, engine

FAKE_AI = {
    "executive_summary": "主线:AI 应用加速。",
    "item_analyses": [{"title": "标题A:AI 应用加速", "summary": "概要", "key_points": "1. 点", "significance": "重要"}],
    "cross_insights": "共振",
    "outlook": "关注监管",
}


def _fake_crawl(self, ids_list, request_interval=100, domain_rules=None):
    """模拟热榜抓取:3 条,其中 1 条不含关键词,应被过滤"""
    results = {
        "weibo": {
            "标题A:AI 应用加速": {"ranks": [1], "url": "https://a.ex/1", "mobileUrl": ""},
            "标题B:行业观察": {"ranks": [2], "url": "https://a.ex/2", "mobileUrl": ""},
            "无关财经新闻": {"ranks": [3], "url": "https://a.ex/3", "mobileUrl": ""},
        }
    }
    return results, {"weibo": "微博"}, []


class FakeAIClient:
    def __init__(self, config):
        pass

    def chat(self, messages, **kwargs):
        return "```json\n" + json.dumps(FAKE_AI, ensure_ascii=False) + "\n```"


@pytest.fixture(autouse=True)
def _prepare():
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield


async def _create_user(*, enable_ai: bool, keyword: str | None = "标题") -> int:
    from app.models.subscription import Subscription
    from app.models.user import User
    from app.models.user_schedule import UserSchedule

    async with AsyncSessionLocal() as s:
        u = User(email=f"u{uuid.uuid4().hex[:8]}@t.local", password_hash="x")
        s.add(u)
        await s.flush()
        uid = u.id
        s.add(
            UserSchedule(
                user_id=uid,
                report_mode="daily",
                enable_ai_summary=enable_ai,
                ai_max_news=10,
            )
        )
        s.add(Subscription(user_id=uid, type="platform", target="weibo", name="微博"))
        if keyword:
            s.add(Subscription(user_id=uid, type="keyword", target=keyword))
        await s.commit()
    return uid


def test_crawl_and_filter_applies_keyword(monkeypatch):
    monkeypatch.setattr(fetcher_mod.DataFetcher, "crawl_websites", _fake_crawl)
    uid = asyncio.run(_create_user(enable_ai=False))

    async def _run():
        async with AsyncSessionLocal() as s:
            user = await pr._load_user_ctx(uid, s)
        return await pr.crawl_and_filter_for_user(user)

    stats, rss = asyncio.run(_run())
    titles = [t["title"] for g in stats for t in g["titles"]]
    assert stats, "stats 不应为空"
    assert "无关财经新闻" not in titles, f"关键词过滤失效: {titles}"
    assert any("标题A" in t for t in titles)
    # 每条都带 url(供正文抓取使用)
    assert all(t.get("url") for g in stats for t in g["titles"])


def test_full_pipeline_end_to_end(monkeypatch):
    monkeypatch.setattr(fetcher_mod.DataFetcher, "crawl_websites", _fake_crawl)
    monkeypatch.setattr(client_mod, "AIClient", FakeAIClient)

    async def _fake_get_many(self, urls, concurrency=None):
        return {u: f"正文:{u}" for u in urls if u.startswith("https://a.ex/")}

    monkeypatch.setattr(ce_mod.ContentExtractor, "get_many", _fake_get_many)
    monkeypatch.setattr(get_settings(), "AI_API_KEY", "test-key", raising=False)

    uid = asyncio.run(_create_user(enable_ai=True))
    out = asyncio.run(pr.run_pipeline_for_user(uid))

    assert out["ok"], out
    assert out["steps"]["crawl"]["hotlist"] >= 1
    ai = out["steps"]["ai_deep_summary"]
    assert ai["enabled"] and ai["success"] and ai["analyzed"] >= 1
    assert out["ai_deep_summary"].executive_summary == FAKE_AI["executive_summary"]

    async def _count_usage() -> int:
        from sqlalchemy import func, select

        from app.models.ai_usage import AIUsage

        async with AsyncSessionLocal() as s:
            return (await s.execute(select(func.count()).select_from(AIUsage))).scalar_one()

    assert asyncio.run(_count_usage()) >= 1


def test_pipeline_skips_ai_without_key(monkeypatch):
    monkeypatch.setattr(fetcher_mod.DataFetcher, "crawl_websites", _fake_crawl)
    monkeypatch.setattr(get_settings(), "AI_API_KEY", "", raising=False)

    uid = asyncio.run(_create_user(enable_ai=True))
    out = asyncio.run(pr.run_pipeline_for_user(uid))

    assert out["ok"]
    assert out["steps"]["ai_deep_summary"] == {"enabled": False}