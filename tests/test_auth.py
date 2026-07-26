from fastapi.testclient import TestClient
from uuid import uuid4

from app.database import SessionLocal
from app.models import Role, User
from app.security import create_auth_cookie, hash_password, verify_password


def test_login_page_opens(app):
    client = TestClient(app)

    response = client.get("/login")

    assert response.status_code == 200
    assert "name=\"username\"" in response.text
    assert "name=\"password\"" in response.text
    assert "教师成果管理系统" in response.text
    assert "成果有序沉淀，材料随时导出" in response.text
    assert 'data-lucide="eye"' in response.text
    assert "login-shell" in response.text
    assert 'class="mobile-login-brand"' in response.text


def test_invalid_login_does_not_authenticate(app):
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "user_id" not in client.cookies
    assert "用户名或密码错误" in response.text


def test_valid_admin_login_redirects_and_sets_cookie(app):
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie_value = client.cookies.get("user_id")
    assert cookie_value
    assert cookie_value != "1"
    assert "httponly" in response.headers["set-cookie"].lower()
    cookie_attributes = {
        attribute.strip().lower()
        for attribute in response.headers["set-cookie"].split(";")[1:]
    }
    assert "secure" not in cookie_attributes


def test_https_login_sets_secure_cookie(app):
    client = TestClient(app)

    response = client.post(
        "https://testserver/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    cookie_attributes = {
        attribute.strip().lower()
        for attribute in response.headers["set-cookie"].split(";")[1:]
    }
    assert "secure" in cookie_attributes


def test_raw_user_id_cookie_is_rejected(app):
    client = TestClient(app)
    client.cookies.set("user_id", "1")

    response = client.get("/admin/users", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_requires_auth(app):
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_renders_for_authenticated_admin(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "admin" in response.text


def test_logout_clears_cookie(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "user_id" not in client.cookies
    cookie_attributes = {
        attribute.strip().lower()
        for attribute in response.headers["set-cookie"].split(";")[1:]
    }
    assert "httponly" in cookie_attributes
    assert "samesite=lax" in cookie_attributes
    assert "secure" not in cookie_attributes


def test_https_logout_clears_cookie_with_secure_attribute(app):
    client = TestClient(app)

    login_response = client.post(
        "https://testserver/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    assert login_response.status_code == 303
    assert client.cookies.get("user_id")

    response = client.get("https://testserver/logout", follow_redirects=False)

    assert response.status_code == 303
    assert "user_id" not in client.cookies
    cookie_attributes = {
        attribute.strip().lower()
        for attribute in response.headers["set-cookie"].split(";")[1:]
    }
    assert "httponly" in cookie_attributes
    assert "samesite=lax" in cookie_attributes
    assert "secure" in cookie_attributes

    protected_response = client.get(
        "https://testserver/admin/users",
        follow_redirects=False,
    )
    assert protected_response.status_code == 303
    assert protected_response.headers["location"] == "/login"


def test_user_marked_for_password_change_is_redirected_after_login(app):
    username = f"must-change-{uuid4().hex}"
    db = SessionLocal()
    try:
        user = User(
            username=username,
            full_name="需改密教师",
            department="艺术学院",
            role=Role.teacher.value,
            password_hash=hash_password("initial-pass-123"),
            must_change_password=True,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    response = client.post(
        "/login",
        data={"username": username, "password": "initial-pass-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/change-password"

    dashboard_response = client.get("/", follow_redirects=False)
    assert dashboard_response.status_code == 303
    assert dashboard_response.headers["location"] == "/change-password"


def test_authenticated_user_can_change_password(app):
    username = f"password-change-{uuid4().hex}"
    db = SessionLocal()
    try:
        user = User(
            username=username,
            full_name="改密教师",
            department="数字艺术学院",
            role=Role.teacher.value,
            password_hash=hash_password("old-pass-123"),
            must_change_password=True,
        )
        db.add(user)
        db.commit()
        user_id = user.id
    finally:
        db.close()

    client = TestClient(app)
    client.cookies.set("user_id", create_auth_cookie(user_id))
    page = client.get("/change-password")
    assert page.status_code == 200
    assert "修改密码" in page.text

    response = client.post(
        "/change-password",
        data={
            "current_password": "old-pass-123",
            "new_password": "new-pass-456",
            "confirm_password": "new-pass-456",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        assert verify_password("new-pass-456", user.password_hash)
        assert user.must_change_password is False
    finally:
        db.close()
