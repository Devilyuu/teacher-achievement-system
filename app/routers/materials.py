from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Achievement, Material, User
from app.security import get_current_user
from app.services.achievement_status import calculate_status
from app.services.storage import delete_material_file, save_material_file


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


def _material_for_user(db: Session, material_id: int, user: User) -> Material:
    material = (
        db.query(Material)
        .join(Achievement)
        .filter(Material.id == material_id, Achievement.user_id == user.id)
        .first()
    )
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material not found",
        )
    return material


def _filename_display_name(filename: str | None) -> str:
    stem = Path(filename or "").stem.strip()
    return stem or "支撑材料"


def _next_material_index(achievement: Achievement) -> int:
    prefix = f"{achievement.id}-"
    numbers: list[int] = []
    for material in achievement.materials:
        if material.material_no.startswith(prefix):
            suffix = material.material_no.removeprefix(prefix)
            if suffix.isdigit():
                numbers.append(int(suffix))
    return (max(numbers) if numbers else 0) + 1


@router.post("/upload")
def upload_material(
    achievement_id: int = Form(...),
    display_name: str = Form(""),
    description: str = Form(""),
    files: list[UploadFile] = File(..., alias="file"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    next_index = _next_material_index(achievement)
    saved_paths: list[str] = []
    uploaded_count = 0
    failed_messages: list[str] = []

    for file in files:
        try:
            stored_path, size, ext = save_material_file(
                achievement.year,
                user.id,
                achievement.id,
                file,
            )
        except ValueError as exc:
            failed_messages.append(f"{file.filename or '未命名文件'}：{exc}")
            continue

        material_name = (
            display_name.strip()
            if len(files) == 1 and display_name.strip()
            else _filename_display_name(file.filename)
        )
        material = Material(
            material_no=f"{achievement.id}-{next_index}",
            display_name=material_name,
            description=description.strip(),
            original_filename=file.filename or "",
            stored_path=stored_path,
            file_ext=ext,
            file_size=size,
        )
        next_index += 1
        uploaded_count += 1
        saved_paths.append(stored_path)
        achievement.materials.append(material)
        db.add(material)

    if uploaded_count:
        achievement.status = calculate_status(achievement)

    try:
        db.commit()
    except Exception:
        db.rollback()
        for stored_path in saved_paths:
            delete_material_file(stored_path)
        raise

    query = urlencode(
        {
            "uploaded": uploaded_count,
            "failed": len(failed_messages),
            "errors": "；".join(failed_messages),
        }
    )
    return RedirectResponse(
        f"/achievements/{achievement.id}?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{material_id}/download")
def download_material(
    material_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _material_for_user(db, material_id, user)
    path = Path(material.stored_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material file not found",
        )
    return FileResponse(
        path,
        filename=material.original_filename,
        media_type="application/octet-stream",
    )


@router.post("/{material_id}/replace")
def replace_material(
    material_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _material_for_user(db, material_id, user)
    achievement = material.achievement
    try:
        stored_path, size, ext = save_material_file(
            achievement.year,
            user.id,
            achievement.id,
            file,
        )
    except ValueError as exc:
        query = urlencode({"replace_error": f"{file.filename or '未命名文件'}：{exc}"})
        return RedirectResponse(
            f"/achievements/{achievement.id}?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    old_path = material.stored_path
    material.original_filename = file.filename or ""
    material.stored_path = stored_path
    material.file_ext = ext
    material.file_size = size
    material.uploaded_at = datetime.utcnow()
    db.commit()
    delete_material_file(old_path)
    return RedirectResponse(
        f"/achievements/{achievement.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{material_id}/delete")
def delete_material(
    material_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = _material_for_user(db, material_id, user)
    achievement = material.achievement
    achievement_id = achievement.id
    stored_path = material.stored_path

    achievement.materials.remove(material)
    db.flush()
    achievement.status = calculate_status(achievement)
    db.commit()
    delete_material_file(stored_path)
    return RedirectResponse(
        f"/achievements/{achievement_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
