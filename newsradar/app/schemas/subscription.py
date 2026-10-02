# coding=utf-8
"""Pydantic schemas:订阅

订阅类型:
    platform      平台热榜,target = platform_id
    rss           RSS 源,target = url
    keyword       关键词组,config 见 KeywordGroupConfig
    ai_interest   AI 兴趣描述,target = 自然语言
    global_filter 全局过滤词,单例行,config = {"words": [...]}
"""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

SUB_TYPES = ("platform", "rss", "keyword", "ai_interest", "global_filter")

# trendradar 频率词解析器识别的区域标记;词组别名不能与它们同名,
# 否则会把整个词组变成区域切换指令
RESERVED_SECTION_NAMES = ("GLOBAL_FILTER", "WORD_GROUPS")

# 行首在该集合内的字符在 frequency_words.txt 里有语法含义(必须词/排除词/条数/词组)
_SYNTAX_PREFIXES = "+!@["


class InvalidSubscriptionConfig(ValueError):
    """订阅 config 结构非法(对 API 而言是 422,不是数据冲突)"""


def _validate_word(raw: Any, *, field: str, allow_regex: bool = True) -> str:
    """校验单个关键词/过滤词能否安全写进 frequency_words.txt 的一行"""
    word = str(raw).strip()
    if not word:
        raise InvalidSubscriptionConfig(f"{field} 不能为空")
    if "\n" in word or "\r" in word:
        raise InvalidSubscriptionConfig(f"{field} 不能包含换行:{word!r}")

    head = word[0]
    if head == "#":
        raise InvalidSubscriptionConfig(
            f"{field} 不能以 # 开头(会被当作注释丢弃):{word!r}"
        )
    if head in _SYNTAX_PREFIXES:
        raise InvalidSubscriptionConfig(
            f"{field} 不能以 {head} 开头(该前缀在频率词语法中有特殊含义):{word!r}"
        )

    if head == "/":
        if not allow_regex:
            raise InvalidSubscriptionConfig(
                f"{field} 不支持正则:{word!r}(上游对全局过滤词按纯文本匹配)"
            )
        m = re.match(r"^/(.+)/[a-z]*$", word)
        if not m:
            raise InvalidSubscriptionConfig(
                f"正则需写成 /pattern/ 或 /pattern/i 形式:{word!r}"
            )
        try:
            re.compile(m.group(1))
        except re.error as e:
            raise InvalidSubscriptionConfig(f"正则无效 {word!r}:{e}")
    return word


class KeywordGroupConfig(BaseModel):
    """一个关键词词组,对应 frequency_words.txt 里由空行分隔的一个块

    [组别名]
    普通词          # 组内"或"关系
    +必须词         # 全部命中才算匹配
    !排除词         # 命中则排除该条(上游实现为全局生效)
    @条数          # 该组最多显示 N 条
    """

    alias: str | None = Field(default=None, max_length=64, description="组别名,可选")
    words: list[str] = Field(default_factory=list, description="普通词,组内或关系")
    required: list[str] = Field(default_factory=list, description="必须词,需全部命中")
    filters: list[str] = Field(default_factory=list, description="排除词,命中即排除")
    max_count: int = Field(default=0, ge=0, le=200, description="该组最多显示条数,0=不限")

    @field_validator("max_count", mode="before")
    @classmethod
    def coerce_max_count(cls, v: Any) -> Any:
        # 前端数字输入框清空时会送 null / ""
        if v is None or v == "":
            return 0
        return v

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        alias = v.strip()
        if not alias:
            return None
        if "\n" in alias or "\r" in alias:
            raise InvalidSubscriptionConfig("组别名不能包含换行")
        if "[" in alias or "]" in alias:
            raise InvalidSubscriptionConfig(f"组别名不能包含方括号:{alias!r}")
        if alias.upper() in RESERVED_SECTION_NAMES:
            raise InvalidSubscriptionConfig(
                f"组别名不能是 {alias}(与区域标记同名):{RESERVED_SECTION_NAMES}"
            )
        return alias

    @field_validator("words", "required", "filters")
    @classmethod
    def validate_words(cls, v: list[str], info) -> list[str]:
        label = {"words": "普通词", "required": "必须词", "filters": "排除词"}[info.field_name]
        out: list[str] = []
        for raw in v:
            word = _validate_word(raw, field=label)
            if word not in out:
                out.append(word)
        return out

    @model_validator(mode="after")
    def validate_non_empty(self) -> "KeywordGroupConfig":
        if not self.words and not self.required:
            raise InvalidSubscriptionConfig(
                "词组至少要有一个普通词或必须词,否则该组不会匹配任何新闻"
            )
        return self


def parse_keyword_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """校验并规范化关键词组 config

    Raises:
        InvalidSubscriptionConfig: 结构非法
    """
    try:
        return KeywordGroupConfig.model_validate(config or {}).model_dump()
    except InvalidSubscriptionConfig:
        raise
    except Exception as e:  # pydantic ValidationError → 统一为本域异常
        detail = "; ".join(
            str(err.get("msg", err)).removeprefix("Value error, ")
            for err in getattr(e, "errors", lambda: [])()
        )
        raise InvalidSubscriptionConfig(detail or str(e)) from e


def derive_keyword_target(cfg: dict[str, Any]) -> str:
    """关键词组的展示/唯一标识:优先组别名,否则用词列表拼接"""
    alias = (cfg.get("alias") or "").strip()
    if alias:
        return alias
    parts = list(cfg.get("words") or []) or list(cfg.get("required") or [])
    return " / ".join(parts)


class SubscriptionBase(BaseModel):
    type: str = Field(description=" / ".join(SUB_TYPES))
    target: str
    name: str | None = Field(default=None, max_length=128)
    config: dict[str, Any] = Field(default_factory=dict)


class SubscriptionCreate(SubscriptionBase):
    target: str = Field(default="", description="keyword 类型可留空,由词组自动派生")

    @model_validator(mode="after")
    def normalize(self) -> "SubscriptionCreate":
        if self.type not in SUB_TYPES:
            raise InvalidSubscriptionConfig(f"不支持的订阅类型:{self.type}")
        if self.type == "keyword":
            self.config = parse_keyword_config(self.config)
            if not self.target.strip():
                self.target = derive_keyword_target(self.config)
        elif not self.target.strip():
            raise InvalidSubscriptionConfig(f"{self.type} 订阅必须提供 target")
        return self


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class SubscriptionOut(SubscriptionBase):
    id: int
    user_id: int
    enabled: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PlatformInfo(BaseModel):
    """trendradar 内置平台清单项"""

    id: str
    name: str
    enabled: bool = True


class PlatformList(BaseModel):
    """平台清单响应"""

    platforms: list[PlatformInfo]
    source: str = "trendradar"


class PlatformSelection(BaseModel):
    """平台多选结果;空列表表示"不限制",即抓取全部平台"""

    platforms: list[str] = Field(default_factory=list)


class GlobalFilterWords(BaseModel):
    """全局过滤词列表(对应 frequency_words.txt 的 [GLOBAL_FILTER] 区域)"""

    words: list[str] = Field(default_factory=list)

    @field_validator("words")
    @classmethod
    def validate_words(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            # 全局过滤区不支持正则:上游按纯文本子串匹配
            word = _validate_word(raw, field="全局过滤词", allow_regex=False)
            if word not in out:
                out.append(word)
        return out