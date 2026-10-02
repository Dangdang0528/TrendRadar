# coding=utf-8
"""关键词组 / 全局过滤词 / 平台默认值 测试

关键点:渲染出的内容必须能被 trendradar 真实解析器
(trendradar.core.frequency)正确读懂,因此这里直接调用上游解析器校验,
而不是断言我们自己的中间结构。
"""

import asyncio
import uuid

import pytest
from pydantic import ValidationError
from trendradar.core.frequency import load_frequency_words, matches_word_groups

import app.adapters.config_provider as cf
from app.adapters.config_provider import (
    UserCtx,
    UserSubscriptionSpec,
    build_config_for_user,
    render_frequency_words,
    render_word_group,
)
from app.db import AsyncSessionLocal, Base, engine
from app.schemas.subscription import (
    GlobalFilterWords,
    InvalidSubscriptionConfig,
    derive_keyword_target,
    parse_keyword_config,
)
from app.services import subscription_service


def _parse(tmp_path, content: str):
    """写出文件 → 交给上游解析器 → (word_groups, filter_words, global_filters)"""
    path = tmp_path / "freq.txt"
    path.write_text(content, encoding="utf-8")
    return load_frequency_words(str(path))


# ── 渲染 → 上游解析器 ─────────────────────────────────────────


def test_rendered_groups_parse_into_expected_structure(tmp_path):
    groups = [
        {
            "alias": "华为",
            "words": ["华为", "鸿蒙"],
            "required": ["发布会"],
            "filters": ["招聘"],
            "max_count": 5,
        },
        {"alias": None, "words": ["/ai|人工智能/"], "required": [], "filters": [], "max_count": 0},
    ]
    content = render_frequency_words(groups, ["震惊"])
    word_groups, filter_words, global_filters = _parse(tmp_path, content)

    assert global_filters == ["震惊"]
    assert len(word_groups) == 2

    huawei, ai = word_groups
    assert huawei["display_name"] == "华为"
    assert huawei["max_count"] == 5
    assert [w["word"] for w in huawei["normal"]] == ["华为", "鸿蒙"]
    assert [w["word"] for w in huawei["required"]] == ["发布会"]

    # 无组别名 → 显示名为正则 pattern 本身
    assert ai["display_name"] == "ai|人工智能"
    assert ai["normal"][0]["is_regex"] is True

    assert [w["word"] for w in filter_words] == ["招聘"]


def test_word_groups_marker_keeps_groups_out_of_global_filter(tmp_path):
    """缺 [WORD_GROUPS] 标记时,后续词组会被解析器当成全局过滤词"""
    content = render_frequency_words([{"alias": None, "words": ["华为"]}], ["震惊"])
    assert "[WORD_GROUPS]" in content

    word_groups, _, global_filters = _parse(tmp_path, content)
    assert global_filters == ["震惊"], "关键词组不应混入全局过滤词"
    assert len(word_groups) == 1


def test_empty_config_matches_everything(tmp_path):
    """没有词组时不做任何过滤(否则用户会一条新闻都收不到)"""
    word_groups, filter_words, global_filters = _parse(tmp_path, render_frequency_words([], []))
    assert word_groups == []
    assert matches_word_groups("随便什么标题", word_groups, filter_words, global_filters) is True


def test_matching_semantics(tmp_path):
    groups = [
        {
            "alias": "华为",
            "words": ["华为", "鸿蒙"],
            "required": ["发布会"],
            "filters": ["招聘"],
            "max_count": 0,
        }
    ]
    word_groups, filter_words, global_filters = _parse(
        tmp_path, render_frequency_words(groups, ["震惊"])
    )

    def hit(title: str) -> bool:
        return matches_word_groups(title, word_groups, filter_words, global_filters)

    assert hit("华为发布会即将举行") is True      # 普通词命中 + 必须词命中
    assert hit("鸿蒙发布会现场") is True          # 同组另一个普通词也算命中
    assert hit("华为新机开售") is False           # 缺必须词「发布会」
    assert hit("华为发布会现场招聘") is False      # 命中排除词
    assert hit("震惊!华为发布会") is False         # 命中全局过滤词
    assert hit("小米新品发布") is False            # 与词组无关


