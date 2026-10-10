# coding=utf-8
"""订阅路由"""

import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.adapters import pipeline_runner
from app.adapters.config_provider import UserCtx
from app.deps import CurrentUser, DbSession
from app.schemas.subscription import (
    CrawlRunResult,
    CrawlRunState,
    GlobalFilterWords,
    InvalidSubscriptionConfig,
    PlatformInfo,
    PlatformList,
    PlatformSelection,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.services import subscription_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# ── 手动抓取:进程内单例(抓取要几十秒,故异步执行 + 前端轮询)────────
_crawl_lock = asyncio.Lock()
_crawl_state = CrawlRunState()
_crawl_task: asyncio.Task | None = None


@router.get("/platforms", response_model=PlatformList)
async def list_platforms():
    """列出 trendradar 内置平台清单(含各平台最近更新时间),供前端勾选"""
    # 扫描抓取库属于阻塞 I/O,放线程池执行
    items = await asyncio.to_thread(subscription_service.list_trendradar_platforms)
    return PlatformList(platforms=[PlatformInfo(**p) for p in items])


@router.put("/platforms", response_model=PlatformSelection)
async def replace_platforms(payload: PlatformSelection, user: CurrentUser, db: DbSession):
    """整体替换平台多选;传空列表 = 不限制 = 抓取全部平台"""
    try:
        ids = await subscription_service.replace_platforms(db, user.id, payload.platforms)
    except InvalidSubscriptionConfig as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return PlatformSelection(platforms=ids)


@router.get("/global-filters", response_model=GlobalFilterWords)
async def get_global_filters(user: CurrentUser, db: DbSession):
    """读取全局过滤词"""
    words = await subscription_service.get_global_filters(db, user.id)
    return GlobalFilterWords(words=words)


@router.put("/global-filters", response_model=GlobalFilterWords)
async def put_global_filters(payload: GlobalFilterWords, user: CurrentUser, db: DbSession):
    """整体替换全局过滤词(命中即排除整条新闻)"""
    words = await subscription_service.set_global_filters(db, user.id, payload.words)
    return GlobalFilterWords(words=words)


@router.post("/crawl", response_model=CrawlRunState)
async def trigger_crawl(user: CurrentUser, db: DbSession):
    """立刻按当前用户的订阅跑一次抓取,刷新各平台数据(不投递、不调用 AI)

    抓取需数十秒,这里立即返回 running 状态,由前端轮询 /crawl/status 取结果。
    """
    global _crawl_state, _crawl_task
    if _crawl_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="已有抓取任务在进行中,请稍候再试"
        )

    # 先在请求会话里把用户上下文读出来(抓取阶段会切换工作目录,不再碰 DB)
    ctx = await pipeline_runner._load_user_ctx(user.id, db)
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    await _crawl_lock.acquire()
    _crawl_state = CrawlRunState(running=True, started_at=datetime.now(timezone.utc))
    _crawl_task = asyncio.create_task(_run_crawl(ctx))
    return _crawl_state


@router.get("/crawl/status", response_model=CrawlRunState)
async def crawl_status(user: CurrentUser):
    """查询最近一次手动抓取的状态与结果"""
    return _crawl_state


async def _run_crawl(ctx: UserCtx) -> None:
    """后台执行抓取,把结果写回 _crawl_state"""
    global _crawl_state
    started = time.monotonic()
    started_at = _crawl_state.started_at
    try:
        outcome = await pipeline_runner.crawl_and_filter_for_user(ctx)
        _crawl_state = CrawlRunState(
            running=False,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            result=CrawlRunResult(
                ok=True,
                platforms=outcome.platforms,
                failed=outcome.failed,
                fetched=outcome.fetched,
                hotlist=len(outcome.stats),
                rss=len(outcome.rss_stats),
                elapsed_sec=round(time.monotonic() - started, 1),
            ),
        )
    except Exception as e:  # noqa: BLE001 - 后台任务无处抛出,统一记为状态
        _crawl_state = CrawlRunState(
            running=False,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error=f"{type(e).__name__}: {e}",
        )
    finally:
        _crawl_lock.release()


@router.get("", response_model=list[SubscriptionOut])
async def list_subs(user: CurrentUser, db: DbSession):
    subs = await subscription_service.list_subscriptions(db, user.id)
    return [SubscriptionOut.model_validate(s) for s in subs]


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
async def create_sub(payload: SubscriptionCreate, user: CurrentUser, db: DbSession):
    try:
        sub = await subscription_service.create_subscription(
            db, user.id,
            type=payload.type, target=payload.target, name=payload.name, config=payload.config,
        )
    except InvalidSubscriptionConfig as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return SubscriptionOut.model_validate(sub)


@router.patch("/{sub_id}", response_model=SubscriptionOut)
async def update_sub(sub_id: int, payload: SubscriptionUpdate, user: CurrentUser, db: DbSession):
    try:
        sub = await subscription_service.update_subscription(
            db, user.id, sub_id,
            name=payload.name, config=payload.config, enabled=payload.enabled,
        )
    except InvalidSubscriptionConfig as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return SubscriptionOut.model_validate(sub)


@router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sub(sub_id: int, user: CurrentUser, db: DbSession):
    ok = await subscription_service.delete_subscription(db, user.id, sub_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订阅不存在")
