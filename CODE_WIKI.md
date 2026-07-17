# TrendRadar Code Wiki

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 项目架构](#2-项目架构)
- [3. 目录结构](#3-目录结构)
- [4. 核心模块详解](#4-核心模块详解)
  - [4.1 主入口模块](#41-主入口模块)
  - [4.2 应用上下文](#42-应用上下文)
  - [4.3 配置管理](#43-配置管理)
  - [4.4 统计分析](#44-统计分析)
  - [4.5 调度系统](#45-调度系统)
  - [4.6 AI 分析模块](#46-ai-分析模块)
  - [4.7 AI 筛选流水线](#47-ai-筛选流水线)
  - [4.8 存储管理](#48-存储管理)
  - [4.9 通知调度](#49-通知调度)
  - [4.10 数据爬取](#410-数据爬取)
  - [4.11 报告生成](#411-报告生成)
- [5. 关键类与函数](#5-关键类与函数)
- [6. 数据流与依赖关系](#6-数据流与依赖关系)
- [7. 运行方式](#7-运行方式)
- [8. 配置说明](#8-配置说明)
- [9. 扩展能力（MCP Server）](#9-扩展能力mcp-server)

---

## 1. 项目概述

**TrendRadar** 是一个热点新闻聚合与分析工具，主要功能包括：

- **多平台数据爬取**：从多个新闻平台抓取热点榜单数据
- **RSS 订阅支持**：支持 RSS 源的数据抓取和分析
- **关键词/AI 智能筛选**：基于关键词匹配或 AI 智能分类筛选新闻
- **AI 深度分析**：调用大语言模型对热点新闻进行深度分析，生成多维度洞察报告
- **多渠道通知推送**：支持飞书、钉钉、企业微信、Telegram 等多种通知渠道
- **HTML 报告生成**：自动生成美观的 HTML 报告
- **时间线调度**：灵活的时间段调度系统，支持差异化配置
- **数据持久化**：支持本地 SQLite 和远程 S3 存储

---

## 2. 项目架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      TrendRadar 主流程                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  数据爬取    │───▶│   数据存储    │───▶│   统计分析      │   │
│  │  Crawler    │    │   Storage    │    │   Analyzer      │   │
│  │  (热榜+RSS)  │    │              │    │   (关键词/AI)   │   │
│  └─────────────┘    └──────────────┘    └────────┬─────────┘   │
│                                                    │             │
│                                                    ▼             │
│                                          ┌──────────────────┐   │
│                                          │    AI 分析       │   │
│                                          │   AIAnalyzer     │   │
│                                          └────────┬─────────┘   │
│                                                    │             │
│                      ┌─────────────────────────────┘             │
│                      │                                           │
│          ┌───────────┴───────────┐                               │
│          ▼                       ▼                               │
│    ┌───────────┐         ┌───────────────┐                       │
│    │ HTML报告  │         │ 通知推送       │                       │
│    │ Generator │         │ Dispatcher    │                       │
│    └───────────┘         │ (多渠道)       │                       │
│                          └───────────────┘                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

```
/workspace/
├── trendradar/                    # 主应用模块
│   ├── __main__.py                # 应用入口（NewsAnalyzer）
│   ├── context.py                 # 应用上下文（AppContext）
│   ├── ai/                        # AI 相关模块
│   │   ├── analyzer.py            # AI 分析器（AIAnalyzer）
│   │   ├── client.py              # AI 客户端（基于 LiteLLM）
│   │   ├── filter.py              # AI 筛选器
│   │   ├── filter_pipeline.py     # AI 筛选流水线
│   │   ├── formatter.py           # AI 格式化工具
│   │   ├── prompt_loader.py       # 提示词加载器
│   │   └── translator.py          # AI 翻译器
│   ├── core/                      # 核心功能模块
│   │   ├── analyzer.py            # 统计分析器
│   │   ├── config.py              # 配置解析工具
│   │   ├── cdn.py                 # CDN 工具
│   │   ├── data.py                # 数据处理工具
│   │   ├── frequency.py           # 频率词匹配
│   │   ├── loader.py              # 配置加载器
│   │   └── scheduler.py           # 时间线调度器
│   ├── crawler/                   # 爬虫模块
│   │   ├── fetcher.py             # 数据获取器
│   │   └── rss/                   # RSS 爬虫子模块
│   │       ├── fetcher.py         # RSS 获取器
│   │       └── parser.py          # RSS 解析器
│   ├── notification/              # 通知模块
│   │   ├── batch.py               # 批量发送工具
│   │   ├── dispatcher.py          # 通知调度器
│   │   ├── formatters.py          # 通知格式器
│   │   ├── renderer.py            # 内容渲染器
│   │   ├── senders.py             # 各渠道发送器
│   │   └── splitter.py            # 内容分片工具
│   ├── report/                    # 报告模块
│   │   ├── formatter.py           # 报告格式化
│   │   ├── generator.py           # 报告生成器
│   │   ├── helpers.py             # 辅助函数
│   │   ├── html.py                # HTML 渲染
│   │   └── rss_html.py            # RSS HTML 渲染
│   ├── storage/                   # 存储模块
│   │   ├── base.py                # 存储抽象基类
│   │   ├── local.py               # 本地存储后端
│   │   ├── manager.py             # 存储管理器
│   │   ├── remote.py              # 远程存储后端（S3）
│   │   ├── sqlite_mixin.py        # SQLite 混入类
│   │   └── *.sql                  # 数据库 schema
│   ├── commands/                  # CLI 命令
│   │   ├── doctor.py              # 健康检查
│   │   ├── status.py              # 状态查询
│   │   ├── test_notification.py   # 通知测试
│   │   └── version.py             # 版本管理
│   └── utils/                     # 工具函数
│       ├── time.py                # 时间工具
│       └── url.py                 # URL 工具
├── mcp_server/                    # FastMCP 服务器
│   ├── server.py                  # MCP 服务器入口
│   ├── services/                  # 服务层
│   ├── tools/                     # MCP 工具定义
│   └── utils/                     # MCP 工具函数
├── config/                        # 配置文件
│   ├── config.yaml                # 主配置
│   ├── timeline.yaml              # 时间线配置
│   ├── ai_interests.txt           # AI 兴趣描述
│   ├── ai_analysis_prompt.txt     # AI 分析提示词
│   └── frequency_words.txt        # 频率词配置
├── docker/                        # Docker 配置
├── output/                        # 输出目录
└── docs/                          # 文档目录
```

---

## 4. 核心模块详解

### 4.1 主入口模块

**文件**: [trendradar/__main__.py](file:///workspace/trendradar/__main__.py)

**核心类**: `NewsAnalyzer`

**职责**: 应用主入口，负责协调整个数据抓取、分析、报告生成和通知推送流程。

**关键方法**:

| 方法名 | 功能描述 |
|--------|----------|
| `__init__` | 初始化分析器，加载配置，创建上下文 |
| `_run_analysis_pipeline` | 统一分析流水线：数据处理 → 统计计算 → AI分析 → HTML生成 |
| `_send_notification_if_needed` | 统一通知发送逻辑 |
| `_crawl_data` | 执行热榜数据爬取 |
| `_crawl_rss_data` | 执行 RSS 数据爬取 |
| `_run_ai_analysis` | 执行 AI 分析 |

**三种运行模式**:

| 模式 | 描述 |
|------|------|
| `incremental` | 增量模式，只关注新增新闻 |
| `current` | 当前榜单模式，展示当前在榜新闻 |
| `daily` | 全天汇总模式，展示所有匹配新闻 |

---

### 4.2 应用上下文

**文件**: [trendradar/context.py](file:///workspace/trendradar/context.py)

**核心类**: `AppContext`

**职责**: 封装所有依赖配置的操作，提供统一接口，消除全局状态依赖。

**核心功能**:

- **配置访问**: 提供配置的属性访问（时区、平台列表、RSS 配置等）
- **时间操作**: 获取当前时间、格式化日期时间
- **存储操作**: 获取存储管理器
- **数据处理**: 读取当天标题、检测新增标题
- **频率词处理**: 加载频率词配置、匹配词组规则
- **统计分析**: 统计词频
- **报告生成**: 准备报告数据、生成 HTML
- **通知调度**: 创建通知调度器
- **AI 筛选**: 执行 AI 智能筛选

---

### 4.3 配置管理

**文件**: [trendradar/core/config.py](file:///workspace/trendradar/core/config.py)

**核心函数**:

| 函数名 | 功能描述 |
|--------|----------|
| `parse_multi_account_config` | 解析多账号配置（支持 `;` 分隔） |
| `validate_paired_configs` | 验证配对配置数量一致性 |
| `limit_accounts` | 限制账号数量 |
| `get_account_at_index` | 安全获取指定索引的账号 |

**文件**: [trendradar/core/loader.py](file:///workspace/trendradar/core/loader.py)

**核心函数**: `load_config()` - 加载并合并 YAML 配置文件和环境变量

---

### 4.4 统计分析

**文件**: [trendradar/core/analyzer.py](file:///workspace/trendradar/core/analyzer.py)

**核心函数**:

| 函数名 | 功能描述 |
|--------|----------|
| `calculate_news_weight` | 计算新闻权重（排名 + 频次 + 热度） |
| `count_word_frequency` | 统计词频，支持必须词、频率词、过滤词 |
| `count_rss_frequency` | 按关键词分组统计 RSS 条目 |
| `convert_keyword_stats_to_platform_stats` | 将关键词统计转换为平台统计 |

**权重计算公式**:

```
total_weight = rank_weight * RANK_WEIGHT + frequency_weight * FREQUENCY_WEIGHT + hotness_weight * HOTNESS_WEIGHT
```

---

### 4.5 调度系统

**文件**: [trendradar/core/scheduler.py](file:///workspace/trendradar/core/scheduler.py)

**核心类**: `Scheduler`, `ResolvedSchedule`

**职责**: 基于时间线配置解析当前应执行的行为（采集/分析/推送）。

**配置模型**:

```yaml
timeline:
  default:            # 默认配置
  periods:            # 时间段定义（如 "morning", "evening"）
  day_plans:          # 日计划（如 "workday", "weekend"）
  week_map:           # 星期到日计划的映射
```

**关键方法**:

| 方法名 | 功能描述 |
|--------|----------|
| `resolve()` | 解析当前时间对应的调度配置 |
| `already_executed()` | 检查指定 action 是否已执行（去重） |
| `record_execution()` | 记录 action 执行 |

---

### 4.6 AI 分析模块

**文件**: [trendradar/ai/analyzer.py](file:///workspace/trendradar/ai/analyzer.py)

**核心类**: `AIAnalyzer`, `AIAnalysisResult`

**职责**: 调用 AI 大模型对热点新闻进行深度分析，生成结构化洞察报告。

**AI 分析输出（5 核心板块）**:

| 板块 | 字段名 | 描述 |
|------|--------|------|
| 核心热点与舆情态势 | `core_trends` | 当前核心热点及其舆情走向 |
| 舆论风向与争议 | `sentiment_controversy` | 舆论倾向和争议点分析 |
| 异动与弱信号 | `signals` | 异常变化和早期信号 |
| RSS 深度洞察 | `rss_insights` | RSS 源的深度分析 |
| 研判与策略建议 | `outlook_strategy` | 趋势研判和策略建议 |

**关键方法**:

| 方法名 | 功能描述 |
|--------|----------|
| `analyze()` | 执行 AI 分析 |
| `_prepare_news_content()` | 准备新闻内容供 AI 分析 |
| `_parse_response()` | 解析 AI 响应（支持 JSON 修复） |
| `_retry_fix_json()` | JSON 解析失败时重试修复 |

---

### 4.7 AI 筛选流水线

**文件**: [trendradar/ai/filter_pipeline.py](file:///workspace/trendradar/ai/filter_pipeline.py)

**核心类**: `AIFilterPipeline`

**职责**: 编排标签提取、批量分类、结果存储的完整 AI 筛选流程。

**执行流程**:

1. 读取兴趣描述文件，计算 hash
2. 对比数据库 hash，决定是否重新提取标签
3. 收集待分类新闻（去重）
4. 按 batch_size 分组调用 AI 分类
5. 保存结果
6. 查询 active 结果，按标签分组返回

**关键方法**:

| 方法名 | 功能描述 |
|--------|----------|
| `run()` | 执行完整筛选流程 |
| `convert_to_report_data()` | 将 AI 筛选结果转换为报告数据格式 |
| `_handle_tag_update()` | 处理标签更新（增量/全量） |

---

### 4.8 存储管理

**文件**: [trendradar/storage/manager.py](file:///workspace/trendradar/storage/manager.py)

**核心类**: `StorageManager`

**职责**: 统一管理存储后端，支持本地 SQLite 和远程 S3 存储。

**存储后端**:

| 后端类型 | 描述 | 适用场景 |
|----------|------|----------|
| `local` | 本地 SQLite 存储 | 本地开发、Docker |
| `remote` | S3 兼容存储 | GitHub Actions |
| `auto` | 自动选择 | 默认，根据环境自动选择 |

**关键方法**:

| 方法名 | 功能描述 |
|--------|----------|
| `get_backend()` | 获取存储后端实例 |
| `save_news_data()` | 保存新闻数据 |
| `save_rss_data()` | 保存 RSS 数据 |
| `detect_new_titles()` | 检测新增标题 |
| `cleanup_old_data()` | 清理过期数据 |
| `pull_from_remote()` | 从远程拉取数据 |

---

### 4.9 通知调度

**文件**: [trendradar/notification/dispatcher.py](file:///workspace/trendradar/notification/dispatcher.py)

**核心类**: `NotificationDispatcher`

**职责**: 统一的多账号通知调度器，支持多种通知渠道。

**支持的通知渠道**:

| 渠道 | 配置项 | 说明 |
|------|--------|------|
| 飞书 | `FEISHU_WEBHOOK_URL` | 支持多账号 |
| 钉钉 | `DINGTALK_WEBHOOK_URL` | 支持多账号 |
| 企业微信 | `WEWORK_WEBHOOK_URL` | 支持多账号 |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 需配对验证 |
| ntfy | `NTFY_SERVER_URL`, `NTFY_TOPIC` | 需配对验证 |
| Bark | `BARK_URL` | 支持多账号 |
| Slack | `SLACK_WEBHOOK_URL` | 支持多账号 |
| 通用 Webhook | `GENERIC_WEBHOOK_URL` | 支持自定义模板 |
| 邮件 | `EMAIL_FROM`, `EMAIL_PASSWORD`, `EMAIL_TO` | 支持多收件人 |

**关键方法**:

| 方法名 | 功能描述 |
|--------|----------|
| `dispatch_all()` | 分发通知到所有已配置渠道 |
| `translate_content()` | 翻译推送内容（AI 翻译） |
| `_send_to_multi_accounts()` | 通用多账号发送逻辑 |

---

### 4.10 数据爬取

**文件**: [trendradar/crawler/fetcher.py](file:///workspace/trendradar/crawler/fetcher.py)

**核心类**: `DataFetcher`

**职责**: 从 NewsNow API 抓取新闻数据，支持重试机制和域名安全校验。

**关键方法**:

| 方法名 | 功能描述 |
|--------|----------|
| `fetch_data()` | 获取单个平台数据，支持重试 |
| `crawl_websites()` | 批量爬取多个平台数据 |
| `_check_domain_safety()` | 域名安全校验 |

**安全特性**:
- HTTPS 强制校验
- 域名白名单校验
- 随机请求间隔（防封禁）

---

### 4.11 报告生成

**文件**: [trendradar/report/generator.py](file:///workspace/trendradar/report/generator.py)

**核心函数**:

| 函数名 | 功能描述 |
|--------|----------|
| `prepare_report_data()` | 准备报告数据（过滤、格式化） |
| `generate_html_report()` | 生成 HTML 报告（快照 + 最新版 + 入口） |

**HTML 输出路径**:

| 路径 | 用途 |
|------|------|
| `output/html/日期/时间.html` | 时间戳快照（历史记录） |
| `output/html/latest/{mode}.html` | 最新报告 |
| `output/index.html` | Docker Volume 入口 |
| `index.html` | GitHub Pages 入口 |

---

## 5. 关键类与函数

### 5.1 核心类速查

| 类名 | 所属模块 | 核心职责 |
|------|----------|----------|
| `NewsAnalyzer` | `trendradar/__main__.py` | 主分析器，协调整个流程 |
| `AppContext` | `trendradar/context.py` | 应用上下文，统一接口 |
| `Scheduler` | `trendradar/core/scheduler.py` | 时间线调度器 |
| `ResolvedSchedule` | `trendradar/core/scheduler.py` | 调度解析结果 |
| `AIAnalyzer` | `trendradar/ai/analyzer.py` | AI 分析器 |
| `AIAnalysisResult` | `trendradar/ai/analyzer.py` | AI 分析结果 |
| `AIFilterPipeline` | `trendradar/ai/filter_pipeline.py` | AI 筛选流水线 |
| `StorageManager` | `trendradar/storage/manager.py` | 存储管理器 |
| `NotificationDispatcher` | `trendradar/notification/dispatcher.py` | 通知调度器 |
| `DataFetcher` | `trendradar/crawler/fetcher.py` | 数据获取器 |

### 5.2 关键函数速查

| 函数名 | 所属模块 | 功能描述 |
|--------|----------|----------|
| `load_config()` | `trendradar/core/loader.py` | 加载配置 |
| `count_word_frequency()` | `trendradar/core/analyzer.py` | 统计词频 |
| `calculate_news_weight()` | `trendradar/core/analyzer.py` | 计算新闻权重 |
| `prepare_report_data()` | `trendradar/report/generator.py` | 准备报告数据 |
| `generate_html_report()` | `trendradar/report/generator.py` | 生成 HTML 报告 |
| `parse_multi_account_config()` | `trendradar/core/config.py` | 解析多账号配置 |

---

## 6. 数据流与依赖关系

### 6.1 主流程数据流

```
配置加载 → NewsAnalyzer 初始化 → AppContext 创建
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   数据爬取(Crawler)           存储管理(Storage)            调度器(Scheduler)
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    ▼
                           统计分析(Analyzer)
                                    │
                          ┌────────┴────────┐
                          ▼                 ▼
                     AI 分析          HTML 生成
                  (AIAnalyzer)        (Generator)
                          │                 │
                          └────────┬────────┘
                                   ▼
                           通知推送(Dispatcher)
```

### 6.2 模块依赖关系

```
trendradar/__main__.py
    ├── trendradar/context.py
    │       ├── trendradar/core/loader.py
    │       ├── trendradar/core/analyzer.py
    │       ├── trendradar/core/scheduler.py
    │       ├── trendradar/report/generator.py
    │       ├── trendradar/notification/dispatcher.py
    │       ├── trendradar/ai/analyzer.py
    │       ├── trendradar/ai/filter_pipeline.py
    │       └── trendradar/storage/manager.py
    ├── trendradar/crawler/fetcher.py
    └── trendradar/storage/manager.py

trendradar/ai/analyzer.py
    ├── trendradar/ai/client.py
    │       └── litellm
    └── trendradar/ai/prompt_loader.py

trendradar/notification/dispatcher.py
    ├── trendradar/core/config.py
    ├── trendradar/notification/senders.py
    └── trendradar/ai/translator.py
```

---

## 7. 运行方式

### 7.1 安装依赖

```bash
pip install -e .
# 或使用 uv（推荐）
uv pip install -e .
```

### 7.2 运行主程序

```bash
# 方式1：作为模块运行
python -m trendradar

# 方式2：使用 CLI 命令
trendradar

# 方式3：Docker 运行
cd docker
docker-compose up -d
```

### 7.3 CLI 命令

```bash
# 版本信息
trendradar --version

# 健康检查
trendradar doctor

# 状态查询
trendradar status

# 测试通知
trendradar test-notification

# 运行 MCP 服务器
trendradar-mcp
```

### 7.4 GitHub Actions 运行

项目包含 `.github/workflows/crawler.yml`，配置后可自动定时运行。

---

## 8. 配置说明

### 8.1 配置文件层次

```
config/config.yaml        # 主配置（必选）
config/timeline.yaml      # 时间线配置（可选）
config/ai_interests.txt   # AI 兴趣描述（AI 筛选模式必选）
config/frequency_words.txt # 频率词配置（关键词模式必选）
config/ai_analysis_prompt.txt # AI 分析提示词（可选）
```

### 8.2 环境变量覆盖

配置项可通过环境变量覆盖，格式为 `CONFIG_<KEY>`：

| 环境变量 | 对应配置项 |
|----------|------------|
| `CONFIG_ENABLE_CRAWLER` | `ENABLE_CRAWLER` |
| `CONFIG_ENABLE_NOTIFICATION` | `ENABLE_NOTIFICATION` |
| `CONFIG_FEISHU_WEBHOOK_URL` | `FEISHU_WEBHOOK_URL` |
| `CONFIG_AI_API_KEY` | `AI.API_KEY` |
| `CONFIG_REPORT_MODE` | `REPORT_MODE` |

### 8.3 核心配置项

```yaml
# 基本配置
ENABLED_CRAWLER: true              # 是否启用爬虫
ENABLED_NOTIFICATION: true         # 是否启用通知
REPORT_MODE: "current"             # 报告模式: daily/current/incremental
TIMEZONE: "Asia/Shanghai"          # 时区

# AI 配置
AI:
  MODEL: "openai/gpt-4"            # 模型名称
  API_KEY: ""                      # API Key
  API_BASE: ""                     # 自定义 API 端点

# 通知渠道
FEISHU_WEBHOOK_URL: ""             # 飞书 Webhook
DINGTALK_WEBHOOK_URL: ""           # 钉钉 Webhook
TELEGRAM_BOT_TOKEN: ""             # Telegram Bot Token
TELEGRAM_CHAT_ID: ""               # Telegram Chat ID

# 存储配置
STORAGE:
  BACKEND: "auto"                  # 存储后端: local/remote/auto
  LOCAL:
    DATA_DIR: "output"             # 本地数据目录
    RETENTION_DAYS: 7              # 数据保留天数
  REMOTE:
    BUCKET_NAME: ""                # S3 Bucket 名称
    ACCESS_KEY_ID: ""              # S3 Access Key
    SECRET_ACCESS_KEY: ""          # S3 Secret Key
    ENDPOINT_URL: ""               # S3 Endpoint

# 调度配置
SCHEDULE:
  enabled: true                    # 是否启用调度
  preset: "always_on"              # 预设模板
```

---

## 9. 扩展能力（MCP Server）

### 9.1 概述

项目提供 FastMCP 2.0 服务器，可作为 AI Agent 的工具扩展，提供数据查询、分析、文章阅读和通知能力。

### 9.2 启动方式

```bash
trendradar-mcp
```

### 9.3 工具列表

| 工具名称 | 所属文件 | 功能描述 |
|----------|----------|----------|
| `query_news` | `mcp_server/tools/data_query.py` | 查询新闻数据 |
| `get_analytics` | `mcp_server/tools/analytics.py` | 获取统计分析 |
| `read_article` | `mcp_server/tools/article_reader.py` | 阅读文章内容 |
| `send_notification` | `mcp_server/tools/notification.py` | 发送通知 |
| `search_news` | `mcp_server/tools/search_tools.py` | 搜索新闻 |
| `sync_storage` | `mcp_server/tools/storage_sync.py` | 同步存储数据 |
| `manage_config` | `mcp_server/tools/config_mgmt.py` | 管理配置 |
| `system_info` | `mcp_server/tools/system.py` | 系统信息 |

### 9.4 MCP Server 架构

```
mcp_server/server.py          # 服务器入口
    ├── tools/                # 工具定义
    │   ├── data_query.py     # 数据查询工具
    │   ├── analytics.py      # 分析工具
    │   ├── article_reader.py # 文章阅读工具
    │   └── ...
    ├── services/             # 服务层
    │   ├── data_service.py   # 数据服务
    │   ├── cache_service.py  # 缓存服务
    │   └── parser_service.py # 解析服务
    └── utils/                # 工具函数
        ├── date_parser.py    # 日期解析
        ├── validators.py     # 参数验证
        └── errors.py         # 错误处理
```

---

## 附录：依赖列表

| 依赖 | 版本 | 用途 |
|------|------|------|
| `requests` | 2.33.0 | HTTP 请求 |
| `PyYAML` | 6.0.3 | YAML 解析 |
| `pytz` | 2026.1 | 时区处理 |
| `fastmcp` | 2.12.5 | MCP 服务器框架 |
| `websockets` | 13.1 | WebSocket 支持 |
| `feedparser` | 6.0.12 | RSS 解析 |
| `boto3` | 1.42.76 | S3 存储 |
| `litellm` | 1.82.6 | AI 模型统一接口 |
| `json-repair` | 0.58.6 | JSON 修复 |
| `tenacity` | 8.5.0 | 重试机制 |

---

**版本**: TrendRadar v6.10.0
**生成时间**: 2025-12-27