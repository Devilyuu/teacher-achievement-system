from app.security import hash_password, verify_password
from app.seed_rules import INITIAL_RULES


def test_password_hash_roundtrip():
    password_hash = hash_password("admin123456")

    assert verify_password("admin123456", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_initial_rules_include_custom_catch_all():
    assert any(
        category == "其他有价值工作（自定义）" and subcategory == "自定义工作事项"
        for category, subcategory, *_ in INITIAL_RULES
    )
