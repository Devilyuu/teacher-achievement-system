import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import config
from app.models import ClaimNature, PerformanceRule
from app.services.achievement_draft_parser import (
    AchievementDraft,
    parse_achievement_draft,
)


@pytest.fixture(scope="module")
def real_rules():
    rules_path = (
        Path(__file__).parents[1] / "app" / "data" / "performance_rules.json"
    )
    return json.loads(rules_path.read_text(encoding="utf-8"))["rules"]


def _rule(**overrides) -> PerformanceRule:
    values = {
        "category": "育人成效",
        "subcategory": "指导学生大赛（包括技能、双创）",
        "base_rule": "3/项",
        "national_rule": "/",
        "provincial_rule": "省二8、省三5",
        "city_rule": "5、4、3/项",
        "school_rule": "3、2、1/项",
        "college_rule": "——",
        "remark": "个人申报",
        "is_team": False,
        "is_department_assigned": False,
        "is_active": True,
    }
    values.update(overrides)
    return PerformanceRule(**values)


def _config(**overrides):
    values = {
        "ai_ready": False,
        "ai_api_key": "",
        "ai_base_url": "https://ai.example.test/v1",
        "ai_model": "test-model",
        "ai_timeout_seconds": 30,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _ai_draft(**overrides):
    values = {
        "year": 2025,
        "title": "AI整理后的竞赛成果",
        "category": "育人成效",
        "subcategory": "指导学生大赛（包括技能、双创）",
        "claim_nature": "成果性工作",
        "date_range": "2025年",
        "level": "省级",
        "personal_role": "第一指导教师",
        "current_stage": "已获二等奖",
        "base_score": 3,
        "performance_score": 8,
        "claimed_score": 11,
        "notes": "",
        "confidence": 0.94,
        "uncertain_fields": [],
    }
    values.update(overrides)
    return values


def _chat_response(content):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def test_deterministic_parser_maps_provincial_student_competition():
    description = (
        "2025年指导学生参加江苏省职业技能竞赛数字艺术赛项，"
        "获得二等奖，我是第一指导教师。"
    )

    draft = parse_achievement_draft(
        description,
        [_rule()],
        integration_config=_config(),
    )

    assert draft.year == 2025
    assert draft.title == "指导学生参加江苏省职业技能竞赛数字艺术赛项，获得二等奖"
    assert draft.category == "育人成效"
    assert draft.subcategory == "指导学生大赛（包括技能、双创）"
    assert draft.claim_nature == ClaimNature.result
    assert draft.level == "省级"
    assert draft.personal_role == "第一指导教师"
    assert draft.base_score == 3
    assert draft.performance_score == 8
    assert draft.claimed_score == 11
    assert 0 <= draft.confidence <= 1
    assert "ai_not_configured" in draft.uncertain_fields


def test_real_rules_keep_competition_example_mapping(real_rules):
    draft = parse_achievement_draft(
        "2025年指导学生参加江苏省职业技能竞赛数字艺术赛项，"
        "获得二等奖，我是第一指导教师。",
        real_rules,
        integration_config=_config(),
    )

    assert (draft.category, draft.subcategory) == (
        "育人成效",
        "指导学生大赛（包括技能、双创）",
    )
    assert draft.level == "省级"
    assert draft.personal_role == "第一指导教师"
    assert draft.base_score == 3
    assert draft.performance_score == 8
    assert draft.claimed_score == 11


def test_real_rules_use_uncertain_custom_fallback_for_weak_skill_words(real_rules):
    draft = parse_achievement_draft(
        "2025年学生技能提升工作",
        real_rules,
        integration_config=_config(),
    )

    assert (draft.category, draft.subcategory) == (
        "其他有价值工作（自定义）",
        "自定义工作事项",
    )
    assert {"category", "subcategory"} <= set(draft.uncertain_fields)
    assert draft.confidence < 0.5


def test_deterministic_parser_marks_missing_year_and_process_stage():
    rules = [
        {
            "category": "教学",
            "subcategory": "在线精品课程建设项目",
            "base_rule": "2/项",
            "school_rule": "6/项",
            "is_active": True,
        }
    ]

    draft = parse_achievement_draft(
        "我作为负责人，校级在线精品课程建设项目正在申报中。",
        rules,
        integration_config=_config(),
    )

    assert draft.year is None
    assert draft.title == "校级在线精品课程建设项目正在申报中"
    assert draft.category == "教学"
    assert draft.subcategory == "在线精品课程建设项目"
    assert draft.claim_nature == ClaimNature.process
    assert draft.current_stage == "申报中"
    assert draft.level == "校级"
    assert draft.personal_role == "负责人"
    assert draft.base_score == 2
    assert draft.performance_score == 6
    assert draft.claimed_score == 8
    assert "year" in draft.uncertain_fields


def test_unknown_description_does_not_invent_a_category():
    draft = parse_achievement_draft(
        "2025年完成了一项难以归类的重要工作。",
        [_rule()],
        integration_config=_config(),
    )

    assert draft.category == ""
    assert draft.subcategory == ""
    assert {"category", "subcategory"} <= set(draft.uncertain_fields)


def test_title_removes_year_and_leading_spoken_role_without_rewriting_content():
    draft = parse_achievement_draft(
        "2025年度，我是负责人，建设在线精品课程。",
        [],
        integration_config=_config(),
    )

    assert draft.title == "建设在线精品课程"
    assert draft.personal_role == "负责人"


def test_title_removes_leading_spoken_year_and_role_but_keeps_body():
    draft = parse_achievement_draft(
        "于2025年，我担任负责人，在线精品课程建设中。",
        [],
        integration_config=_config(),
    )

    assert draft.title == "在线精品课程建设中"
    assert draft.personal_role == "负责人"
    assert draft.claim_nature == ClaimNature.process
    assert draft.current_stage == "建设中"


@pytest.mark.parametrize(
    "description",
    [
        "2025年担任负责人，建设在线精品课程",
        "2025年建设在线精品课程，担任负责人",
    ],
)
def test_title_removes_role_prefix_or_suffix_without_first_person(description):
    draft = parse_achievement_draft(
        description,
        [],
        integration_config=_config(),
    )

    assert draft.title == "建设在线精品课程"
    assert draft.personal_role == "负责人"


def test_parser_only_uses_active_rule_pairs():
    rules = [
        {
            "category": "错误分类",
            "subcategory": "在线精品课程建设项目",
            "base_rule": "99",
            "school_rule": "99",
            "is_active": False,
        },
        {
            "category": "教学",
            "subcategory": "在线精品课程建设项目",
            "base_rule": "2",
            "school_rule": "6",
            "is_active": True,
        },
    ]

    draft = parse_achievement_draft(
        "2025年校级在线精品课程建设项目，担任负责人。",
        rules,
        integration_config=_config(),
    )

    assert (draft.category, draft.subcategory) == (
        "教学",
        "在线精品课程建设项目",
    )


def test_ambiguous_rule_score_stays_zero_and_is_marked_uncertain():
    draft = parse_achievement_draft(
        "2025年指导学生参加江苏省职业技能竞赛。",
        [_rule(provincial_rule="省二8、省三5")],
        integration_config=_config(),
    )

    assert draft.base_score == 3
    assert draft.performance_score == 0
    assert draft.claimed_score == 3
    assert "performance_score" in draft.uncertain_fields


def test_conditional_rule_score_requires_condition_in_description(real_rules):
    draft = parse_achievement_draft(
        "校级专业教学资源库建设项目申报中",
        real_rules,
        integration_config=_config(),
    )

    assert draft.subcategory == "专业教学资源库建设申报立项/验收通过"
    assert draft.base_score == 5
    assert draft.performance_score == 0
    assert "performance_score" in draft.uncertain_fields


@pytest.mark.parametrize(
    "description",
    [
        "校级专业教学资源库建设项目尚未验收通过",
        "校级专业教学资源库建设项目未通过验收",
        "校级专业教学资源库建设项目验收未通过",
    ],
)
def test_real_conditional_rule_rejects_negated_acceptance(
    description,
    real_rules,
):
    draft = parse_achievement_draft(
        description,
        real_rules,
        integration_config=_config(),
    )

    assert draft.subcategory == "专业教学资源库建设申报立项/验收通过"
    assert draft.performance_score == 0
    assert "performance_score" in draft.uncertain_fields


def test_conditional_rule_score_is_used_when_condition_is_explicit(real_rules):
    draft = parse_achievement_draft(
        "校级专业教学资源库建设项目验收通过",
        real_rules,
        integration_config=_config(),
    )

    assert draft.subcategory == "专业教学资源库建设申报立项/验收通过"
    assert draft.performance_score == 10


def test_award_condition_accepts_an_explicit_special_prize():
    rule = {
        "category": "教学",
        "subcategory": "测试项目",
        "base_rule": "1/项",
        "school_rule": "10/项（获奖）",
        "is_active": True,
    }

    draft = parse_achievement_draft(
        "2025年校级测试项目获得特等奖",
        [rule],
        integration_config=_config(),
    )

    assert draft.performance_score == 10


@pytest.mark.parametrize(
    "description",
    [
        "2025年校级测试项目未获奖",
        "2025年校级测试项目没有获奖",
        "2025年校级测试项目不符合获奖条件",
    ],
)
def test_award_condition_rejects_negated_award_evidence(description):
    rule = {
        "category": "教学",
        "subcategory": "测试项目",
        "base_rule": "1/项",
        "school_rule": "10/项（获奖）",
        "is_active": True,
    }

    draft = parse_achievement_draft(
        description,
        [rule],
        integration_config=_config(),
    )

    assert draft.performance_score == 0
    assert "performance_score" in draft.uncertain_fields


def test_unlabelled_rank_list_is_not_inferred_from_award_order(real_rules):
    draft = parse_achievement_draft(
        "指导学生参加市级职业技能竞赛并获得二等奖，担任第一指导教师",
        real_rules,
        integration_config=_config(),
    )

    assert draft.subcategory == "指导学生大赛（包括技能、双创）"
    assert draft.performance_score == 0
    assert "performance_score" in draft.uncertain_fields


def test_draft_model_rejects_unknown_level():
    with pytest.raises(ValueError):
        AchievementDraft(
            year=2025,
            title="测试成果",
            category="教学",
            subcategory="测试",
            claim_nature=ClaimNature.result,
            date_range="2025年",
            level="国际级",
            personal_role="",
            current_stage="",
            base_score=0,
            performance_score=0,
            claimed_score=0,
            notes="",
            confidence=0.5,
            uncertain_fields=[],
        )


def test_draft_model_normalizes_inconsistent_claimed_score():
    draft = AchievementDraft(
        year=2025,
        title="测试成果",
        category="教学",
        subcategory="测试",
        claim_nature=ClaimNature.result,
        date_range="2025年",
        level="",
        personal_role="",
        current_stage="",
        base_score=2,
        performance_score=3,
        claimed_score=99,
        notes="",
        confidence=0.5,
        uncertain_fields=[],
    )

    assert draft.claimed_score == 5
    assert "claimed_score" in draft.uncertain_fields


@pytest.mark.parametrize(
    ("base_score", "performance_score", "claimed_score"),
    [
        (1e308, 1e308, 0),
        (100001, 0, 100001),
        (60000, 60000, 120000),
    ],
)
def test_draft_model_rejects_non_finite_or_unreasonable_scores(
    base_score,
    performance_score,
    claimed_score,
):
    with pytest.raises(ValueError):
        AchievementDraft(
            year=2025,
            title="测试成果",
            category="教学",
            subcategory="测试",
            claim_nature=ClaimNature.result,
            date_range="2025年",
            level="",
            personal_role="",
            current_stage="",
            base_score=base_score,
            performance_score=performance_score,
            claimed_score=claimed_score,
            notes="",
            confidence=0.5,
            uncertain_fields=[],
        )


def test_draft_model_limits_each_uncertain_field_name():
    with pytest.raises(ValueError):
        AchievementDraft(
            year=2025,
            title="测试成果",
            category="教学",
            subcategory="测试",
            claim_nature=ClaimNature.result,
            date_range="2025年",
            level="",
            personal_role="",
            current_stage="",
            base_score=0,
            performance_score=0,
            claimed_score=0,
            notes="",
            confidence=0.5,
            uncertain_fields=["x" * 33],
        )


def test_draft_model_limits_uncertain_field_count():
    with pytest.raises(ValueError):
        AchievementDraft(
            year=2025,
            title="测试成果",
            category="教学",
            subcategory="测试",
            claim_nature=ClaimNature.result,
            date_range="2025年",
            level="",
            personal_role="",
            current_stage="",
            base_score=0,
            performance_score=0,
            claimed_score=0,
            notes="",
            confidence=0.5,
            uncertain_fields=[f"field_{index}" for index in range(33)],
        )


def test_unreasonable_score_in_lightweight_rule_is_not_emitted():
    rule = {
        "category": "教学",
        "subcategory": "在线精品课程建设项目",
        "base_rule": "999999/项",
        "school_rule": "999999/项",
        "is_active": True,
    }

    draft = parse_achievement_draft(
        "2025年校级在线精品课程建设项目",
        [rule],
        integration_config=_config(),
    )

    assert draft.base_score == 0
    assert draft.performance_score == 0
    assert {"base_score", "performance_score"} <= set(draft.uncertain_fields)
    assert "Infinity" not in draft.model_dump_json()


@pytest.mark.parametrize("description", ["", " " * 4, "成" * 2001])
def test_parser_rejects_descriptions_outside_length_limit(description):
    with pytest.raises(ValueError, match="1 to 2000"):
        parse_achievement_draft(
            description,
            [_rule()],
            integration_config=_config(),
        )


def test_parser_accepts_description_at_length_limit_without_oversized_title():
    draft = parse_achievement_draft(
        "成" * 2000,
        [_rule()],
        integration_config=_config(),
    )

    assert len(draft.title) == 255
    assert "title" in draft.uncertain_fields


@pytest.mark.parametrize(
    ("description", "expected_level"),
    [
        ("获得浙江省教学成果奖", "省级"),
        ("获得南京市教学成果奖", "市级"),
        ("获国家教学成果奖", "国家级"),
        ("获学院级优秀项目", "学院级"),
        ("获校级优秀项目", "校级"),
    ],
)
def test_deterministic_parser_extracts_supported_levels(
    description,
    expected_level,
):
    draft = parse_achievement_draft(
        description,
        [],
        integration_config=_config(),
    )

    assert draft.level == expected_level


@pytest.mark.parametrize(
    "description",
    [
        "服务全省教师发展",
        "在学校参加培训",
    ],
)
def test_level_inference_requires_explicit_level_or_achievement_context(
    description,
    real_rules,
):
    draft = parse_achievement_draft(
        description,
        real_rules,
        integration_config=_config(),
    )

    assert draft.level == ""
    assert "level" in draft.uncertain_fields


@pytest.mark.parametrize(
    ("description", "expected_level"),
    [
        ("非国家级而是省级教学成果奖", "省级"),
        ("不是国家级而是市级科研项目", "市级"),
        ("并非省级而是校级建设项目", "校级"),
        ("不属于市级而是学院级项目", "学院级"),
        ("非国家级科研项目", ""),
    ],
)
def test_level_parser_ignores_negated_candidates(description, expected_level):
    draft = parse_achievement_draft(
        description,
        [],
        integration_config=_config(),
    )

    assert draft.level == expected_level


@pytest.mark.parametrize(
    "region",
    [
        "北京市",
        "天津市",
        "上海市",
        "重庆市",
        "河北省",
        "山西省",
        "辽宁省",
        "吉林省",
        "黑龙江省",
        "江苏省",
        "浙江省",
        "安徽省",
        "福建省",
        "江西省",
        "山东省",
        "河南省",
        "湖北省",
        "湖南省",
        "广东省",
        "海南省",
        "四川省",
        "贵州省",
        "云南省",
        "陕西省",
        "甘肃省",
        "青海省",
        "台湾省",
        "内蒙古自治区",
        "广西壮族自治区",
        "西藏自治区",
        "宁夏回族自治区",
        "新疆维吾尔自治区",
        "香港特别行政区",
        "澳门特别行政区",
    ],
)
def test_province_level_regions_are_provincial_in_achievement_context(region):
    draft = parse_achievement_draft(
        f"{region}教学成果奖",
        [],
        integration_config=_config(),
    )

    assert draft.level == "省级"


def test_ordinary_city_remains_city_level():
    draft = parse_achievement_draft(
        "常州市教学成果奖",
        [],
        integration_config=_config(),
    )

    assert draft.level == "市级"


@pytest.mark.parametrize(
    "description",
    [
        "在线精品课程正在申报",
        "在线精品课程拟申报",
        "在线精品课程处于申报阶段",
        "在线精品课程建设中",
    ],
)
def test_process_nature_covers_common_in_progress_phrases(description):
    draft = parse_achievement_draft(
        description,
        [],
        integration_config=_config(),
    )

    assert draft.claim_nature == ClaimNature.process


def test_ai_parser_uses_dynamic_openai_compatible_config_and_normalizes_total(
    monkeypatch,
):
    requests = []

    def handler(request):
        requests.append(request)
        return _chat_response(json.dumps(_ai_draft(claimed_score=99)))

    integration_config = _config(
        ai_ready=True,
        ai_api_key="secret-test-key",
        ai_base_url="https://gateway.example.test/v1/",
        ai_timeout_seconds=47.5,
    )
    monkeypatch.setattr(
        config,
        "get_personal_integration_config",
        lambda: integration_config,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))

    draft = parse_achievement_draft(
        "2025年指导学生参加江苏省职业技能竞赛，获得二等奖，"
        "我是第一指导教师。",
        [_rule()],
        client=client,
    )

    assert draft.title == "AI整理后的竞赛成果"
    assert draft.claimed_score == 11
    assert "claimed_score" in draft.uncertain_fields
    assert draft.confidence != 0.94
    assert "ai_not_configured" not in draft.uncertain_fields
    assert requests[0].url == (
        "https://gateway.example.test/v1/chat/completions"
    )
    assert requests[0].headers["Authorization"] == "Bearer secret-test-key"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "test-model"
    assert payload["response_format"] == {"type": "json_object"}
    prompt = json.dumps(payload["messages"], ensure_ascii=False)
    assert "指导学生大赛（包括技能、双创）" in prompt
    assert "uncertain_fields" in prompt
    assert "secret-test-key" not in prompt
    assert all(
        value == 47.5
        for value in requests[0].extensions["timeout"].values()
    )


