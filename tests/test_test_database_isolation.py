from pathlib import Path

from app.config import DATABASE_PATH
from app.database import SessionLocal


def test_pytest_uses_database_outside_application_data_directory(app):
    test_database = Path(SessionLocal.kw["bind"].url.database).resolve()

    assert test_database != DATABASE_PATH.resolve()
    assert "pytest-" in str(test_database)