def test_exclude_words_are_global_across_groups(tmp_path):
    """上游实现:! 排除词收集为扁平列表,在任何词组匹配前生效(非"仅限本组")

    UI 文案依赖这一真实行为,这里锁定它防止误改。
    """
    groups = [
        {"alias": "A组", "words": ["甲"], "required": [], "filters": ["广告"], "max_count": 0},
        {"alias": "B组", "words": ["乙"], "required": [], "filters": [], "max_count": 0},
    ]
    word_groups, filter_words, global_filters = _parse(
        tmp_path, render_frequency_words(groups, [])
    )

    assert matches_word_groups("乙 广告", word_groups, filter_words, global_filters) is False


def test_regex_group_matches_ignoring_case(tmp_path):
    groups = [{"alias": "AI", "words": ["/(?<![a-zA-Z])ai(?![a-zA-Z])/"], "required": [], "filters": [], "max_count": 0}]
    word_groups, filter_words, global_filters = _parse(
        tmp_path, render_frequency_words(groups, [])
    )

    assert matches_word_groups("AI 芯片进展", word_groups, filter_words, global_filters) is True
    assert matches_word_groups("ai 芯片进展", word_groups, filter_words, global_filters) is True
    assert matches_word_groups("MAIL 服务器", word_groups, filter_words, global_filters) is False


def test_render_word_group_requires_some_word():
    assert render_word_group({"words": [], "required": []}) == ""


# ── 词组 config 校验 ─────────────────────────────────────────


@pytest.mark.parametrize(
    "words",
    [
        ["+苹果"],       # 必须词前缀应由 required 字段表达
        ["!广告"],       # 排除词前缀应由 filters 字段表达
        ["@5"],          # 条数应由 max_count 表达
        ["[组名]"],      # 词组标记应由 alias 表达
        ["#注释"],       # 会被解析器当注释丢弃
        ["带\n换行"],     # 换行会破坏行结构
        ["/未闭合"],      # 正则格式错误
        ["/[未闭合/"],    # 正则编译失败
        [""],            # 空词
    ],
)
def test_invalid_words_are_rejected(words):
    with pytest.raises(InvalidSubscriptionConfig):
        parse_keyword_config({"words": words})


@pytest.mark.parametrize("alias", ["WORD_GROUPS", "global_filter", "含[括号", "含\n换行"])
def test_invalid_alias_is_rejected(alias):
    with pytest.raises(InvalidSubscriptionConfig):
        parse_keyword_config({"alias": alias, "words": ["华为"]})


def test_group_without_words_is_rejected():
    with pytest.raises(InvalidSubscriptionConfig):
        parse_keyword_config({"alias": "空组"})


def test_required_only_group_is_allowed():
    cfg = parse_keyword_config({"required": ["苹果", "发布会"]})
    assert cfg["words"] == []
    assert cfg["required"] == ["苹果", "发布会"]


def test_config_is_normalized():
    cfg = parse_keyword_config({"words": [" 华为 ", "华为", "鸿蒙"], "max_count": None})
    assert cfg["words"] == ["华为", "鸿蒙"], "应去重并 strip"
    assert cfg["max_count"] == 0
    assert cfg["required"] == [] and cfg["filters"] == []


def test_derive_keyword_target():
    assert derive_keyword_target({"alias": "华为", "words": ["a"]}) == "华为"
    assert derive_keyword_target({"alias": None, "words": ["华为", "鸿蒙"]}) == "华为 / 鸿蒙"
    assert derive_keyword_target({"alias": None, "words": [], "required": ["苹果"]}) == "苹果"


