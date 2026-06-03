import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import ALLOWED_EXTENSIONS, UPLOAD_DIR


def safe_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {ext or '<none>'}")
    return ext


def save_material_file(
    year: int,
    user_id: int,
    achievement_id: int,
    upload: UploadFile,
) -> tuple[str, int, str]:
    ext = safe_extension(upload.filename or "")
    upload_dir = UPLOAD_DIR / str(year) / str(user_id) / str(achievement_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_path = upload_dir / f"{uuid4().hex}{ext}"
    upload.file.seek(0)
    with stored_path.open("wb") as output:
        shutil.copyfileobj(upload.file, output)

    size = stored_path.stat().st_size
    return str(stored_path), size, ext
