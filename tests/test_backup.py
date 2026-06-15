import json
import sqlite3
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password
from app.services.backup_builder import build_system_backup


def _create_sqlite_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO sample (value) VALUES ('backup-row')")
        connection.commit()
    finally:
        connection.close()


def test_backup_builder_creates_openable_snapshot_materials_and_manifest(tmp_path):
    database_path = tmp_path / "database" / "app.sqlite3"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    _create_sqlite_database(database_path)
    (upload_dir / "2026" / "1").mkdir(parents=True)
    (upload_dir / "2026" / "1" / "proof.pdf").write_bytes(b"proof")
    (upload_dir / "2026" / "1" / "note.docx").write_bytes(b"note")
    export_dir.mkdir()
    (export_dir / "old-export.zip").write_bytes(b"must not be included")

    backup_path = build_system_backup(database_path, upload_dir, export_dir)

    assert backup_path.exists()
    with ZipFile(backup_path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("backup_manifest.json"))
        archive.extract("database/app.sqlite3", tmp_path / "restore")

    assert "database/app.sqlite3" in names
    assert "uploads/2026/1/proof.pdf" in names
    assert "uploads/2026/1/note.docx" in names
    assert not any("old-export.zip" in name for name in names)
    assert manifest["material_file_count"] == 2
    assert manifest["material_total_bytes"] == 9

    restored = sqlite3.connect(tmp_path / "restore" / "database" / "app.sqlite3")
    try:
        assert restored.execute("SELECT value FROM sample").fetchone()[0] == "backup-row"
    finally:
        restored.close()


def test_backup_builder_handles_empty_upload_directory(tmp_path):
    database_path = tmp_path / "database" / "app.sqlite3"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"
    _create_sqlite_database(database_path)

    backup_path = build_system_backup(database_path, upload_dir, export_dir)

    with ZipFile(backup_path) as archive:
        manifest = json.loads(archive.read("backup_manifest.json"))
        assert archive.namelist() == [
            "database/app.sqlite3",
            "backup_manifest.json",
        ]
    assert manifest["material_file_count"] == 0
    assert manifest["material_total_bytes"] == 0