def test_global_filters_reject_regex():
    """上游对全局过滤词按纯文本子串匹配,/.../ 会失效,故直接拒绝"""
    with pytest.raises(ValidationError):
        GlobalFilterWords(words=["/赌博|博彩/"])
    assert GlobalFilterWords(words=[" 震惊 ", "震惊"]).words == ["震惊"]


# ── 平台:默认全平台 ─────────────────────────────────────────


def test_platforms_default_to_all_when_unset():
    cfg = build_config_for_user(UserCtx(user_id=1, email="x@t.local"))
    catalog = cf.load_platform_catalog()
    assert catalog, "测试夹具应复制了 config.yaml"
    assert [p["id"] for p in cfg["PLATFORMS"]] == [p["id"] for p in catalog]


def test_explicit_platform_selection_wins():
    user = UserCtx(
        user_id=1,
        email="x@t.local",
        subscriptions=[UserSubscriptionSpec(type="platform", target="zhihu", name="知乎")],
    )
    cfg = build_config_for_user(user)
    assert [p["id"] for p in cfg["PLATFORMS"]] == ["zhihu"]


def test_non_platform_subscriptions_do_not_leak_into_platforms():
    user = UserCtx(
        user_id=1,
        email="x@t.local",
        subscriptions=[UserSubscriptionSpec(type="rss", target="https://example.com/f.xml")],
    )
    cfg = build_config_for_user(user)
    assert len(cfg["PLATFORMS"]) == len(cf.load_platform_catalog()), "应回退到全平台"


# ── 服务层(DB) ──────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())


async def _create_user() -> int:
    from app.models.user import User

    async with AsyncSessionLocal() as s:
        u = User(email=f"sub{uuid.uuid4().hex[:8]}@t.local", password_hash="x")
        s.add(u)
        await s.flush()
        uid = u.id
        await s.commit()
    return uid


def test_replace_platforms_then_clear_falls_back_to_all():
    async def _run():
        uid = await _create_user()
        async with AsyncSessionLocal() as db:
            await subscription_service.replace_platforms(db, uid, ["zhihu", "weibo", "zhihu"])
            await db.commit()
            subs = await subscription_service.list_subscriptions(db, uid)
            assert sorted(s.target for s in subs) == ["weibo", "zhihu"]

            # 清空 → 不限制 → 抓取全平台
            await subscription_service.replace_platforms(db, uid, [])
            await db.commit()
            subs = await subscription_service.list_subscriptions(db, uid)
            assert subs == []

            user = await _load_ctx(uid, db)
            assert len(user.subscriptions) == 0
            cfg = build_config_for_user(user)
            assert len(cfg["PLATFORMS"]) == len(cf.load_platform_catalog())

    asyncio.run(_run())


def test_replace_platforms_rejects_unknown_id():
    async def _run():
        uid = await _create_user()
        async with AsyncSessionLocal() as db:
            with pytest.raises(InvalidSubscriptionConfig):
                await subscription_service.replace_platforms(db, uid, ["not-a-platform"])
            await db.rollback()

    asyncio.run(_run())


def test_global_filters_round_trip():
    async def _run():
        uid = await _create_user()
        async with AsyncSessionLocal() as db:
            assert await subscription_service.get_global_filters(db, uid) == []

            await subscription_service.set_global_filters(db, uid, ["震惊", "标题党"])
            await db.commit()
            assert await subscription_service.get_global_filters(db, uid) == ["震惊", "标题党"]

            # 幂等:再次写入不会产生第二行
            await subscription_service.set_global_filters(db, uid, ["震惊"])
            await db.commit()
            assert await subscription_service.get_global_filters(db, uid) == ["震惊"]
            subs = await subscription_service.list_subscriptions(db, uid)
            assert len([s for s in subs if s.type == "global_filter"]) == 1

            # 清空 → 删除该行
            await subscription_service.set_global_filters(db, uid, [])
            await db.commit()
            assert await subscription_service.get_global_filters(db, uid) == []

    asyncio.run(_run())


def test_keyword_group_create_and_update_derives_target():
    async def _run():
        uid = await _create_user()
        async with AsyncSessionLocal() as db:
            sub = await subscription_service.create_subscription(
                db, uid, "keyword", "", None,
                {"alias": "华为", "words": ["华为", "鸿蒙"], "required": ["发布会"]},
            )
            await db.commit()
            assert sub.target == "华为"

            updated = await subscription_service.update_subscription(
                db, uid, sub.id,
                config={"alias": None, "words": ["比亚迪"], "required": [], "filters": [], "max_count": 0},
            )
            await db.commit()
            assert updated.target == "比亚迪", "改词组后 target 应重新派生"

    asyncio.run(_run())


def test_keyword_group_duplicate_target_rejected():
    async def _run():
        from app.models.subscription import Subscription

        uid = await _create_user()
        async with AsyncSessionLocal() as db:
            a = await subscription_service.create_subscription(
                db, uid, "keyword", "", None, {"alias": "AI", "words": ["人工智能"]},
            )
            await db.commit()
            b = await subscription_service.create_subscription(
                db, uid, "keyword", "", None, {"alias": "机器人", "words": ["机器人"]},
            )
            await db.commit()
            a_id, b_id = a.id, b.id  # rollback 会让 ORM 对象过期,先取出主键

            with pytest.raises(InvalidSubscriptionConfig):
                await subscription_service.update_subscription(
                    db, uid, b_id, config={"alias": "AI", "words": ["别的"]},
                )
            await db.rollback()

            # 换新会话确认冲突改动没有落库
            async with AsyncSessionLocal() as db2:
                assert (await db2.get(Subscription, b_id)).target == "机器人"
                assert (await db2.get(Subscription, a_id)).target == "AI"

    asyncio.run(_run())


async def _load_ctx(user_id: int, db) -> UserCtx:
    import app.adapters.pipeline_runner as pr

    return await pr._load_user_ctx(user_id, db)


def test_write_user_frequency_file_end_to_end(tmp_path, monkeypatch):
    """DB 里的词组 + 全局过滤词 → 落盘文件 → 上游解析器读回"""

    async def _run():
        uid = await _create_user()
        async with AsyncSessionLocal() as db:
            await subscription_service.create_subscription(
                db, uid, "keyword", "", None,
                {"alias": "华为", "words": ["华为", "鸿蒙"], "required": ["发布会"], "filters": ["招聘"], "max_count": 3},
            )
            await subscription_service.set_global_filters(db, uid, ["震惊"])
            await db.commit()
            return await _load_ctx(uid, db)

    user = asyncio.run(_run())
    content = render_frequency_words(
        [s.config for s in user.subscriptions if s.type == "keyword"],
        [w for s in user.subscriptions if s.type == "global_filter" for w in s.config["words"]],
    )

    word_groups, filter_words, global_filters = _parse(tmp_path, content)
    assert global_filters == ["震惊"]
    assert len(word_groups) == 1 and word_groups[0]["display_name"] == "华为"
    assert [w["word"] for w in filter_words] == ["招聘"]
    assert matches_word_groups("华为发布会现场", word_groups, filter_words, global_filters) is True
    assert matches_word_groups("华为发布会 招聘", word_groups, filter_words, global_filters) is False


def test_legacy_flat_keyword_subscription_still_filters(monkeypatch):
    """早期"一个关键词一行"的老数据不能在升级后静默失效"""
    import app.adapters.pipeline_runner as pr

    user = UserCtx(
        user_id=424242,
        email="legacy@t.local",
        subscriptions=[UserSubscriptionSpec(type="keyword", target="人工智能", config={})],
    )
    path = pr._write_user_frequency_file(user)
    word_groups, _, _ = load_frequency_words(path)
    assert len(word_groups) == 1
    assert [w["word"] for w in word_groups[0]["normal"]] == ["人工智能"]