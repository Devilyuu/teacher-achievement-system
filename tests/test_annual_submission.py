from datetime import datetime, timedelta
from uuid import uuid4

from app.database import SessionLocal
from app.models import (
    Achievement,
    AnnualSubmission,
    ClaimNature,
    ExportRecord,
    Material,
    Role,
    User,
)
from app.security import hash_password
from app.services.annual_submission import (
    ANNUAL_STATUS_EXPORTED,
    ANNUAL_STATUS_IN_PROGRESS,
    ANNUAL_STATUS_NOT_STARTED,
    ANNUAL_STATUS_SUBMITTED,
    confirm_annual_submission,
    get_annual_submission_state,
)


def _create_teacher(db, username: str | None = None) -> User:
    user = User(
        username=username or f"annual-{uuid4().hex}",
        full_name=f"Annual Teacher {uuid4().hex[:5]}",
        department="Annual Test",
        role=Role.teacher.value,
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.flush()
    return user


def _add_achievement(
    db,
    user: User,
    *,
    year: int = 2026,
    updated_at: datetime | None = None,
) -> Achievement:
    timestamp = updated_at or datetime.utcnow()
    achievement = Achievement(
        user_id=user.id,
        year=year,
        category="教学",
        subcategory="教学成果",
        claim_nature=ClaimNature.result.value,
        title=f"Annual achievement {uuid4().hex[:5]}",
        claimed_score=1,
        updated_at=timestamp,
    )
    db.add(achievement)
    db.flush()
    return achievement


def test_annual_status_is_not_started_without_records_or_submission(app):
    db = SessionLocal()
    try:
        user = _create_teacher(db)
        db.commit()

        state = get_annual_submission_state(db, user.id, 2026)

        assert state.status == ANNUAL_STATUS_NOT_STARTED
        assert state.achievement_count == 0
        assert state.submitted_at is None
    finally:
        db.close()


def test_annual_status_is_in_progress_with_records_but_no_submission(app):
    db = SessionLocal()
    try:
        user = _create_teacher(db)
        _add_achievement(db, user)
        db.commit()

        state = get_annual_submission_state(db, user.id, 2026)

        assert state.status == ANNUAL_STATUS_IN_PROGRESS
        assert state.achievement_count == 1
        assert state.submitted_at is None
    finally:
        db.close()


def test_annual_status_is_submitted_after_teacher_confirms(app):
    db = SessionLocal()
    try:
        user = _create_teacher(db)
        _add_achievement(db, user)
        db.commit()

        record = confirm_annual_submission(db, user, 2026)
        state = get_annual_submission_state(db, user.id, 2026)

        assert record.status == "submitted"
        assert state.status == ANNUAL_STATUS_SUBMITTED
        assert state.submitted_at == record.submitted_at
        assert db.query(AnnualSubmission).filter_by(user_id=user.id, year=2026).count() == 1
    finally:
        db.close()


def test_reconfirming_annual_submission_refreshes_existing_record(app):
    db = SessionLocal()
    try:
        user = _create_teacher(db)
        _add_achievement(db, user)
        db.commit()

        first = confirm_annual_submission(db, user, 2026)
        first_id = first.id
        first.submitted_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
        previous_submitted_at = first.submitted_at

        refreshed = confirm_annual_submission(db, user, 2026)

        assert refreshed.id == first_id
        assert refreshed.submitted_at > previous_submitted_at
        assert db.query(AnnualSubmission).filter_by(user_id=user.id, year=2026).count() == 1
    finally:
        db.close()


def test_annual_status_returns_to_in_progress_when_record_changes_after_submission(app):
    db = SessionLocal()
    try:
        user = _create_teacher(db)
        achievement = _add_achievement(db, user)
        db.commit()
        record = confirm_annual_submission(db, user, 2026)

        achievement.updated_at = record.submitted_at + timedelta(minutes=5)
        db.commit()

        state = get_annual_submission_state(db, user.id, 2026)

        assert state.status == ANNUAL_STATUS_IN_PROGRESS
    finally:
        db.close()


def test_annual_status_returns_to_in_progress_when_material_changes_after_submission(app):
    db = SessionLocal()
    try:
        user = _create_teacher(db)
        achievement = _add_achievement(db, user)
        material = Material(
            achievement_id=achievement.id,
            material_no=f"{achievement.id}-1",
            display_name="Proof",
            original_filename="proof.pdf",
            stored_path="data/uploads/proof.pdf",
            file_ext=".pdf",
            file_size=10,
        )
        achievement.materials.append(material)
        db.add(material)
        db.commit()
        record = confirm_annual_submission(db, user, 2026)

        material.uploaded_at = record.submitted_at + timedelta(minutes=5)
        db.commit()

        state = get_annual_submission_state(db, user.id, 2026)

        assert state.status == ANNUAL_STATUS_IN_PROGRESS
    finally:
        db.close()


def test_annual_status_is_exported_when_latest_export_follows_submission(app):
    db = SessionLocal()
    try:
        user = _create_teacher(db)
        _add_achievement(db, user)
        db.commit()
        record = confirm_annual_submission(db, user, 2026)
        export_record = ExportRecord(
            user_id=user.id,
            year=2026,
            file_name="annual.zip",
            file_path="data/exports/annual.zip",
            generated_at=record.submitted_at + timedelta(minutes=5),
        )
        db.add(export_record)
        db.commit()

        state = get_annual_submission_state(db, user.id, 2026)

        assert state.status == ANNUAL_STATUS_EXPORTED
        assert state.exported_at == export_record.generated_at
    finally:
        db.close()
