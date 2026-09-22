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

## 部署 · 宝塔 Linux 面板 + Docker

> 本章针对**宝塔(BT)Linux 面板**环境。核心思路:代码与 Docker 都在服务器上,
> 通过宝塔的「终端/SSH」执行 `docker compose`,再在宝塔「网站」里做反向代理与域名绑定。

### 1. 目录结构(必须的两个仓库同级)

Dockerfile 的 `build context` 是 `..`(即父目录),因此 `trendradar/` 与 `newsradar/`
**必须放在同一个父目录**下。在宝塔建议放:

```
/www/wwwroot/newsradar-project/
├── trendradar/     # 上游核心仓库
└── newsradar/      # 本仓库
```

### 2. 上传代码

- 宝塔「文件」→ 进入 `/www/wwwroot/`,新建目录 `newsradar-project`
- 分别上传/拉取 `trendradar` 与 `newsradar` 两个仓库到该目录
  ```sh
  cd /www/wwwroot/newsradar-project
  git clone <your-trendradar-repo> trendradar
  git clone <your-newsradar-repo> newsradar
  ```

### 3. 准备 .env

```sh
cd /www/wwwroot/newsradar-project/newsradar
cp .env.example .env
```

生产环境务必修改并强随机生成密钥:

```sh
# 生成强密钥
openssl rand -base64 48   # 用于 SECRET_KEY
openssl rand -base64 48   # 用于 CREDENTIAL_ENCRYPTION_KEY
```

编辑 `.env`:

```ini
APP_ENV=prod
DEBUG=false
SECRET_KEY=<上面生成的值1>
CREDENTIAL_ENCRYPTION_KEY=<上面生成的值2>
# 换掉数据库密码(并同步到 docker-compose.yml 的 postgres 环境)
DATABASE_URL=postgresql+psycopg://newsradar:<强密码>@db:5432/newsradar
```

> 注意:`DATABASE_URL` 里的 `@host` 在容器内必须是 `db`,不是 `localhost`
> (Compose 服务名)。`CREDENTIAL_ENCRYPTION_KEY` 一旦启用不要变,否则已存凭证无法解密。

### 4. 构建并启动(docker 服务全量)

宝塔面板左上角「终端」或 SSH 进入,在**父目录**执行:

```sh
cd /www/wwwroot/newsradar-project
docker compose -f newsradar/docker-compose.yml up --build -d
```

- `-d` 后台运行;第一次会构建镜像,耗时较长。
- 启动顺序:db → redis → api(api 命令会自动执行 `alembic upgrade head` 建表)。

检查状态与日志:

```sh
docker compose -f newsradar/docker-compose.yml ps
docker compose -f newsradar/docker-compose.yml logs -f api
```

验证接口(服务器本机):

```sh
curl http://localhost:8000/health/ready
# 期望 {"status":"ok","checks":{"db":"ok","redis":"ok"}}
```

### 5. 宝塔「网站」反向代理 + 域名绑定

1. 宝塔「网站」→「添加站点」,填你的域名(如 `news.example.com`),PHP 版选「纯静态」。
2. 进入该站点 →「反向代理」→「添加反向代理」:
   - 代理名称:`newsradar-api`
   - 目标 URL:`http://127.0.0.1:8000`
   - 发送域名:保持 `$host`
3. 到「SSL」→ 申请 Let's Encrypt 证书,并开启「强制 HTTPS」。

> 可选:若用宝塔「Docker 管理器」插件,可视化管理容器/镜像/网络,但推荐直接用
> 终端 `docker compose`,配置文件更清晰、可追溯。

### 6. 常用运维命令(在父目录执行)

```sh
# 重启 API(改代码后)
docker compose -f newsradar/docker-compose.yml restart api

# 查看所有服务日志
docker compose -f newsradar/docker-compose.yml logs --tail=100 -f

# 手动跑数据库迁移(通常 api 启动已自动执行)
docker compose -f newsradar/docker-compose.yml exec api alembic upgrade head

# 备份数据库
docker compose -f newsradar/docker-compose.yml exec db \
  pg_dump -U newsradar newsradar > backup_$(date +%F).sql

# 升级:先拉代码再重建
cd /www/wwwroot/newsradar-project
git -C trendradar pull && git -C newsradar pull
docker compose -f newsradar/docker-compose.yml up --build -d
```

### 7. 常见问题

| 现象 | 原因 / 解法 |
|---|---|
| 端口被占 | 把 docker-compose.yml 的 `8000:8000` 改成 `8001:8000` 之类 |
| `/health/ready` 显示 db/redis fail | 检查 db/redis 容器是否启动:`docker compose ps` |
| 反代 502 | 反代目标写错端口,或 api 容器未起来;先本机 `curl localhost:8000` 排障 |
| 变更密钥后旧渠道失效 | `CREDENTIAL_ENCRYPTION_KEY` 变了导致凭证无法解密;该值须持久、稳定 |

## 技术栈

FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis 7 · Arq · pydantic-settings ·
trendradar(core,以 path 依赖引入)
