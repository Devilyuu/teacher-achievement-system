from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import Achievement, AchievementStatus, ExportRecord, User
from app.security import get_current_user
from app.services.export_history import generate_personal_export
from app.services.reporting_year import get_user_default_year


router = APIRouter(prefix="/exports", tags=["exports"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _format_file_size(file_size: int) -> str:
    if file_size >= 1024 * 1024:
        return f"{file_size / (1024 * 1024):.1f} MB"
    if file_size >= 1024:
        return f"{file_size / 1024:.1f} KB"
    return f"{file_size} B"


@router.get("")
def export_history(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(ExportRecord)
        .filter(ExportRecord.user_id == user.id)
        .order_by(ExportRecord.year.desc())
        .all()
    )
    record_rows = [
        {
            "record": record,
            "file_exists": Path(record.file_path).is_file(),
            "file_size_display": _format_file_size(record.file_size),
        }
        for record in records
    ]
    return templates.TemplateResponse(
        request,
        "exports/list.html",
        {
            "user": user,
            "records": record_rows,
            "current_year": get_user_default_year(db, user.id),
        },
    )


@router.get("/records/{record_id}/download")
def download_recorded_export(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(ExportRecord)
        .filter(
            ExportRecord.id == record_id,
            ExportRecord.user_id == user.id,
        )
        .one_or_none()
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    file_path = Path(record.file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=record.file_name,
    )


@router.get("/{year}/review")
def review_personal_export(
    year: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievements = (
        db.query(Achievement)
        .filter(Achievement.user_id == user.id, Achievement.year == year)
        .order_by(Achievement.id)
        .all()
    )
    ready_statuses = {
        AchievementStatus.ready.value,
        AchievementStatus.exported.value,
    }
    needs_attention = [
        achievement
        for achievement in achievements
        if achievement.status not in ready_statuses
    ]
    return templates.TemplateResponse(
        request,
        "exports/review.html",
        {
            "user": user,
            "year": year,
            "achievements": achievements,
            "ready_count": len(achievements) - len(needs_attention),
            "needs_attention": needs_attention,
            "material_count": sum(len(achievement.materials) for achievement in achievements),
        },
    )


@router.get("/{year}/personal")
def export_personal(
    year: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, zip_path = generate_personal_export(db, user, year)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )
