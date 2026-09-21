# NewsRadar Dockerfile
# 阶段 0:基础镜像
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 系统依赖(bcrypt/cryptography/psycopg 编译需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# === 步骤 1:把 trendradar 源码拷进来(从平级目录)===
# 在 docker build context = /workspace 时,trendradar/ 目录可见
COPY trendradar/ /app/vendor/trendradar/
COPY config/ /app/vendor/config/
COPY mcp_server/ /app/vendor/mcp_server/
COPY pyproject.toml /app/vendor/pyproject.toml
COPY version /app/vendor/version

# === 步骤 2:安装 trendradar ===
RUN pip install -e /app/vendor

# === 步骤 3:把 newsradar 自身拷进来 ===
COPY newsradar/pyproject.toml newsradar/README.md /app/newsradar/
COPY newsradar/app/ /app/newsradar/app/
COPY newsradar/alembic.ini /app/newsradar/alembic.ini
COPY newsradar/alembic/ /app/newsradar/alembic/

WORKDIR /app/newsradar

# === 步骤 4:安装 newsradar 自身(含所有依赖)===
RUN pip install -e .

ENV PYTHONPATH=/app/newsradar:/app/vendor

EXPOSE 8000

# 默认启动 API;worker 用同样镜像、不同 entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
