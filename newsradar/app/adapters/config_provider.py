# coding=utf-8
"""TrendRadar 配置 Provider

将"用户的订阅偏好 + 全局默认"翻译成 trendradar 认识的 config dict。
trendradar 的核心模块只认 dict,不关心来源,因此我们零侵入适配。

参见 trendradar/core/loader.py::load_config() 输出的 dict 结构,这里按相同键名组装。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import get_settings


@dataclass
class UserSubscriptionSpec:
    """单条用户订阅(与未来 ORM 解耦的中间数据结构)"""

    type: str  # platform / rss / keyword / ai_interest
    target: str  # platform_id / rss_url / 关键词文本 / ai_interest 文本
    name: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserChannelSpec:
    """单条投递渠道"""

    channel: str  # feishu / email / ...
    label: Optional[str]
    credential: Dict[str, Any]  # 已解密的明文凭证


@dataclass
class UserScheduleSpec:
    """per-user 调度配置"""

    cron_expr: str = "0 9 * * *"
    report_mode: str = "incremental"  # daily / current / incremental
    enable_ai_summary: bool = False
    ai_language: str = "zh"
    ai_max_news: int = 30


@dataclass
class UserCtx:
    """worker 调用流水线时的用户上下文"""

    user_id: int
    email: str
    timezone: str = "Asia/Shanghai"
    language: str = "zh"
    subscriptions: List[UserSubscriptionSpec] = field(default_factory=list)
    channels: List[UserChannelSpec] = field(default_factory=list)
    schedule: UserScheduleSpec = field(default_factory=UserScheduleSpec)


def build_config_for_user(user: UserCtx) -> Dict[str, Any]:
    """把 UserCtx 翻译为 trendradar 风格的 config dict

    原则:
    - 全局默认来自环境变量(全局 AI key、trendradar 工作目录等)
    - per-user 偏好(订阅平台、RSS、关键词、AI 开关)覆盖对应位置
    - 通知渠道投递不通过 trendradar config,而是通过我们自己的 dispatcher 调 senders
      (因此 NOTIFICATION_* 不在这里构造,留空避免 trendradar 自动发)
    """

    settings = get_settings()

    # 平台订阅
    platforms = [
        {"id": s.target, "name": s.name or s.target, "enabled": True}
        for s in user.subscriptions
        if s.type == "platform"
    ]
    if not platforms:
        # 没订阅平台时,给一个空列表,避免 trendradar 跑全部平台
        platforms = []

    # RSS 订阅
    rss_feeds = [
        {"url": s.target, "name": s.name or s.target, "enabled": True}
        for s in user.subscriptions
        if s.type == "rss"
    ]

    # 关键词(复用 trendradar 的 frequency_words 概念)
    frequency_words = "\n".join(
        s.target for s in user.subscriptions if s.type == "keyword"
    )

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

    # 存储配置(本地 SQLite,在 trendradar 工作目录下的 output/news/)
    work_dir = settings.TRENDRADAR_WORK_DIR
    storage_config = {
        "TYPE": "local",  # trendradar 支持 local / s3
        "LOCAL_PATH": f"{work_dir}/output/news",
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
        "FREQUENCY_WORDS": frequency_words,
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
