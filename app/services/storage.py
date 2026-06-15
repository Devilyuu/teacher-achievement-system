from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_MB, UPLOAD_DIR


MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


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
    size = 0
    upload.file.seek(0)
    try:
        with stored_path.open("wb") as output:
            while True:
                chunk = upload.file.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError(
                        f"File exceeds {MAX_UPLOAD_MB}MB upload limit"
                    )
                output.write(chunk)
    except Exception:
        if stored_path.exists():
            stored_path.unlink()
        raise

    if size == 0:
        stored_path.unlink()
        raise ValueError("File is empty")
    return str(stored_path), size, ext


def delete_material_file(stored_path: str) -> None:
    upload_root = UPLOAD_DIR.resolve()
    path = Path(stored_path).resolve()
    if not path.is_relative_to(upload_root):
        raise ValueError("Stored material path is outside the upload directory")
    if path.is_file():
        path.unlink()
