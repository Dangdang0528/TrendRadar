"""正文级 AI 深度总结引擎(阶段 2)

与 trendradar 的"标题级 AI 分析"互补:本引擎先通过 ContentExtractor 抓取
Top-N 热搜链接的【正文】,再交由 AI 基于正文事实做深度解读,产出结构化结果。

设计原则:
- 不重复造轮子:正文抓取复用 app.adapters.content_extractor;AI 调用复用
  trendradar 的 AIClient(项目统一客户端),上游零改动。
- 仅对 Top-N 抓正文,控制成本与延迟;抓不到正文的条目降级为"仅标题",不编造。
- 单条失败隔离:一条抓取/解析失败不影响整体。
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.adapters.content_extractor import ContentExtractor
from app.config import get_settings

settings = get_settings()

_PROMPT_FILE = Path(__file__).parent / "prompts" / "deep_summary_prompt.txt"


@dataclass
class DeepSummaryItem:
    """参与深度总结的单条新闻"""

    title: str
    url: str = ""
    source: str = ""
    content: str | None = None  # 抓取到的正文;None 表示未获取


@dataclass
class DeepSummaryResult:
    """正文级深度总结结果"""

    executive_summary: str = ""
    item_analyses: list[dict] = field(default_factory=list)
    cross_insights: str = ""
    outlook: str = ""

    success: bool = False
    skipped: bool = False  # 无正文可分析(非失败)
    error: str = ""

    total_candidates: int = 0  # 候选新闻总条数
    analyzed: int = 0          # 实际获取到正文并参与分析的条数
    raw_response: str = ""


def _load_prompt() -> tuple[str, str]:
    """加载 [system]/[user] 格式的提示词模板"""
    if not _PROMPT_FILE.exists():
        return "", ""
    content = _PROMPT_FILE.read_text(encoding="utf-8")
    if "[system]" not in content or "[user]" not in content:
        return "", content.strip()
    system_part, user_part = content.split("[user]", 1)
    system_prompt = system_part.split("[system]", 1)[1].strip()
    return system_prompt, user_part.strip()


def collect_candidates(
    stats: list[dict],
    rss_stats: list[dict] | None = None,
    max_news: int = 30,
) -> list[DeepSummaryItem]:
    """从热榜/RSS 统计中按重要性顺序收集候选条目,按 url(或标题)去重,截取 Top-N。

    stats 内每条词组已按权重排序,因此顺序遍历即近似按热度取前 N。
    """
    candidates: list[DeepSummaryItem] = []
    seen: set[str] = set()

    for group in list(stats or []) + list(rss_stats or []):
        if len(candidates) >= max_news:
            break
        for t in group.get("titles", []):
            if len(candidates) >= max_news:
                break
            title = str(t.get("title", "")).strip()
            if not title:
                continue
            url = str(t.get("url") or t.get("mobile_url") or "").strip()
            key = url or title
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                DeepSummaryItem(
                    title=title,
                    url=url,
                    source=str(t.get("source_name") or t.get("source") or ""),
                )
            )
    return candidates


def _format_news_content(items: list[DeepSummaryItem]) -> str:
    """把候选条目格式化为注入 prompt 的正文块"""
    blocks: list[str] = []
    for i, it in enumerate(items, 1):
        head = f"### {i}. {it.title}"
        if it.source:
            head += f" [{it.source}]"
        lines = [head]
        if it.url:
            lines.append(f"链接: {it.url}")
        if it.content:
            lines.append("正文:")
            lines.append(it.content)
        else:
            lines.append("正文: (未获取到正文,仅有标题)")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _parse_json_response(response: str) -> dict:
    """从 AI 响应中提取 JSON 对象(容忍 markdown 代码块)"""
    if not response or not response.strip():
        return {}
    json_str = response.strip()
    if "```json" in json_str:
        json_str = json_str.split("```json", 1)[1]
        json_str = json_str.split("```", 1)[0]
    elif "```" in json_str:
        json_str = json_str.split("```", 1)[1].split("```", 1)[0]
    json_str = json_str.strip()
    try:
        data = json.loads(json_str)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import repair_json

        repaired = repair_json(json_str, return_objects=True)
        return repaired if isinstance(repaired, dict) else {}
    except Exception:  # noqa: BLE001 - 修复失败时回退为空,由上层判定
        return {}


async def run_content_deep_summary(
    *,
    stats: list[dict],
    extractor: ContentExtractor,
    rss_stats: list[dict] | None = None,
    max_news: int = 30,
    language: str = "zh",
    get_time_func: Callable[[], Any],
    ai_config: dict | None = None,
) -> DeepSummaryResult:
    """执行正文级 AI 深度总结的完整流程。

    Args:
        stats: 热榜统计(含 url)
        extractor: 正文抓取器
        rss_stats: RSS 统计(可选)
        max_news: 参与分析的 Top-N 上限
        language: 输出语言
        get_time_func: 取当前时间的函数
        ai_config: trendradar 风格 AI 配置(含 MODEL/API_KEY/...);缺省用全局设置
    """
    candidates = collect_candidates(stats, rss_stats, max_news=max_news)
    result = DeepSummaryResult(total_candidates=len(candidates))
    if not candidates:
        result.skipped = True
        result.error = "无候选新闻,跳过深度总结"
        return result

    # 1. 抓取正文(仅对有 url 的条目)
    urls = [c.url for c in candidates if c.url]
    contents = await extractor.get_many(urls) if urls else {}
    for c in candidates:
        if c.url:
            c.content = contents.get(c.url)
    result.analyzed = sum(1 for c in candidates if c.content)

    if result.analyzed == 0:
        result.skipped = True
        result.error = "未获取到任何正文,跳过深度总结"
        return result

    # 2. 构建提示词
    system_prompt, user_template = _load_prompt()
    if not user_template:
        result.error = "深度总结提示词模板缺失"
        return result

    language_name = "中文" if str(language).startswith("zh") else "English"
    user_prompt = (
        user_template.replace("{current_time}", str(get_time_func()))
        .replace("{news_count}", str(result.analyzed))
        .replace("{total_count}", str(result.total_candidates))
        .replace("{news_content}", _format_news_content(candidates))
        .replace("{language}", language_name)
    )

    # 3. 调用 AI(复用 trendradar 统一客户端)
    try:
        from trendradar.ai.client import AIClient

        cfg = ai_config or _default_ai_config()
        client = AIClient(cfg)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        response = client.chat(messages)
    except Exception as e:  # noqa: BLE001 - AI 调用失败统一转错误结果
        result.error = f"AI 调用失败 ({type(e).__name__}): {e}"
        return result

    result.raw_response = response

    # 4. 解析结构化结果
    data = _parse_json_response(response)
    if not data:
        result.error = "AI 响应解析失败"
        return result

    result.executive_summary = str(data.get("executive_summary", "") or "")
    result.cross_insights = str(data.get("cross_insights", "") or "")
    result.outlook = str(data.get("outlook", "") or "")
    analyses = data.get("item_analyses", [])
    if isinstance(analyses, list):
        result.item_analyses = [a for a in analyses if isinstance(a, dict)]
    result.success = True
    return result


def _default_ai_config() -> dict:
    """全局默认 AI 配置(trendradar 风格键名)"""
    return {
        "MODEL": settings.AI_MODEL,
        "API_KEY": settings.AI_API_KEY or "",
        "API_BASE": settings.AI_API_BASE,
        "TIMEOUT": settings.AI_TIMEOUT,
        "MAX_TOKENS": settings.AI_MAX_TOKENS,
    }