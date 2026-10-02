# coding=utf-8
"""正文级 AI 深度总结引擎单测(不触网,AI 与正文抓取均 mock)"""

import asyncio
import json

import pytest

import app.adapters.content_extractor as ce_mod
import trendradar.ai.client as client_mod
from app.adapters import deep_summary as ds

FAKE_AI = {
    "executive_summary": "主线:AI 应用加速落地。",
    "item_analyses": [
        {"title": "T1", "summary": "概要1", "key_points": "1. 要点", "significance": "重要"}
    ],
    "cross_insights": "多源共振",
    "outlook": "关注监管节奏",
}


def _stats_fixture() -> list[dict]:
    return [
        {
            "word": "AI",
            "titles": [
                {"title": "T1", "url": "https://ex.com/1", "source_name": "微博"},
                {"title": "T2", "url": "https://ex.com/2", "source_name": "微博"},
            ],
        },
        {
            "word": "科技",
            "titles": [
                {"title": "T1", "url": "https://ex.com/1", "source_name": "微博"},  # 重复 url
                {"title": "T3", "url": "https://ex.com/3", "source_name": "知乎"},
            ],
        },
    ]


def test_collect_candidates_dedup_and_cap():
    items = ds.collect_candidates(_stats_fixture(), None, max_news=2)
    assert [i.title for i in items] == ["T1", "T2"]  # 去重 + 截断
    assert items[0].url == "https://ex.com/1"
    assert items[0].source == "微博"


def test_collect_candidates_without_url_falls_back_to_title():
    stats = [{"titles": [{"title": "只有标题", "source_name": "X"}]}]
    items = ds.collect_candidates(stats)
    assert len(items) == 1 and items[0].url == "" and items[0].title == "只有标题"


@pytest.mark.parametrize(
    "raw",
    [
        "```json\n" + json.dumps(FAKE_AI, ensure_ascii=False) + "\n```",
        json.dumps(FAKE_AI, ensure_ascii=False),
        "前缀噪声 " + json.dumps(FAKE_AI, ensure_ascii=False) + " 后缀",
    ],
)
def test_parse_json_response_variants(raw):
    assert ds._parse_json_response(raw)["executive_summary"] == FAKE_AI["executive_summary"]


def test_parse_json_response_empty():
    assert ds._parse_json_response("") == {}


def _fake_extractor(contents: dict[str, str]):
    """构造一个 get_many 被替换的 ContentExtractor"""

    class _Ex:
        async def get_many(self, urls, concurrency=None):
            return {u: contents[u] for u in urls if u in contents}

    return _Ex()


def test_run_content_deep_summary_success(monkeypatch):
    class FakeAIClient:
        def __init__(self, config):
            pass

        def chat(self, messages, **kwargs):
            return "```json\n" + json.dumps(FAKE_AI, ensure_ascii=False) + "\n```"

    monkeypatch.setattr(client_mod, "AIClient", FakeAIClient)

    extractor = _fake_extractor({"https://ex.com/1": "正文一", "https://ex.com/2": "正文二"})
    result = asyncio.run(
        ds.run_content_deep_summary(
            stats=_stats_fixture(),
            extractor=extractor,
            max_news=10,
            get_time_func=lambda: "2026-01-01 00:00:00",
        )
    )
    assert result.success and not result.skipped
    assert result.analyzed == 2  # T1/T2 有正文;T3 无
    assert result.executive_summary == FAKE_AI["executive_summary"]
    assert len(result.item_analyses) == 1


def test_run_content_deep_summary_skips_without_content(monkeypatch):
    # 抓不到任何正文 → 优雅跳过,不编造、不报错
    extractor = _fake_extractor({})
    result = asyncio.run(
        ds.run_content_deep_summary(
            stats=_stats_fixture(),
            extractor=extractor,
            get_time_func=lambda: "2026-01-01 00:00:00",
        )
    )
    assert result.skipped and not result.success
    assert result.analyzed == 0
    assert "未获取到任何正文" in result.error