"""正文抓取适配器:基于 trafilatura 抓取热搜链接的正文,并写入数据库缓存

定位:在不改上游 trendradar 的前提下,为"正文级 AI 深度总结"提供正文来源。

设计:
1. 抓取用开源库 trafilatura(fetch_url + extract),不重复造轮子。
2. "url → 正文" 缓存到 article_contents 表,命中缓存直接返回,避免重复抓取。
3. 失败记录(success=False),后续可据此跳过,不反复重试坏链接。
4. 提供 clean_old_cache() 供定时任务删除超过缓存 TTL 的过期记录。
"""

import asyncio
import time
from datetime import UTC
from urllib.parse import urlparse

import requests
from requests import RequestException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.models.article_content import ArticleContent

settings = get_settings()

# trafilatura 缺依赖时给出友好提示(保持可 import,便于测试分层)
try:
    from trafilatura import extract
    HAS_TRAFILATURA = True
except ImportError:  # pragma: no cover
    HAS_TRAFILATURA = False
    extract = None  # type: ignore


class ContentExtractor:
    """正文抓取器:带并发、单篇失败隔离、数据库缓存"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def get(self, url: str) -> str | None:
        """获取单个链接正文:先查缓存,未命中则抓取并写缓存"""
        async with self.session_factory() as session:
            row = await session.scalar(
                select(ArticleContent).where(ArticleContent.url == url)
            )
            if row and row.content:
                return row.content

        content = await asyncio.to_thread(_extract_once, url)
        await self._store(url, content)
        return content

    async def get_many(
        self,
        urls: list[str],
        concurrency: int | None = None,
    ) -> dict[str, str]:
        """批量获取;返回 {url: 正文},无正文的 url 不在结果中。

        - 命中缓存的直接取,避免重复抓取
        - 未命中用信号量限并发,单篇失败不影响整体
        """
        concurrency = concurrency or settings.CONTENT_EXTRACT_MAX_WORKERS
        sem = asyncio.Semaphore(concurrency)

        # 1. 一次性查缓存
        async with self.session_factory() as session:
            rows = await session.scalars(
                select(ArticleContent).where(ArticleContent.url.in_(urls))
            )
            cached = {r.url: r.content for r in rows if r.content}

        results = {u: c for u, c in cached.items()}
        to_fetch = [u for u in urls if u not in cached]

        async def _one(url: str) -> None:
            async with sem:
                try:
                    content = await asyncio.to_thread(_extract_once, url)
                except Exception:  # noqa: BLE001 - 单篇解析异常不应中断整体批量
                    content = None
                if content:
                    await self._store(url, content)
                    results[url] = content
                    print(f"[正文抓取] ok {url} ({len(content)}字)")
                else:
                    print(f"[正文抓取] skip {url}")

        if to_fetch:
            await asyncio.gather(*(_one(u) for u in to_fetch))
        return results

    async def _store(self, url: str, content: str | None) -> None:
        """写入/更新缓存。失败同样落库(success=False),避免反复失效重抓。"""
        domain = _domain_of(url) or ""
        success = bool(content)
        async with self.session_factory() as session:
            row = await session.scalar(
                select(ArticleContent).where(ArticleContent.url == url)
            )
            if row:
                row.content = content
                row.domain = domain
                row.success = success
            else:
                session.add(
                    ArticleContent(
                        url=url,
                        content=content,
                        domain=domain,
                        success=success,
                    )
                )
            await session.commit()

    async def clean_old_cache(self, ttl_days: int | None = None) -> int:
        """删除超过 TTL 的过期正文缓存。返回删除条数。

        供定时任务(如每日)调用;ttl_days 默认取配置 CONTENT_CACHE_TTL_DAYS。
        """
        from datetime import datetime, timedelta

        ttl = ttl_days or settings.CONTENT_CACHE_TTL_DAYS
        cutoff = datetime.now(UTC) - timedelta(days=ttl)
        async with self.session_factory() as session:
            res = await session.execute(
                delete(ArticleContent).where(ArticleContent.fetched_at < cutoff)
            )
            await session.commit()
            return res.rowcount or 0


# ---- 模块级同步抓取函数(便于独立单元测试)----


def _domain_of(url: str) -> str | None:
    """提取 url 域名"""
    try:
        return urlparse(url).hostname or None
    except Exception:  # noqa: BLE001 - 非法 URL 不应中断批量抓取
        return None


def _truncate(text: str, max_chars: int) -> str:
    """按字符截断,避免切碎中文"""
    return text if len(text) <= max_chars else text[:max_chars]


def _extract_once(url: str) -> str | None:
    """单篇抓取(同步、阻塞)。

    用 requests 抓 HTML(可控超时/UA),再交给 trafilatura.extract 提取正文——
    比 trafilatura.fetch_url 更可控(超时、请求头、代理),便于生产配置。
    """
    if not HAS_TRAFILATURA:
        raise RuntimeError("trafilatura 未安装,请执行 pip install trafilatura")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
    }
    try:
        resp = requests.get(url, headers=headers, timeout=settings.CONTENT_EXTRACT_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except RequestException:
        # 超时/连接失败/非 2xx:视为无正文,不中断批量
        return None

    # favor_precision:宁可漏,也不混入导航/评论等噪声(供正文级总结)
    text = extract(
        html,
        favor_precision=True,
        include_links=False,
        include_formatting=False,
        include_comments=False,
    )
    if not text:
        return None
    return _truncate(text, settings.CONTENT_EXTRACT_MAX_CHARS)


async def run_extraction_for_test() -> str:
    """端到端自测入口:抓取示意 url,验证流程可用"""
    from app.db import AsyncSessionLocal

    urls = [
        "https://www.bbc.com/news",
        "https://news.ycombinator.com/",
    ]
    extractor = ContentExtractor(AsyncSessionLocal)
    t0 = time.monotonic()
    result = await extractor.get_many(urls)
    elapsed = round(time.monotonic() - t0, 2)
    rows_desc = [f"{k}:{len(v)}字" for k, v in result.items()]
    return (
        f"ok: 抓取 {len(result)}/{len(urls)} 篇正文,"
        f"结果={rows_desc or '无'}, 耗时={elapsed}s"
    )