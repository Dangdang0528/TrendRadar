# coding=utf-8
"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.config import get_settings
from app.db import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期

    MVP 阶段:启动时自动建表(仅 dev 环境,生产用 alembic upgrade head)
    """
    if settings.APP_ENV == "dev" and settings.DEBUG:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="多租户新闻订阅 SaaS(基于 TrendRadar 核心)",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="")


@app.get("/")
async def root() -> dict:
    return {
        "service": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
