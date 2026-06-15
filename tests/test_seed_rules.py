from uuid import uuid4

from app.database import SessionLocal
from app.models import PerformanceRule
from app.security import hash_password, verify_password
from app.seed_rules import INITIAL_RULES, load_rule_catalog, seed_initial_data


def test_password_hash_roundtrip():
    password_hash = hash_password("admin123456")

    assert verify_password("admin123456", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_initial_rules_include_custom_catch_all():
    assert any(
        category == "其他有价值工作（自定义）" and subcategory == "自定义工作事项"
        for category, subcategory, *_ in INITIAL_RULES
    )


def test_rule_catalog_contains_all_excel_rules_and_custom_catch_all():
    rules = load_rule_catalog()

    assert len(rules) == 79
    assert len({rule["category"] for rule in rules}) == 10
    assert sum(rule["is_team"] for rule in rules) == 8
    assert sum(rule["is_department_assigned"] for rule in rules) == 2


def test_rule_catalog_preserves_level_rules_and_color_based_assignment_modes():
    rules = {
        (rule["category"], rule["subcategory"]): rule
        for rule in load_rule_catalog()
    }

    horizontal_project = rules[("科研与社会服务工作", "横向课题及项目")]
    assert horizontal_project["base_rule"] == "0.5/万元（上限10分，分数负责人分配）"
    assert horizontal_project["is_team"] is False
    assert horizontal_project["is_department_assigned"] is False

    team_award = rules[("教学", "教学成果奖申报及获奖")]
    assert team_award["city_rule"] == "15、12、10/项"
    assert team_award["is_team"] is True

    union_activity = rules[
        ("师德师风及党建思政工作", "参与工会活动（运动会、羽毛球、乒乓球等）")
    ]
    assert union_activity["is_department_assigned"] is True
    assert union_activity["is_team"] is False


def test_seed_preserves_edited_and_custom_rules(app):
    source = load_rule_catalog()[0]
    custom_subcategory = f"管理员新增规则{uuid4().hex}"
    db = SessionLocal()
    try:
        existing = (
            db.query(PerformanceRule)
            .filter_by(
                category=source["category"],
                subcategory=source["subcategory"],
            )
            .one()
        )
        existing.remark = "管理员人工修改"
        existing.sort_order = 4321
        existing.is_active = False
        custom = PerformanceRule(
            category="管理员自定义类别",
            subcategory=custom_subcategory,
            base_rule="2/项",
            remark="人工新增",
            is_active=True,
            sort_order=5000,
        )
        db.add(custom)
        db.commit()

        seed_initial_data()
        db.expire_all()

        edited = db.get(PerformanceRule, existing.id)
        persisted_custom = (
            db.query(PerformanceRule)
            .filter_by(subcategory=custom_subcategory)
            .one()
        )
        assert edited.remark == "管理员人工修改"
        assert edited.sort_order == 4321
        assert edited.is_active is False
        assert persisted_custom.is_active is True
        assert persisted_custom.base_rule == "2/项"
    finally:
        if "existing" in locals():
            existing = db.get(PerformanceRule, existing.id)
            existing.remark = source["remark"]
            existing.sort_order = source["sort_order"]
            existing.is_active = True
        db.query(PerformanceRule).filter_by(
            subcategory=custom_subcategory
        ).delete()
        db.commit()
        db.close()
