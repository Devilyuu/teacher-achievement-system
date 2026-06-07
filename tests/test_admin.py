from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import PerformanceRule, Role, User
from app.security import hash_password, verify_password


def _login_admin(client: TestClient) -> None:
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )


def _create_teacher(username: str, password: str = "teacher-pass-123") -> None:
    db = SessionLocal()
    try:
        db.add(
            User(
                username=username,
                full_name="普通教师",
                department="教学部",
                role=Role.teacher.value,
                password_hash=hash_password(password),
            )
        )
        db.commit()
    finally:
        db.close()


def test_admin_users_page_requires_authentication(app):
    client = TestClient(app)

    response = client.get("/admin/users", follow_redirects=False)

    assert response.status_code in {401, 303}
    if response.status_code == 303:
        assert response.headers["location"] == "/login"


def test_non_admin_user_cannot_access_admin_users_page(app):
    username = f"teacher-{uuid4().hex}"
    _create_teacher(username)
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": username, "password": "teacher-pass-123"},
        follow_redirects=False,
    )

    response = client.get("/admin/users", follow_redirects=False)

    assert response.status_code == 403


def test_admin_can_create_teacher_user_and_teacher_can_log_in(app):
    username = f"created-teacher-{uuid4().hex}"
    password = "new-teacher-pass-123"
    admin_client = TestClient(app)
    _login_admin(admin_client)

    response = admin_client.post(
        "/admin/users",
        data={
            "username": username,
            "full_name": "新建教师",
            "department": "信息工程学院",
            "role": Role.teacher.value,
            "password": password,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/users?")

    list_response = admin_client.get("/admin/users")
    assert list_response.status_code == 200
    assert username in list_response.text
    assert "新建教师" in list_response.text
    assert "信息工程学院" in list_response.text

    teacher_client = TestClient(app)
    login_response = teacher_client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )

    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/change-password"
    assert teacher_client.cookies.get("user_id")

    db = SessionLocal()
    try:
        created_user = db.query(User).filter_by(username=username).one()
        assert created_user.must_change_password is True
    finally:
        db.close()


def test_admin_can_deactivate_and_reactivate_teacher(app):
    username = f"toggle-teacher-{uuid4().hex}"
    _create_teacher(username)
    db = SessionLocal()
    try:
        teacher = db.query(User).filter_by(username=username).one()
        teacher_id = teacher.id
    finally:
        db.close()

    client = TestClient(app)
    _login_admin(client)

    deactivate = client.post(
        f"/admin/users/{teacher_id}/toggle-active",
        follow_redirects=False,
    )
    assert deactivate.status_code == 303

    blocked_login = TestClient(app).post(
        "/login",
        data={"username": username, "password": "teacher-pass-123"},
        follow_redirects=False,
    )
    assert blocked_login.status_code == 401

    reactivate = client.post(
        f"/admin/users/{teacher_id}/toggle-active",
        follow_redirects=False,
    )
    assert reactivate.status_code == 303

    allowed_login = TestClient(app).post(
        "/login",
        data={"username": username, "password": "teacher-pass-123"},
        follow_redirects=False,
    )
    assert allowed_login.status_code == 303


def test_admin_cannot_deactivate_own_account(app):
    client = TestClient(app)
    _login_admin(client)
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        admin_id = admin.id
    finally:
        db.close()

    response = client.post(
        f"/admin/users/{admin_id}/toggle-active",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    db = SessionLocal()
    try:
        assert db.get(User, admin_id).is_active is True
    finally:
        db.close()


def test_admin_can_reset_teacher_password_and_require_change(app):
    username = f"reset-teacher-{uuid4().hex}"
    _create_teacher(username)
    db = SessionLocal()
    try:
        teacher = db.query(User).filter_by(username=username).one()
        teacher_id = teacher.id
    finally:
        db.close()

    client = TestClient(app)
    _login_admin(client)
    response = client.post(
        f"/admin/users/{teacher_id}/reset-password",
        data={"new_password": "reset-pass-456"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db = SessionLocal()
    try:
        teacher = db.get(User, teacher_id)
        assert verify_password("reset-pass-456", teacher.password_hash)
        assert teacher.must_change_password is True
    finally:
        db.close()


def test_duplicate_username_returns_page_error(app):
    client = TestClient(app)
    _login_admin(client)

    response = client.post(
        "/admin/users",
        data={
            "username": "admin",
            "full_name": "重复用户",
            "department": "测试",
            "role": Role.teacher.value,
            "password": "password123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=" in response.headers["location"]


def test_admin_rules_page_includes_custom_category(app):
    client = TestClient(app)
    _login_admin(client)

    response = client.get("/admin/rules")

    assert response.status_code == 200
    assert "其他有价值工作（自定义）" in response.text


def test_admin_rules_page_only_lists_active_rules_and_shows_assignment_mode(app):
    db = SessionLocal()
    try:
        db.add(
            PerformanceRule(
                category="停用测试类别",
                subcategory="不应显示的停用规则",
                is_active=False,
                sort_order=999,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    _login_admin(client)
    response = client.get("/admin/rules")

    assert response.status_code == 200
    assert "不应显示的停用规则" not in response.text
    assert "团队负责人申报并分配" in response.text
    assert "项目负责人统一赋分" in response.text
