import json
from types import SimpleNamespace

import httpx
import pytest

from app import config
from app.models import ClaimNature, PerformanceRule
from app.services.achievement_draft_parser import (
    AchievementDraft,
    parse_achievement_draft,
)


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
    assert "ai_unavailable" in draft.uncertain_fields


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
    assert "ai_unavailable" not in draft.uncertain_fields
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
    assert all(
        value is not None and 0 < value <= 8
        for value in requests[0].extensions["timeout"].values()
    )


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
        lambda request: (_ for _ in ()).throw(
            httpx.ConnectError("offline", request=request)
        ),
    ],
    ids=[
        "malformed-json",
        "unknown-category",
        "negative-score",
        "non-finite-score",
        "network",
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
    assert "ai_unavailable" in draft.uncertain_fields
    assert "must-not-leak" not in repr(draft)
