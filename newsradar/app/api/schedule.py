# coding=utf-8
"""调度路由"""

from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.schemas.schedule import AIUsageSummary, ScheduleOut, ScheduleUpdate
from app.services import schedule_service

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("", response_model=ScheduleOut)
async def get_schedule(user: CurrentUser, db: DbSession):
    schedule = await schedule_service.get_or_create_schedule(db, user.id)
    return ScheduleOut.model_validate(schedule)


@router.put("", response_model=ScheduleOut)
async def put_schedule(payload: ScheduleUpdate, user: CurrentUser, db: DbSession):
    schedule = await schedule_service.update_schedule(
        db, user.id,
        cron_expr=payload.cron_expr,
        report_mode=payload.report_mode,
        enable_ai_summary=payload.enable_ai_summary,
        ai_language=payload.ai_language,
        ai_max_news=payload.ai_max_news,
        channel_filter=payload.channel_filter,
        enabled=payload.enabled,
    )
    return ScheduleOut.model_validate(schedule)


@router.get("/ai-usage", response_model=AIUsageSummary)
async def ai_usage(user: CurrentUser, db: DbSession):
    return await schedule_service.get_ai_usage_summary(db, user.id)
