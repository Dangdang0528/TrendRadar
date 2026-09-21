# coding=utf-8
"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, channels, health, schedule, subscriptions
from app.config import get_settings
from app.db import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期

    dev 模式下自动建表(生产用 alembic upgrade head)。
    注册所有 ORM 模型到 Base.metadata。
    """
    # 触发所有模型注册
    import app.models  # noqa: F401

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

# CORS:MVP 阶段放开,前端 Alpine.js 单页可直接调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(health.router, prefix="")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(subscriptions.router, prefix="/api/v1")
app.include_router(channels.router, prefix="/api/v1")
app.include_router(schedule.router, prefix="/api/v1")


@app.get("/")
async def root() -> dict:
    return {
        "service": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
