import json
import sqlite3
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.config import UPLOAD_DIR
from app.database import SessionLocal
from app.models import Role, User
from app.security import create_auth_cookie, hash_password
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


def _login_admin(client: TestClient) -> None:
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )


def _create_teacher() -> int:
    db = SessionLocal()
    try:
        user = User(
            username=f"backup-teacher-{uuid4().hex}",
            full_name="备份权限教师",
            department="备份测试学院",
            role=Role.teacher.value,
            password_hash=hash_password("password123"),
        )
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def test_backup_page_and_download_require_admin(app):
    unauthenticated = TestClient(app).get(
        "/admin/backup",
        follow_redirects=False,
    )
    assert unauthenticated.status_code in {303, 401}

    teacher_client = TestClient(app)
    teacher_client.cookies.set("user_id", create_auth_cookie(_create_teacher()))
    assert teacher_client.get("/admin/backup").status_code == 403
    assert teacher_client.get("/admin/backup/download").status_code == 403


def test_admin_can_open_backup_page_and_download_complete_zip(app):
    client = TestClient(app)
    _login_admin(client)
    marker = f"backup-marker-{uuid4().hex}.txt"
    marker_path = UPLOAD_DIR / "test-backup-route" / marker
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("route backup", encoding="utf-8")

    page = client.get("/admin/backup")
    download = client.get("/admin/backup/download")

    assert page.status_code == 200
    assert "系统备份" in page.text
    assert "下载完整备份" in page.text
    assert download.status_code == 200
    assert download.headers["content-type"] in {
        "application/zip",
        "application/x-zip-compressed",
    }
    with ZipFile(BytesIO(download.content)) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("backup_manifest.json"))
    assert "database/app.sqlite3" in names
    assert f"uploads/test-backup-route/{marker}" in names
    assert manifest["material_file_count"] >= 1
