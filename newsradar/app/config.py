# coding=utf-8
"""应用配置:从环境变量加载,12-factor 风格"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置

    所有配置通过环境变量或 .env 文件注入,见 .env.example
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # === 应用 ===
    APP_NAME: str = "NewsRadar"
    APP_ENV: str = Field(default="dev", description="dev / prod")
    DEBUG: bool = True
    SECRET_KEY: str = "dev-only-change-me-in-production-please-32bytes+"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # === 数据库 ===
    DATABASE_URL: str = "postgresql+psycopg://newsradar:newsradar@db:5432/newsradar"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # === Redis / 队列 ===
    REDIS_URL: str = "redis://redis:6379/0"
    ARQ_MAX_TRIES: int = 3
    ARQ_TIMEOUT_SECONDS: int = 600
    WORKER_CONCURRENCY: int = 4

    # === 邮件(注册激活) ===
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 465
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None
    APP_BASE_URL: str = "http://localhost:8000"

    # === 凭证加密 ===
    CREDENTIAL_ENCRYPTION_KEY: str = "dev-only-change-me-32-bytes-base64-or-hex!!"

    # === AI 全局 key(方案 B:per-user 开关,全局一个 key)===
    AI_API_KEY: Optional[str] = None
    AI_MODEL: str = "gpt-4o-mini"
    AI_API_BASE: Optional[str] = None
    AI_TIMEOUT: int = 120
    AI_MAX_TOKENS: int = 5000

    # === 正文抓取(正文级 AI 深度总结) ===
    # 正文抓取并发数(过多易触发反爬/被限速)
    CONTENT_EXTRACT_MAX_WORKERS: int = 4
    # 单篇正文截断后的最大字符数(控 token 成本)
    CONTENT_EXTRACT_MAX_CHARS: int = 800
    # 抓取 HTTP 超时(秒)
    CONTENT_EXTRACT_TIMEOUT: int = 10
    # 正文缓存保留时长(天),到期的缓存会被清理任务删除
    CONTENT_CACHE_TTL_DAYS: int = 30

    # === TrendRadar 核心 ===
    # trendradar 的工作目录(读取 config/*.txt prompt、写入 output/news/*.db)
    TRENDRADAR_WORK_DIR: str = "/workspace"
    # trendradar 抓取用的平台 API(参考 config.yaml)
    PLATFORMS_API_URL: Optional[str] = None

    # === 速率限制 ===
    AI_GLOBAL_RATE_LIMIT_PER_MINUTE: int = 30
    AI_PER_USER_RATE_LIMIT_PER_HOUR: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
