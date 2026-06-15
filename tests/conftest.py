from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import close_all_sessions

from app import database
from app.database import SessionLocal


@pytest.fixture
def app(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "database" / "app.sqlite3"
    database_path.parent.mkdir(parents=True)

    test_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal.configure(bind=test_engine)
    monkeypatch.setattr(database, "engine", test_engine)

    from app import main, schema_updates
    from app.routers import admin

    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(schema_updates, "engine", test_engine)
    monkeypatch.setattr(admin, "DATABASE_PATH", database_path)

    try:
        yield main.create_app()
    finally:
        close_all_sessions()
        test_engine.dispose()
