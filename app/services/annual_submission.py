from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Achievement, AnnualSubmission, ExportRecord, Material, User


ANNUAL_SUBMISSION_SUBMITTED = "submitted"
ANNUAL_STATUS_NOT_STARTED = "未开始"
ANNUAL_STATUS_IN_PROGRESS = "整理中"
ANNUAL_STATUS_SUBMITTED = "已提交"
ANNUAL_STATUS_EXPORTED = "已导出"
ANNUAL_STATUS_OPTIONS = [
    ANNUAL_STATUS_NOT_STARTED,
    ANNUAL_STATUS_IN_PROGRESS,
    ANNUAL_STATUS_SUBMITTED,
    ANNUAL_STATUS_EXPORTED,
]


@dataclass(frozen=True)
class AnnualSubmissionState:
    status: str
    achievement_count: int
    submitted_at: datetime | None = None
    exported_at: datetime | None = None


def confirm_annual_submission(
    db: Session,
    user: User,
    year: int,
) -> AnnualSubmission:
    now = datetime.utcnow()
    record = (
        db.query(AnnualSubmission)
        .filter(AnnualSubmission.user_id == user.id, AnnualSubmission.year == year)
        .one_or_none()
    )
    if record is None:
        record = AnnualSubmission(user_id=user.id, year=year)
        db.add(record)
    record.status = ANNUAL_SUBMISSION_SUBMITTED
    record.submitted_at = now
    record.updated_at = now
    db.commit()
    db.refresh(record)
    return record


def get_annual_submission_state(
    db: Session,
    user_id: int,
    year: int,
) -> AnnualSubmissionState:
    achievement_count = (
        db.query(func.count(Achievement.id))
        .filter(Achievement.user_id == user_id, Achievement.year == year)
        .scalar()
        or 0
    )
    submission = (
        db.query(AnnualSubmission)
        .filter(AnnualSubmission.user_id == user_id, AnnualSubmission.year == year)
        .one_or_none()
    )
    if submission is None:
        status = (
            ANNUAL_STATUS_IN_PROGRESS
            if achievement_count
            else ANNUAL_STATUS_NOT_STARTED
        )
        return AnnualSubmissionState(status=status, achievement_count=achievement_count)

    latest_activity_at = _latest_activity_at(db, user_id, year)
    latest_export_at = _latest_export_at(db, user_id, year)
    if (
        latest_export_at is not None
        and latest_export_at >= submission.submitted_at
        and (
            latest_activity_at is None
            or latest_activity_at <= latest_export_at
        )
    ):
        return AnnualSubmissionState(
            status=ANNUAL_STATUS_EXPORTED,
            achievement_count=achievement_count,
            submitted_at=submission.submitted_at,
            exported_at=latest_export_at,
        )
    if latest_activity_at is not None and latest_activity_at > submission.submitted_at:
        return AnnualSubmissionState(
            status=ANNUAL_STATUS_IN_PROGRESS,
            achievement_count=achievement_count,
            submitted_at=submission.submitted_at,
            exported_at=latest_export_at,
        )
    return AnnualSubmissionState(
        status=ANNUAL_STATUS_SUBMITTED,
        achievement_count=achievement_count,
        submitted_at=submission.submitted_at,
        exported_at=latest_export_at,
    )


def _latest_activity_at(
    db: Session,
    user_id: int,
    year: int,
) -> datetime | None:
    latest_achievement_at = (
        db.query(func.max(Achievement.updated_at))
        .filter(Achievement.user_id == user_id, Achievement.year == year)
        .scalar()
    )
    latest_material_at = (
        db.query(func.max(Material.uploaded_at))
        .join(Achievement)
        .filter(Achievement.user_id == user_id, Achievement.year == year)
        .scalar()
    )
    values = [
        value
        for value in [latest_achievement_at, latest_material_at]
        if value is not None
    ]
    return max(values) if values else None


def _latest_export_at(
    db: Session,
    user_id: int,
    year: int,
) -> datetime | None:
    return (
        db.query(func.max(ExportRecord.generated_at))
        .filter(ExportRecord.user_id == user_id, ExportRecord.year == year)
        .scalar()
    )
