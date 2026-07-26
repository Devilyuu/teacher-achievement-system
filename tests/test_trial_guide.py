from fastapi.testclient import TestClient

from app.services.reporting_year import default_reporting_year


def _login_admin(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_teacher_trial_guide_is_available_from_sidebar(app):
    client = TestClient(app)
    _login_admin(client)

    dashboard = client.get("/")

    assert dashboard.status_code == 200
    assert 'href="/trial-guide"' in dashboard.text
    assert "试用指引" in dashboard.text


def test_trial_guide_explains_core_teacher_trial_flow(app):
    client = TestClient(app)
    _login_admin(client)

    response = client.get("/trial-guide")

    assert response.status_code == 200
    assert "教师试用指引" in response.text
    assert f"{default_reporting_year()} 年度" in response.text
    assert "新增一条真实或接近真实的成果" in response.text
    assert "上传至少一份支撑材料" in response.text
    assert "生成年度材料包" in response.text
    assert 'href="/achievements/new?year=' in response.text
    assert 'href="/exports/' in response.text
    assert 'href="/feedback"' in response.text
