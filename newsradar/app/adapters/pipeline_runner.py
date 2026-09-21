# coding=utf-8
"""Pipeline Runner

调用 trendradar 核心流水线,生成报告(暂不投递)。
阶段 0 的最简实现:验证适配层能调通 trendradar。

后续阶段:
- 阶段 1:加载真实 UserCtx(从 DB)
- 阶段 2:投递到飞书 / 邮箱;并接入 AI 总结(若用户开启)
"""

import os
from typing import Any, Dict, Optional

from app.adapters.config_provider import UserCtx, build_config_for_user
from app.config import get_settings


def run_pipeline_once_for_test() -> Dict[str, Any]:
    """阶段 0 验证用:硬编码一个 UserCtx,调用 trendradar 跑一次

    用法:
      docker compose run --rm api python -c \\
        "from app.adapters.pipeline_runner import run_pipeline_once_for_test; \\
         run_pipeline_once_for_test()"

    Returns:
        运行结果摘要
    """

    # 构造测试用户(暂不查 DB)
    user = UserCtx(
        user_id=0,
        email="test@local",
        timezone="Asia/Shanghai",
        language="zh",
        subscriptions=[],  # 空 → trendradar 不抓平台
        channels=[],
        schedule=type("S", (), {
            "cron_expr": "0 9 * * *",
            "report_mode": "incremental",
            "enable_ai_summary": False,
            "ai_language": "zh",
            "ai_max_news": 30,
        })(),
    )

    # 切换工作目录到 trendradar 期望的位置(config/、output/ 在这里)
    settings = get_settings()
    os.chdir(settings.TRENDRADAR_WORK_DIR)

    # 构造 trendradar config
    config = build_config_for_user(user)

    try:
        # 仅验证 import 与 config 组装能跑通,不真正调抓取(防止外部网络问题)
        from trendradar.context import AppContext

        ctx = AppContext(config)
        return {
            "ok": True,
            "config_keys": sorted(config.keys()),
            "ctx_class": ctx.__class__.__name__,
            "user_email": user.email,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def run_pipeline_for_user(user_id: int) -> Dict[str, Any]:
    """阶段 2 实现:按 user_id 加载配置、跑流水线、投递

    TODO(阶段 1/2):
    - 从 DB 加载 user / subscriptions / channels / schedule
    - 解密 channel credential
    - 构造 UserCtx
    - 调用 trendradar 抓取 + 筛选 + 报告生成
    - (可选)若用户开启 AI 总结:调用 AIAnalyzer.analyze()
    - 调 senders 投递飞书/邮箱
    - 写 notification_logs / ai_usage
    """
    raise NotImplementedError("run_pipeline_for_user 在阶段 2 实现")
