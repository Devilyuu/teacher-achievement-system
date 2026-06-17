import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TEACHER_ACHIEVEMENT_DATA_DIR", BASE_DIR / "data"))
DATABASE_PATH = DATA_DIR / "database" / "app.sqlite3"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
USER_IMPORT_DIR = DATA_DIR / "imports" / "users"
SECRET_KEY = os.environ.get(
    "TEACHER_ACHIEVEMENT_SECRET_KEY",
    "change-this-local-dev-secret",
)
MAX_UPLOAD_MB = 50
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".zip",
    ".rar",
    ".7z",
}
