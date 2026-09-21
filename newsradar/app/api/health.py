# coding=utf-8
"""健康检查与基础元数据端点"""

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health() -> dict:
    """Liveness probe"""
    return {"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV}


@router.get("/health/ready")
async def readiness() -> dict:
    """Readiness probe:轻量检查 DB / Redis 连通性"""
    from app.db import engine
    from sqlalchemy import text

    checks: dict[str, str] = {}

    # DB
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"fail: {type(e).__name__}"

    # Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, encoding="utf-8")
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"fail: {type(e).__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
