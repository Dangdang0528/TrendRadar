# coding=utf-8
"""订阅路由"""

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.subscription import (
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


@router.get("/platforms", response_model=PlatformList)
async def list_platforms():
    """列出 trendradar 内置平台清单,供前端勾选"""
    items = subscription_service.list_trendradar_platforms()
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
