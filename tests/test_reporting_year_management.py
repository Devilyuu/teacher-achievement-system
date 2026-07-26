from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Achievement, ClaimNature, User, UserReportingYear
from app.services.reporting_year import (
    ReportingYearInUseError,
    ReportingYearProtectedError,
    add_user_reporting_year,
    current_reporting_year,
    get_user_default_year,
    get_user_reporting_years,
    remove_user_reporting_year,
    set_user_default_year,
)


def _admin(db):
    return db.query(User).filter(User.username == "admin").one()


def test_current_year_is_the_default_when_user_has_no_preference(app):
    db = SessionLocal()
    try:
        assert get_user_default_year(db, _admin(db).id) == datetime.now().year
    finally:
        db.close()


def test_user_can_add_year_and_set_it_as_default(app):
    db = SessionLocal()
    try:
        user = _admin(db)
        add_user_reporting_year(db, user.id, 2027)
        set_user_default_year(db, user.id, 2027)

        assert get_user_default_year(db, user.id) == 2027
        assert get_user_reporting_years(db, user.id)[:2] == [2027, 2026]
        assert (
            db.query(UserReportingYear)
            .filter_by(user_id=user.id, year=2027, is_default=True)
            .one()
        )
    finally:
        db.close()


def test_reporting_year_preferences_are_isolated_by_user(app):
    db = SessionLocal()
    try:
        admin = _admin(db)
        teacher = User(
            username="teacher-year-test",
            full_name="Teacher",
            password_hash="unused",
        )
        db.add(teacher)
        db.commit()
        db.refresh(teacher)

        set_user_default_year(db, admin.id, 2027)

        assert get_user_default_year(db, admin.id) == 2027
        assert get_user_default_year(db, teacher.id) == current_reporting_year()
        assert 2027 not in get_user_reporting_years(db, teacher.id)
    finally:
        db.close()


def test_user_can_remove_empty_year_and_default_falls_back_to_current(app):
    db = SessionLocal()
    try:
        user = _admin(db)
        set_user_default_year(db, user.id, 2027)

        remove_user_reporting_year(db, user.id, 2027)

        assert get_user_default_year(db, user.id) == current_reporting_year()
        assert 2027 not in get_user_reporting_years(db, user.id)
    finally:
        db.close()


def test_current_natural_year_cannot_be_removed(app):
    db = SessionLocal()
    try:
        user = _admin(db)
        with pytest.raises(ReportingYearProtectedError):
            remove_user_reporting_year(
                db,
                user.id,
                current_reporting_year(),
            )
    finally:
        db.close()


def test_year_with_achievement_cannot_be_removed(app):
    db = SessionLocal()
    try:
        user = _admin(db)
        add_user_reporting_year(db, user.id, 2025)
        achievement = Achievement(
            user_id=user.id,
            year=2025,
            category="Teaching",
            subcategory="Award",
            claim_nature=ClaimNature.result.value,
            title="Protected achievement",
        )
        db.add(achievement)
        db.commit()

        with pytest.raises(ReportingYearInUseError):
            remove_user_reporting_year(db, user.id, 2025)

        assert db.query(Achievement).filter_by(title="Protected achievement").one()
        assert 2025 in get_user_reporting_years(db, user.id)
    finally:
        db.close()


def test_dashboard_year_routes_manage_preferences_and_default(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    add_response = client.post(
        "/reporting-years",
        data={"year": "2027"},
        follow_redirects=False,
    )
    assert add_response.status_code == 303
    assert add_response.headers["location"] == "/?year=2027&year_action=added"

    default_response = client.post(
        "/reporting-years/2027/default",
        follow_redirects=False,
    )
    assert default_response.status_code == 303
    assert default_response.headers["location"] == "/?year=2027&year_action=default"

    dashboard = client.get("/")
    achievements = client.get("/achievements")
    new_form = client.get("/achievements/new")
    assert "2027" in dashboard.text
    assert 'class="year-manager"' in dashboard.text
    assert "管理年度" in dashboard.text
    assert 'href="/achievements/new?year=2027"' in dashboard.text
    assert '<option value="2027" selected>' in achievements.text
    assert '<option value="2027" selected>' in new_form.text

    remove_response = client.post(
        "/reporting-years/2027/delete",
        follow_redirects=False,
    )
    assert remove_response.status_code == 303
    assert remove_response.headers["location"] == "/?year=2026&year_action=removed"


def test_dashboard_refuses_to_remove_year_with_achievement(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        user = _admin(db)
        db.add(
            Achievement(
                user_id=user.id,
                year=2025,
                category="Teaching",
                subcategory="Award",
                claim_nature=ClaimNature.result.value,
                title="Keep me",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/reporting-years/2025/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?year=2025&year_error=in_use"
    db = SessionLocal()
    try:
        assert db.query(Achievement).filter_by(title="Keep me").one()
    finally:
        db.close()


def test_personal_default_year_is_used_by_export_and_trial_pages(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        user = _admin(db)
        set_user_default_year(db, user.id, 2027)
    finally:
        db.close()

    export_page = client.get("/exports")
    trial_page = client.get("/trial-guide")

    assert 'href="/exports/2027/review"' in export_page.text
    assert "2027 年度" in trial_page.text
