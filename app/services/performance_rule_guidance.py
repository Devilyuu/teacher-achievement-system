from sqlalchemy.orm import Session

from app.models import PerformanceRule


LEVEL_OPTIONS = [
    {"value": "国家级", "rule_field": "national_rule"},
    {"value": "省级", "rule_field": "provincial_rule"},
    {"value": "市级", "rule_field": "city_rule"},
    {"value": "校级", "rule_field": "school_rule"},
    {"value": "学院级", "rule_field": "college_rule"},
]

_LEVEL_RULE_FIELDS = {
    option["value"]: option["rule_field"]
    for option in LEVEL_OPTIONS
}


def find_rule(
    db: Session,
    category: str,
    subcategory: str,
) -> PerformanceRule | None:
    return (
        db.query(PerformanceRule)
        .filter(
            PerformanceRule.category == category,
            PerformanceRule.subcategory == subcategory,
            PerformanceRule.is_active.is_(True),
        )
        .first()
    )


def rule_for_level(rule: PerformanceRule | None, level: str) -> str:
    if rule is None:
        return ""
    field_name = _LEVEL_RULE_FIELDS.get(level)
    level_rule = getattr(rule, field_name, "") if field_name else ""
    return level_rule.strip() or rule.base_rule.strip()


def assignment_mode(rule: PerformanceRule | None) -> str:
    if rule is None:
        return "线下审核认定"
    if rule.is_team:
        return "团队负责人申报并分配"
    if rule.is_department_assigned:
        return "项目负责人统一赋分"
    return "个人申报"
