import json
from pathlib import Path

from app.database import SessionLocal
from app.models import PerformanceRule, Role, User
from app.security import hash_password


RULE_CATALOG_PATH = Path(__file__).with_name("data") / "performance_rules.json"


def _load_catalog() -> dict:
    with RULE_CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def load_rule_catalog() -> list[dict]:
    return _load_catalog()["rules"]


def load_deprecated_rule_keys() -> set[tuple[str, str]]:
    catalog = _load_catalog()
    return {
        (rule["category"], rule["subcategory"])
        for rule in catalog.get("deprecated_rules", [])
    }


INITIAL_RULES = [
    (
        rule["category"],
        rule["subcategory"],
        rule["base_rule"],
        rule["national_rule"],
        rule["provincial_rule"],
        rule["city_rule"],
        rule["school_rule"],
        rule["college_rule"],
        rule["remark"],
        rule["is_team"],
        rule["is_department_assigned"],
    )
    for rule in load_rule_catalog()
]


def _apply_rule_values(target: PerformanceRule, source: dict) -> None:
    target.category = source["category"]
    target.subcategory = source["subcategory"]
    target.base_rule = source["base_rule"]
    target.national_rule = source["national_rule"]
    target.provincial_rule = source["provincial_rule"]
    target.city_rule = source["city_rule"]
    target.school_rule = source["school_rule"]
    target.college_rule = source["college_rule"]
    target.remark = source["remark"]
    target.is_team = source["is_team"]
    target.is_department_assigned = source["is_department_assigned"]
    target.is_active = True
    target.sort_order = source["sort_order"]


def seed_initial_data() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="admin").first():
            db.add(
                User(
                    username="admin",
                    full_name="系统管理员",
                    department="管理",
                    role=Role.admin.value,
                    password_hash=hash_password("admin123456"),
                )
            )

        catalog = load_rule_catalog()
        deprecated_rule_keys = load_deprecated_rule_keys()
        existing_rules = db.query(PerformanceRule).all()
        existing_by_key = {
            (rule.category, rule.subcategory): rule
            for rule in existing_rules
        }

        for source_rule in catalog:
            key = (source_rule["category"], source_rule["subcategory"])
            if key in existing_by_key:
                target = existing_by_key[key]
            else:
                target = PerformanceRule()
                db.add(target)
            _apply_rule_values(target, source_rule)

        if deprecated_rule_keys:
            for existing_rule in existing_rules:
                if (existing_rule.category, existing_rule.subcategory) in deprecated_rule_keys:
                    existing_rule.is_active = False

        db.commit()
    finally:
        db.close()
