from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    Achievement,
    AchievementStatus,
    ExportRecord,
    User,
)
from app.services.export_builder import build_personal_export


def generate_personal_export(
    db: Session,
    user: User,
    year: int,
) -> tuple[ExportRecord, Path]:
    achievements = (
        db.query(Achievement)
        .filter(Achievement.user_id == user.id, Achievement.year == year)
        .order_by(Achievement.id)
        .all()
    )
    zip_path = build_personal_export(db, user, year)

    record = (
        db.query(ExportRecord)
        .filter(ExportRecord.user_id == user.id, ExportRecord.year == year)
        .one_or_none()
    )
    if record is None:
        record = ExportRecord(user_id=user.id, year=year)
        db.add(record)

    record.file_name = zip_path.name
    record.file_path = str(zip_path)
    record.achievement_count = len(achievements)
    record.material_count = sum(len(item.materials) for item in achievements)
    record.file_size = zip_path.stat().st_size
    record.generated_at = datetime.utcnow()

    for achievement in achievements:
        achievement.status = AchievementStatus.exported.value
        achievement.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(record)
    return record, zip_path
