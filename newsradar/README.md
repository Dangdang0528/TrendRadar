# coding=utf-8
# NewsRadar

多租户新闻订阅 SaaS,基于 [TrendRadar](../trendradar) 核心构建。

## 目标(MVP 范围)

注册 → 订阅平台/RSS → 绑定飞书/邮箱 → 在指定时间收到推送;可选启用 AI 总结。

## 仓库结构(模式 B · 独立仓库)

```
/workspace
├── trendradar/        # 上游核心(零改动,作为 path 依赖引入)
└── newsradar/         # 本仓库
    ├── app/
    │   ├── main.py
    │   ├── config.py
    │   ├── db.py
    │   ├── deps.py
    │   ├── api/health.py
    │   ├── models/user.py
    │   └── adapters/
    │       ├── config_provider.py     # 把 UserCtx 翻译为 trendradar config dict
    │       └── pipeline_runner.py     # 调用 trendradar 流水线 + 投递
    ├── alembic/
    │   ├── env.py
    │   └── versions/0001_baseline_users.py
    ├── docker-compose.yml
    ├── Dockerfile
    ├── pyproject.toml
    ├── alembic.ini
    └── .env.example
```

## 阶段 0 启动

> 所有命令在 `/workspace` 目录下执行,因为 docker-compose 的 build context 是 `/workspace`,
> 这样 Dockerfile 能同时 `COPY trendradar/` 与 `COPY newsradar/`。

### 1. 准备 .env

```sh
cd /workspace/newsradar
cp .env.example .env
# 按需修改 SECRET_KEY / CREDENTIAL_ENCRYPTION_KEY / AI_API_KEY
```

### 2. 拉起 api + db + redis

```sh
cd /workspace
docker compose -f newsradar/docker-compose.yml up --build
```

启动后:
- API:`http://localhost:8000`
- OpenAPI:`http://localhost:8000/docs`
- 健康检查:`http://localhost:8000/health/ready`

### 3. 验证适配层

```sh
docker compose -f newsradar/docker-compose.yml exec api \
  python -c "from app.adapters.pipeline_runner import run_pipeline_once_for_test; print(run_pipeline_once_for_test())"
```

预期输出:`{"ok": true, "config_keys": [...], "ctx_class": "AppContext", "user_email": "test@local"}`,
证明 trendradar 核心已成功 import 且 config dict 结构正确。

## 后续阶段

- **阶段 1**:用户/认证 + 订阅/渠道 CRUD
- **阶段 2**:Arq worker + per-user 调度 + 端到端投递;接入 AI 总结(方案 B)

## 技术栈

FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis 7 · Arq · pydantic-settings ·
trendradar(core,以 path 依赖引入)
