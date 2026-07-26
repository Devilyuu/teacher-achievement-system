from app.models import PerformanceRule
from app.services.performance_rule_guidance import (
    LEVEL_OPTIONS,
    assignment_mode,
    rule_for_level,
)


def _rule(**overrides) -> PerformanceRule:
    values = {
        "category": "教学",
        "subcategory": "教学成果奖申报及获奖",
        "base_rule": "10/项",
        "national_rule": "30/项",
        "provincial_rule": "20/项",
        "city_rule": "15/项",
        "school_rule": "10/项",
        "college_rule": "5/项",
        "remark": "",
        "is_team": False,
        "is_department_assigned": False,
    }
    values.update(overrides)
    return PerformanceRule(**values)


def test_level_options_cover_the_confirmed_five_levels():
    assert [option["value"] for option in LEVEL_OPTIONS] == [
        "国家级",
        "省级",
        "市级",
        "校级",
        "学院级",
    ]


def test_rule_for_level_uses_the_matching_level_rule_and_falls_back_to_base_rule():
    rule = _rule(provincial_rule="20/项", college_rule="")

    assert rule_for_level(rule, "省级") == "20/项"
    assert rule_for_level(rule, "学院级") == "10/项"


def test_assignment_mode_distinguishes_personal_team_and_department_assignment():
    assert assignment_mode(_rule()) == "个人申报"
    assert assignment_mode(_rule(is_team=True)) == "团队负责人申报并分配"
    assert assignment_mode(_rule(is_department_assigned=True)) == "项目负责人统一赋分"
