from datetime import datetime

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Achievement, ClaimNature, User


def test_dashboard_shows_current_year_summary_recent_record_and_export(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    year = datetime.now().year
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = Achievement(
            user_id=admin.id,
            year=year,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="年度首页测试成果",
            claimed_score=6,
        )
        db.add(achievement)
        db.commit()
    finally:
        db.close()

    response = client.get("/")

    assert response.status_code == 200
    assert f"{year} 年度成果概览" in response.text
    assert "年度首页测试成果" in response.text
    assert "待完善" in response.text
    assert f'href="/exports/{year}/personal"' in response.text
    assert 'data-lucide="archive-restore"' in response.text
    assert 'data-lucide="package-down"' not in response.text
    assert 'src="http://testserver/static/vendor/lucide.min.js"' in response.text
    assert "unpkg.com" not in response.text
