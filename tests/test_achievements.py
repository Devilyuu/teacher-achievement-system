from fastapi.testclient import TestClient


def test_authenticated_admin_can_create_achievement_and_see_it_in_list(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.post(
        "/achievements",
        data={
            "year": "2026",
            "category": "其他有价值工作（自定义）",
            "subcategory": "自定义工作事项",
            "claim_nature": "过程性工作",
            "title": "省级技能大赛裁判工作",
            "date_range": "2026-05",
            "level": "省级",
            "personal_role": "裁判",
            "current_stage": "已完成裁判工作并提交总结",
            "base_score": "0",
            "performance_score": "0",
            "claimed_score": "2",
            "notes": "说明该工作对专业建设的价值",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/achievements"

    list_response = client.get("/achievements")

    assert list_response.status_code == 200
    assert "省级技能大赛裁判工作" in list_response.text
    assert "待完善" in list_response.text


def test_achievements_requires_authentication(app):
    client = TestClient(app)

    response = client.get("/achievements", follow_redirects=False)

    assert response.status_code in {401, 303}
    if response.status_code == 303:
        assert response.headers["location"] == "/login"
