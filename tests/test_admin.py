from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password


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
    assert response.headers["location"] == "/admin/users"

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
    assert login_response.headers["location"] == "/"
    assert teacher_client.cookies.get("user_id")


def test_admin_rules_page_includes_custom_category(app):
    client = TestClient(app)
    _login_admin(client)

    response = client.get("/admin/rules")

    assert response.status_code == 200
    assert "其他有价值工作（自定义）" in response.text
