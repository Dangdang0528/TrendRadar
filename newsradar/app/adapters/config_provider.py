"""TrendRadar 配置 Provider

将"用户的订阅偏好 + 全局默认"翻译成 trendradar 认识的 config dict。
trendradar 的核心模块只认 dict,不关心来源,因此我们零侵入适配。

参见 trendradar/core/loader.py::load_config() 输出的 dict 结构,这里按相同键名组装。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import get_settings


@dataclass
class UserSubscriptionSpec:
    """单条用户订阅(与未来 ORM 解耦的中间数据结构)"""

    type: str  # platform / rss / keyword / ai_interest / global_filter
    target: str  # platform_id / rss_url / 关键词组标识 / 全局过滤词
    name: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserChannelSpec:
    """单条投递渠道"""

    channel: str  # feishu / email / ...
    label: str | None
    credential: dict[str, Any]  # 已解密的明文凭证


@dataclass
class UserScheduleSpec:
    """per-user 调度配置"""

    cron_expr: str = "0 9 * * *"
    report_mode: str = "incremental"  # daily / current / incremental
    enable_ai_summary: bool = False
    ai_language: str = "zh"
    ai_max_news: int = 30
    # 投递渠道筛选:{"include": ["feishu"], "exclude": ["email"]},None/{} 表示不过滤
    channel_filter: dict[str, Any] | None = None


@dataclass
class UserCtx:
    """worker 调用流水线时的用户上下文"""

    user_id: int
    email: str
    timezone: str = "Asia/Shanghai"
    language: str = "zh"
    subscriptions: list[UserSubscriptionSpec] = field(default_factory=list)
    channels: list[UserChannelSpec] = field(default_factory=list)
    schedule: UserScheduleSpec = field(default_factory=UserScheduleSpec)


PLATFORM_CATALOG_CACHE: list[dict[str, Any]] | None = None

# 全局过滤词的"单例行"占位 target(user_subscriptions 需要唯一 target)
GLOBAL_FILTER_TARGET = "__global__"


def load_platform_catalog() -> list[dict[str, Any]]:
    """从 trendradar config/config.yaml 读取内置平台清单(带进程内缓存)

    Returns:
        [{"id", "name", "enabled"}, ...];文件缺失或解析失败时返回空列表
    """
    global PLATFORM_CATALOG_CACHE
    if PLATFORM_CATALOG_CACHE is not None:
        return PLATFORM_CATALOG_CACHE

    import yaml

    config_path = Path(get_settings().TRENDRADAR_WORK_DIR) / "config" / "config.yaml"
    sources: list[dict[str, Any]] = []
    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            sources = data.get("platforms", {}).get("sources", []) or []
    except Exception:  # noqa: BLE001 - 清单读不到时退化为空,不影响主流程
        sources = []

    catalog = [
        {"id": s["id"], "name": s.get("name", s["id"]), "enabled": s.get("enabled", True)}
        for s in sources
        if s.get("id")
    ]
    PLATFORM_CATALOG_CACHE = catalog
    return catalog


def render_word_group(cfg: dict[str, Any]) -> str:
    """把结构化的关键词组渲染成 frequency_words.txt 里的一个词组块

    语法(与 trendradar/core/frequency.py 对齐):
        [组别名]   词组第一行,给整组指定显示名
        普通词     组内"或"关系,任一命中即可
        +词        必须词,全部命中才算匹配
        !词        排除词,命中则整条新闻被排除
        @N         该组最多显示 N 条
        /pat/      正则(自动忽略大小写)
    """
    alias = str(cfg.get("alias") or "").strip()
    words = [str(w).strip() for w in (cfg.get("words") or []) if str(w).strip()]
    required = [str(w).strip() for w in (cfg.get("required") or []) if str(w).strip()]
    filters = [str(w).strip() for w in (cfg.get("filters") or []) if str(w).strip()]
    try:
        max_count = int(cfg.get("max_count") or 0)
    except (TypeError, ValueError):
        max_count = 0

    if not words and not required:
        return ""

    lines: list[str] = []
    if alias:
        lines.append(f"[{alias}]")
    lines.extend(words)
    lines.extend(f"+{w}" for w in required)
    lines.extend(f"!{w}" for w in filters)
    if max_count > 0:
        lines.append(f"@{max_count}")
    return "\n".join(lines)


def render_frequency_words(
    keyword_groups: list[dict[str, Any]],
    global_filters: list[str] | None = None,
) -> str:
    """渲染完整的 frequency_words.txt 内容

    两个区域必须都显式写出 [GLOBAL_FILTER] 与 [WORD_GROUPS]:解析器只在
    遇到区域标记时切换 current_section,缺少 [WORD_GROUPS] 会让后续词组
    被当成全局过滤词。

    两个区域都为空时,文件不产生任何词组 → trendradar 匹配所有新闻(即不过滤)。
    """
    lines: list[str] = ["[GLOBAL_FILTER]"]
    lines.extend(str(w).strip() for w in (global_filters or []) if str(w).strip())
    lines.append("")
    lines.append("[WORD_GROUPS]")

    for cfg in keyword_groups:
        block = render_word_group(cfg)
        if block:
            lines.append("")
            lines.append(block)

    return "\n".join(lines) + "\n"


def build_config_for_user(user: UserCtx) -> dict[str, Any]:
    """把 UserCtx 翻译为 trendradar 风格的 config dict

    原则:
    - 全局默认来自环境变量(全局 AI key、trendradar 工作目录等)
    - per-user 偏好(订阅平台、RSS、关键词、AI 开关)覆盖对应位置
    - 通知渠道投递不通过 trendradar config,而是通过我们自己的 dispatcher 调 senders
      (因此 NOTIFICATION_* 不在这里构造,留空避免 trendradar 自动发)
    """

    settings = get_settings()

    # 平台订阅:未指定任何平台时默认抓取全部平台
    platforms = [
        {"id": s.target, "name": s.name or s.target, "enabled": True}
        for s in user.subscriptions
        if s.type == "platform"
    ]
    if not platforms:
        platforms = [
            {"id": p["id"], "name": p["name"], "enabled": True}
            for p in load_platform_catalog()
            if p.get("enabled", True)
        ]

    # RSS 订阅
    rss_feeds = [
        {"url": s.target, "name": s.name or s.target, "enabled": True}
        for s in user.subscriptions
        if s.type == "rss"
    ]

    # 关键词:trendradar 只认 frequency_words.txt 文件,per-user 内容由
    # pipeline_runner._write_user_frequency_file + render_frequency_words 生成,
    # 无法通过 config dict 传递(故此处不构造 FREQUENCY_WORDS 键)。

    # AI 兴趣描述
    ai_interests = "\n".join(
        s.target for s in user.subscriptions if s.type == "ai_interest"
    )

    # AI 配置(全局 key)
    ai_config = {
        "MODEL": settings.AI_MODEL,
        "API_KEY": settings.AI_API_KEY or "",
        "API_BASE": settings.AI_API_BASE,
        "TIMEOUT": settings.AI_TIMEOUT,
        "MAX_TOKENS": settings.AI_MAX_TOKENS,
    }

    # AI 分析配置(per-user 开关)
    ai_analysis_config = {
        "ENABLED": user.schedule.enable_ai_summary and bool(settings.AI_API_KEY),
        "LANGUAGE": "Chinese" if user.schedule.ai_language.startswith("zh") else "English",
        "MAX_NEWS_FOR_ANALYSIS": user.schedule.ai_max_news,
        "INCLUDE_RSS": True,
        "INCLUDE_RANK_TIMELINE": False,
        "INCLUDE_STANDALONE": False,
        "PROMPT_FILE": "ai_analysis_prompt.txt",
        "MODE": "follow_report",
    }

    # 存储配置(本地 SQLite,落在 trendradar 工作目录 output/ 下)
    # 结构与 trendradar core.loader._load_storage_config 对齐,AppContext 才能识别
    work_dir = settings.TRENDRADAR_WORK_DIR
    storage_config = {
        "BACKEND": "local",  # trendradar 支持 auto / local / remote(s3)
        "LOCAL": {"DATA_DIR": f"{work_dir}/output"},
        "FORMATS": {"SQLITE": True, "TXT": False, "HTML": False},
    }

    config = {
        # 基础
        "DEBUG": settings.DEBUG,
        "TIMEZONE": user.timezone,
        "LANGUAGE": "zh" if user.language.startswith("zh") else "en",

        # 平台与 RSS
        "PLATFORMS": platforms,
        "PLATFORMS_API_URL": settings.PLATFORMS_API_URL,
        "RSS": {
            "ENABLED": bool(rss_feeds),
            "FEEDS": rss_feeds,
            "MAX_ITEMS_PER_FEED": 20,
        },

        # 筛选
        "AI_INTERESTS": ai_interests,
        "FILTER": {
            "FREQUENCY_MIN_COUNT": 1,
            "ENABLE_WORD_GROUPS": True,
            "ENABLE_AI_FILTER": False,  # MVP 暂不启用 AI 筛选
        },

        # 报告
        "REPORT_MODE": user.schedule.report_mode,
        "DISPLAY": {
            "SHOW_RANK": True,
            "SHOW_TIME_RANGE": True,
            "SHOW_COUNT": True,
        },

        # AI
        "AI": ai_config,
        "AI_ANALYSIS": ai_analysis_config,

        # 存储
        "STORAGE": storage_config,

        # 通知:这里全空,投递由我们自己的 orchestrator 接管
        "NOTIFICATION_CHANNELS": [],
        "NOTIFICATION_BATCH": False,

        # 调度:per-user 触发由 Arq + cron 控制,trendradar 内部调度不参与
        "SCHEDULE": {},
    }

    return config
