from fastapi.testclient import TestClient


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
    assert client.cookies.get("user_id")
    assert "httponly" in response.headers["set-cookie"].lower()


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
