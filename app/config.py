import os
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_FEISHU_SYNC_USERNAME = ""
DEFAULT_FEISHU_APP_ID = ""
DEFAULT_FEISHU_APP_SECRET = ""
DEFAULT_FEISHU_BASE_TOKEN = ""
DEFAULT_FEISHU_TABLE_ID = ""
DEFAULT_ACHIEVEMENT_AI_API_KEY = ""
DEFAULT_ACHIEVEMENT_AI_BASE_URL = "https://api.deepseek.com"
DEFAULT_ACHIEVEMENT_AI_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class PersonalIntegrationConfig:
    sync_username: str
    feishu_app_id: str = field(repr=False)
    feishu_app_secret: str = field(repr=False)
    feishu_base_token: str = field(repr=False)
    feishu_table_id: str = field(repr=False)
    ai_api_key: str = field(repr=False)
    ai_base_url: str
    ai_model: str

    def allows_username(self, username: str) -> bool:
        return bool(self.sync_username) and username == self.sync_username

    @property
    def feishu_ready(self) -> bool:
        return all(
            (
                self.feishu_app_id,
                self.feishu_app_secret,
                self.feishu_base_token,
                self.feishu_table_id,
            )
        )

    @property
    def ai_ready(self) -> bool:
        return all((self.ai_api_key, self.ai_base_url, self.ai_model))


def _environment_value(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def get_personal_integration_config() -> PersonalIntegrationConfig:
    return PersonalIntegrationConfig(
        sync_username=_environment_value(
            "FEISHU_SYNC_USERNAME",
            DEFAULT_FEISHU_SYNC_USERNAME,
        ),
        feishu_app_id=_environment_value(
            "FEISHU_APP_ID",
            DEFAULT_FEISHU_APP_ID,
        ),
        feishu_app_secret=_environment_value(
            "FEISHU_APP_SECRET",
            DEFAULT_FEISHU_APP_SECRET,
        ),
        feishu_base_token=_environment_value(
            "FEISHU_BASE_TOKEN",
            DEFAULT_FEISHU_BASE_TOKEN,
        ),
        feishu_table_id=_environment_value(
            "FEISHU_TABLE_ID",
            DEFAULT_FEISHU_TABLE_ID,
        ),
        ai_api_key=_environment_value(
            "ACHIEVEMENT_AI_API_KEY",
            DEFAULT_ACHIEVEMENT_AI_API_KEY,
        ),
        ai_base_url=_environment_value(
            "ACHIEVEMENT_AI_BASE_URL",
            DEFAULT_ACHIEVEMENT_AI_BASE_URL,
        ),
        ai_model=_environment_value(
            "ACHIEVEMENT_AI_MODEL",
            DEFAULT_ACHIEVEMENT_AI_MODEL,
        ),
    )


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
