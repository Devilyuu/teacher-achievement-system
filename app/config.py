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
FEISHU_SYNC_USERNAME = os.environ.get("FEISHU_SYNC_USERNAME", "")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_BASE_TOKEN = os.environ.get("FEISHU_BASE_TOKEN", "")
FEISHU_TABLE_ID = os.environ.get("FEISHU_TABLE_ID", "")
ACHIEVEMENT_AI_API_KEY = os.environ.get("ACHIEVEMENT_AI_API_KEY", "")
ACHIEVEMENT_AI_BASE_URL = os.environ.get(
    "ACHIEVEMENT_AI_BASE_URL",
    "https://api.deepseek.com",
)
ACHIEVEMENT_AI_MODEL = os.environ.get(
    "ACHIEVEMENT_AI_MODEL",
    "deepseek-chat",
)
MAX_UPLOAD_MB = 50
MAX_BATCH_UPLOAD_FILES = 10
MAX_BATCH_UPLOAD_MB = MAX_UPLOAD_MB * MAX_BATCH_UPLOAD_FILES
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
