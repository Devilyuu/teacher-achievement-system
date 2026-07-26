from datetime import datetime

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Achievement, AchievementStatus, AnnualSubmission, ClaimNature, User
from app.services.reporting_year import default_reporting_year


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

    response = client.get(f"/?year={year}")

    assert response.status_code == 200
    assert f"{year} 年度成果概览" in response.text
    assert "年度首页测试成果" in response.text
    assert "待完善" in response.text
    assert f'href="/exports/{year}/personal"' in response.text
    assert 'data-lucide="archive-restore"' in response.text
    assert 'data-lucide="package-down"' not in response.text
    assert 'src="http://testserver/static/vendor/lucide.min.js"' in response.text
    assert "unpkg.com" not in response.text


def test_dashboard_uses_designed_right_rail_for_year_workbench(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="dashboard-workbench"' in response.text
    assert 'class="dashboard-side"' in response.text
    assert 'class="panel annual-submission-panel dashboard-status-card"' in response.text
    assert 'class="dashboard-side-metrics"' in response.text
    assert 'class="panel category-panel dashboard-category-card"' in response.text
    assert 'data-lucide="clipboard-check"' in response.text


def test_dashboard_defaults_to_current_reporting_year(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/")

    assert response.status_code == 200
    assert f"{default_reporting_year()} 年度成果概览" in response.text
    assert f'href="/achievements/new?year={default_reporting_year()}"' in response.text


def test_dashboard_carries_selected_year_to_new_record(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/?year=2025")

    assert response.status_code == 200
    assert '<option value="2025" selected>2025 年</option>' in response.text
    assert '<option value="2026"' in response.text
    assert 'href="/achievements/new?year=2025"' in response.text


def test_dashboard_shows_current_year_pending_items_with_reasons(app):
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
        pending = Achievement(
            user_id=admin.id,
            year=year,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="当前年度待处理成果",
            claimed_score=3,
            status=AchievementStatus.needs_info.value,
        )
        ready = Achievement(
            user_id=admin.id,
            year=year,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="当前年度已完整成果",
            claimed_score=5,
            status=AchievementStatus.ready.value,
        )
        previous_year_pending = Achievement(
            user_id=admin.id,
            year=year - 1,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="上一年度待处理成果",
            claimed_score=3,
            status=AchievementStatus.needs_info.value,
        )
        db.add_all([pending, ready, previous_year_pending])
        db.commit()
        pending_id = pending.id
    finally:
        db.close()

    response = client.get(f"/?year={year}")

    assert response.status_code == 200
    assert 'class="panel pending-panel"' in response.text
    pending_panel = response.text.split('class="panel pending-panel"', 1)[1].split(
        "</section>",
        1,
    )[0]
    assert "待处理事项" in pending_panel
    assert "当前年度待处理成果" in pending_panel
    assert "未上传支撑材料" in pending_panel
    assert f'href="/achievements/{pending_id}"' in pending_panel
    assert "当前年度已完整成果" not in pending_panel
    assert "上一年度待处理成果" not in pending_panel


def test_dashboard_shows_pending_empty_state_when_no_items(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="panel pending-panel"' in response.text
    assert "本年度暂无待处理事项" in response.text


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

    response = client.get(f"/?year={year}")

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
