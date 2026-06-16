from pathlib import Path

from fastapi import HTTPException, status

from app.config import UPLOAD_DIR
from app.models import Material


PREVIEW_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
PREVIEW_EXTENSIONS = set(PREVIEW_MEDIA_TYPES)


def preview_media_type(material: Material) -> str:
    media_type = PREVIEW_MEDIA_TYPES.get((material.file_ext or "").lower())
    if not media_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material preview is not supported",
        )
    return media_type


def safe_material_path(material: Material) -> Path:
    upload_root = UPLOAD_DIR.resolve()
    path = Path(material.stored_path).resolve()
    if not path.is_relative_to(upload_root) or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material file not found",
        )
    return path
