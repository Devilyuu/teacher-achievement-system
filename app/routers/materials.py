from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Achievement, Material, User
from app.security import get_current_user
from app.services.achievement_status import calculate_status
from app.services.storage import save_material_file


router = APIRouter(prefix="/materials", tags=["materials"])


def _achievement_for_user(db: Session, achievement_id: int, user: User) -> Achievement:
    achievement = (
        db.query(Achievement)
        .filter(Achievement.id == achievement_id, Achievement.user_id == user.id)
        .first()
    )
    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Achievement not found",
        )
    return achievement


@router.post("/upload")
def upload_material(
    achievement_id: int = Form(...),
    display_name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    try:
        stored_path, size, ext = save_material_file(
            achievement.year,
            user.id,
            achievement.id,
            file,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    next_index = (
        db.query(Material)
        .filter(Material.achievement_id == achievement.id)
        .count()
        + 1
    )
    material = Material(
        material_no=f"{achievement.id}-{next_index}",
        display_name=display_name.strip() or file.filename or "Uploaded material",
        description=description.strip(),
        original_filename=file.filename or "",
        stored_path=stored_path,
        file_ext=ext,
        file_size=size,
    )
    achievement.materials.append(material)
    achievement.status = calculate_status(achievement)

    db.add(material)
    db.commit()
    return RedirectResponse(
        f"/achievements/{achievement.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