def test_ai_classification_without_description_evidence_uses_custom_fallback(
    real_rules,
):
    def handler(request):
        return _chat_response(
            json.dumps(
                _ai_draft(
                    title="跨部门育人支持工作",
                    level="",
                    personal_role="负责人",
                    base_score=99999,
                    performance_score=1,
                    claimed_score=100000,
                    confidence=0.99,
                )
            )
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    draft = parse_achievement_draft(
        "2025年完成跨部门育人支持工作，担任负责人。",
        real_rules,
        integration_config=_config(
            ai_ready=True,
            ai_api_key="secret-key",
        ),
        client=client,
    )

    assert (draft.category, draft.subcategory) == (
        "其他有价值工作（自定义）",
        "自定义工作事项",
    )
    assert draft.title == "跨部门育人支持工作"
    assert draft.personal_role == "负责人"
    assert draft.base_score == 0
    assert draft.performance_score == 0
    assert draft.claimed_score == 0
    assert draft.confidence < 0.5
    assert {"category", "subcategory"} <= set(draft.uncertain_fields)


def test_ai_classification_conflict_uses_strong_deterministic_rule(real_rules):
    def handler(request):
        return _chat_response(
            json.dumps(
                _ai_draft(
                    title="AI整理的资源库成果",
                    level="校级",
                    personal_role="负责人",
                )
            )
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    draft = parse_achievement_draft(
        "2025年校级专业教学资源库建设项目验收通过，担任负责人。",
        real_rules,
        integration_config=_config(
            ai_ready=True,
            ai_api_key="secret-key",
        ),
        client=client,
    )

    assert (draft.category, draft.subcategory) == (
        "教学",
        "专业教学资源库建设申报立项/验收通过",
    )
    assert draft.title == "AI整理的资源库成果"
    assert draft.base_score == 5
    assert draft.performance_score == 10
    assert {"category", "subcategory"} <= set(draft.uncertain_fields)
    assert draft.confidence < 0.5


def test_ai_score_over_safe_limit_forces_validated_fallback(real_rules):
    def handler(request):
        return _chat_response(
            json.dumps(
                _ai_draft(
                    base_score=999999,
                    performance_score=0,
                    claimed_score=999999,
                )
            )
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    draft = parse_achievement_draft(
        "2025年学生技能提升工作",
        real_rules,
        integration_config=_config(
            ai_ready=True,
            ai_api_key="secret-key",
        ),
        client=client,
    )

    assert (draft.category, draft.subcategory) == (
        "其他有价值工作（自定义）",
        "自定义工作事项",
    )
    assert draft.claimed_score == 0
    assert "ai_invalid_response" in draft.uncertain_fields


def test_ai_timeout_has_a_specific_safe_reason(real_rules):
    def handler(request):
        raise httpx.ReadTimeout(
            "secret internal timeout detail",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    draft = parse_achievement_draft(
        "2025年学生技能提升工作",
        real_rules,
        integration_config=_config(
            ai_ready=True,
            ai_api_key="secret-key",
        ),
        client=client,
    )

    assert "ai_timeout" in draft.uncertain_fields
    assert "ai_invalid_response" not in draft.uncertain_fields
    assert "secret" not in repr(draft)


def test_ai_overflow_error_never_escapes_public_parser(real_rules):
    def handler(request):
        raise OverflowError("float overflow from huge model number")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    draft = parse_achievement_draft(
        "2025年学生技能提升工作",
        real_rules,
        integration_config=_config(
            ai_ready=True,
            ai_api_key="secret-key",
        ),
        client=client,
    )

    assert "ai_invalid_response" in draft.uncertain_fields
    assert draft.claimed_score == 0


def test_ai_network_error_has_a_specific_safe_reason(real_rules):
    def handler(request):
        raise httpx.ConnectError("internal network detail", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    draft = parse_achievement_draft(
        "2025年学生技能提升工作",
        real_rules,
        integration_config=_config(
            ai_ready=True,
            ai_api_key="secret-key",
        ),
        client=client,
    )

    assert "ai_network_error" in draft.uncertain_fields
    assert "ai_invalid_response" not in draft.uncertain_fields


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda request: _chat_response("{not-json"),
        lambda request: _chat_response(
            json.dumps(
                _ai_draft(category="模型自创分类", subcategory="模型自创小类")
            )
        ),
        lambda request: _chat_response(json.dumps(_ai_draft(base_score=-1))),
        lambda request: _chat_response(
            json.dumps(_ai_draft(base_score=float("inf")))
        ),
    ],
    ids=[
        "malformed-json",
        "unknown-category",
        "negative-score",
        "non-finite-score",
    ],
)
def test_invalid_or_unavailable_ai_falls_back_safely(response_factory):
    client = httpx.Client(transport=httpx.MockTransport(response_factory))

    draft = parse_achievement_draft(
        "2025年指导学生参加江苏省职业技能竞赛，获得二等奖，"
        "我是第一指导教师。",
        [_rule()],
        integration_config=_config(
            ai_ready=True,
            ai_api_key="must-not-leak",
        ),
        client=client,
    )

    assert draft.title.startswith("指导学生参加江苏省职业技能竞赛")
    assert draft.category == "育人成效"
    assert draft.subcategory == "指导学生大赛（包括技能、双创）"
    assert draft.base_score == 3
    assert draft.performance_score == 8
    assert "ai_invalid_response" in draft.uncertain_fields
    assert "must-not-leak" not in repr(draft)
