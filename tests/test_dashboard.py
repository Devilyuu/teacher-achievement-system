from datetime import datetime

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Achievement, AnnualSubmission, ClaimNature, User


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


def test_dashboard_shows_annual_submission_status_and_confirm_button(app):
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
        db.add(
            Achievement(
                user_id=admin.id,
                year=year,
                category="教学",
                subcategory="教学成果",
                claim_nature=ClaimNature.result.value,
                title="年度状态测试成果",
                claimed_score=2,
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/")

    assert response.status_code == 200
    assert "年度整理状态" in response.text
    assert "整理中" in response.text
    assert f'action="/annual-submissions/{year}/confirm"' in response.text
    assert "确认本年度材料已整理完成" in response.text


def test_teacher_can_confirm_current_year_submission_from_dashboard(app):
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
        user_id = admin.id
    finally:
        db.close()

    response = client.post(
        f"/annual-submissions/{year}/confirm",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/?year={year}&submitted=1"
    db = SessionLocal()
    try:
        record = db.query(AnnualSubmission).filter_by(user_id=user_id, year=year).one()
        assert record.status == "submitted"
    finally:
        db.close()


def test_confirming_same_year_updates_existing_submission(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )
    year = datetime.now().year

    first = client.post(
        f"/annual-submissions/{year}/confirm",
        follow_redirects=False,
    )
    assert first.status_code == 303
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        record = db.query(AnnualSubmission).filter_by(user_id=admin.id, year=year).one()
        record_id = record.id
        record.submitted_at = datetime(2020, 1, 1)
        db.commit()
        previous_submitted_at = record.submitted_at
    finally:
        db.close()

    second = client.post(
        f"/annual-submissions/{year}/confirm",
        follow_redirects=False,
    )

    assert second.status_code == 303
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        records = db.query(AnnualSubmission).filter_by(user_id=admin.id, year=year).all()
        assert len(records) == 1
        assert records[0].id == record_id
        assert records[0].submitted_at > previous_submitted_at
    finally:
        db.close()
