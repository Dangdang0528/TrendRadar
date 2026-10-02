# coding=utf-8
"""FastAPI 应用入口"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, channels, health, schedule, subscriptions
from app.config import get_settings
from app.db import Base, engine

settings = get_settings()

# 前端构建产物目录(frontend/dist)。存在则由此服务托管 SPA;
# 开发期用 `cd frontend && npm run dev`(Vite 代理 /api 到本服务),不依赖此目录。
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


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


# ── 前端 SPA 托管(需先构建 frontend/dist)──────────────────────
# 挂载顺序:API 路由(/api、/health、/docs 等)已在前注册,优先匹配;
# catch-all 仅兜底非 API 路径,保证前端路由刷新不 404。
# 开发期用 `cd frontend && npm run dev`(Vite 代理 /api 到本服务)。
if FRONTEND_DIST.is_dir():
    _assets_dir = FRONTEND_DIST / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    _RESERVED_PREFIXES = ("api/", "assets/", "health", "docs", "redoc", "openapi.json")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith(_RESERVED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

else:

    @app.get("/")
    async def root() -> dict:
        return {
            "service": settings.APP_NAME,
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
            "hint": "前端未构建;执行 cd frontend && npm run build 后由本服务托管",
        }
