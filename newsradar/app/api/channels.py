# coding=utf-8
"""渠道路由"""

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.channel import ChannelCreate, ChannelOut, ChannelTestResult, ChannelUpdate
from app.services import channel_service

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelOut])
async def list_channels(user: CurrentUser, db: DbSession):
    chs = await channel_service.list_channels(db, user.id)
    return [ChannelOut.model_validate(ch) for ch in chs]


@router.post("", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
async def create_channel(payload: ChannelCreate, user: CurrentUser, db: DbSession):
    try:
        ch = await channel_service.create_channel(
            db, user.id,
            channel=payload.channel, label=payload.label,
            credential=payload.credential, priority=payload.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ChannelOut.model_validate(ch)


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: int, payload: ChannelUpdate, user: CurrentUser, db: DbSession,
):
    try:
        ch = await channel_service.update_channel(
            db, user.id, channel_id,
            label=payload.label, credential=payload.credential,
            priority=payload.priority, enabled=payload.enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return ChannelOut.model_validate(ch)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: int, user: CurrentUser, db: DbSession):
    ok = await channel_service.delete_channel(db, user.id, channel_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="渠道不存在")


@router.post("/{channel_id}/test", response_model=ChannelTestResult)
async def test_channel(channel_id: int, user: CurrentUser, db: DbSession):
    """立即推送一条测试消息"""
    result = await channel_service.test_channel(db, user.id, channel_id)
    return ChannelTestResult(
        success=result["success"],
        message=result["message"],
        channel="tested",
        sent_at=result["sent_at"],
    )
