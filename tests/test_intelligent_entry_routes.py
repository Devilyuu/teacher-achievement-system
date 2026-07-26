from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Role, User
from app.security import create_auth_cookie, hash_password


def _client_for_user(app, username: str) -> TestClient:
    db = SessionLocal()
    try:
        user = User(
            username=username,
            full_name="Personal user",
            department="Digital Arts",
            role=Role.teacher.value,
            password_hash=hash_password("password123"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.set("user_id", create_auth_cookie(user_id))
    return client


def test_intelligent_entry_is_only_visible_to_configured_user(app, monkeypatch):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "1867")
    personal_client = _client_for_user(app, "1867")
    ordinary_client = _client_for_user(app, "ordinary-intelligent-user")

    personal_page = personal_client.get("/achievements/new")
    ordinary_page = ordinary_client.get("/achievements/new")

    assert 'id="intelligent-entry-panel"' in personal_page.text
    assert 'data-lucide="mic"' in personal_page.text
    assert 'id="intelligent-entry-panel"' not in ordinary_page.text


def test_configured_user_can_turn_description_into_reviewable_draft(
    app,
    monkeypatch,
):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "1867")
    monkeypatch.delenv("ACHIEVEMENT_AI_API_KEY", raising=False)
    client = _client_for_user(app, "1867")

    response = client.post(
        "/achievements/intelligent-draft",
        data={
            "description": (
                "2025年指导学生参加江苏省职业技能大赛数字艺术赛项，"
                "获得二等奖，本人是指导教师。"
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft"]["year"] == 2025
    assert payload["draft"]["level"] == "省级"
    assert payload["draft"]["category"]
    assert payload["draft"]["subcategory"]
    assert payload["draft"]["title"]
    assert payload["mode"] == "rule"


def test_ordinary_user_cannot_call_intelligent_entry_endpoint(app, monkeypatch):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "1867")
    client = _client_for_user(app, "ordinary-intelligent-user")

    response = client.post(
        "/achievements/intelligent-draft",
        data={"description": "A valid achievement description"},
    )

    assert response.status_code == 403


def test_intelligent_entry_rejects_blank_or_oversized_description(
    app,
    monkeypatch,
):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "1867")
    client = _client_for_user(app, "1867")

    blank = client.post(
        "/achievements/intelligent-draft",
        data={"description": "   "},
    )
    oversized = client.post(
        "/achievements/intelligent-draft",
        data={"description": "x" * 2001},
    )

    assert blank.status_code == 422
    assert oversized.status_code == 422
