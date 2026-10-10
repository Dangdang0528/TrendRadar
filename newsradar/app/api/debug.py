# coding=utf-8
"""调试路由:正文抓取效果预览

仅 DEBUG 模式开放(生产 DEBUG=false 时整体返回 404)。
用途:选择一个/多个链接,直接跑一遍正文抓取,看抓到的正文质量与字数,不调用 AI、不产生费用。
"""

import asyncio
import glob
import os
import sqlite3

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.adapters.content_extractor import ContentExtractor
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.deps import CurrentUser
from app.models.article_content import ArticleContent

router = APIRouter(prefix="/debug", tags=["debug"])

# 单次最多试抓的链接数(避免误操作发起大量请求)
MAX_URLS = 20
# 返回给前端的正文预览字符数
PREVIEW_CHARS = 600


class HotlistItem(BaseModel):
    title: str
    url: str
    source: str = ""


class HotlistOut(BaseModel):
    date: str
    dates: list[str] = Field(default_factory=list, description="可选的热榜日期")
    items: list[HotlistItem]


class ExtractRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, description="待试抓的链接")
    force: bool = Field(default=False, description="true=忽略缓存重新抓取")


class ExtractItem(BaseModel):
    url: str
    ok: bool
    from_cache: bool = False
    length: int = 0
    content: str = ""


class ExtractResult(BaseModel):
    total: int
    ok_count: int
    results: list[ExtractItem]


def _ensure_debug_enabled() -> None:
    """非 DEBUG 环境整体隐藏该路由"""
    if not get_settings().DEBUG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _news_db_files() -> list[str]:
    """全部热榜 SQLite 路径(按日期升序)"""
    pattern = os.path.join(
        get_settings().TRENDRADAR_WORK_DIR, "output", "news", "*.db"
    )
    return sorted(glob.glob(pattern))


def _news_db_for(date: str | None) -> str | None:
    """指定日期的热榜库;date 为空时取最近一天"""
    files = _news_db_files()
    if not files:
        return None
    if date:
        candidate = os.path.join(os.path.dirname(files[-1]), f"{date}.db")
        return candidate if os.path.exists(candidate) else None
    return files[-1]


@router.get("/hotlist", response_model=HotlistOut)
async def hotlist(user: CurrentUser, date: str | None = None, limit: int = 15):
    """读取某天抓取的热榜条目,供前端一键挑选试抓目标

    默认取最近一天;同一天里 weibo 等平台存的是搜索跳转链接(抓不到正文),
    可切换到较早日期或手动粘贴链接。
    """
    _ensure_debug_enabled()
    path = _news_db_for(date)
    if not path:
        raise HTTPException(status_code=404, detail="暂无热榜数据,请先执行一次抓取")

    def _read() -> list[HotlistItem]:
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "select title, url, platform_id from news_items "
                "where url is not null and url <> '' order by rank asc"
            ).fetchall()
        finally:
            conn.close()

        items: list[HotlistItem] = []
        seen: set[str] = set()
        for title, url, platform_id in rows:
            if url in seen:
                continue
            seen.add(url)
            items.append(
                HotlistItem(title=title or "", url=url, source=platform_id or "")
            )
            if len(items) >= limit:
                break
        return items

    items = await asyncio.to_thread(_read)
    dates = [os.path.basename(f).removesuffix(".db") for f in _news_db_files()]
    return HotlistOut(
        date=os.path.basename(path).removesuffix(".db"),
        dates=list(reversed(dates)),
        items=items,
    )


@router.post("/extract", response_model=ExtractResult)
async def extract(payload: ExtractRequest, user: CurrentUser):
    """对给定链接试抓正文,返回逐条结果(仅抓正文,不做 AI 分析)"""
    _ensure_debug_enabled()
    urls = list(dict.fromkeys(u.strip() for u in payload.urls if u.strip()))[:MAX_URLS]
    if not urls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请至少提供一个链接"
        )

    # 先记录抓取前的缓存状态,用于标记 from_cache
    cached: dict[str, str | None] = {}
    if not payload.force:
        async with AsyncSessionLocal() as session:
            rows = await session.scalars(
                select(ArticleContent).where(ArticleContent.url.in_(urls))
            )
            cached = {r.url: r.content for r in rows}

    contents = await ContentExtractor(AsyncSessionLocal).get_many(
        urls, force=payload.force
    )

    results: list[ExtractItem] = []
    for url in urls:
        content = contents.get(url)
        results.append(
            ExtractItem(
                url=url,
                ok=bool(content),
                from_cache=bool(content) and bool(cached.get(url)),
                length=len(content) if content else 0,
                content=(content or "")[:PREVIEW_CHARS],
            )
        )
    return ExtractResult(
        total=len(urls),
        ok_count=sum(1 for r in results if r.ok),
        results=results,
    )