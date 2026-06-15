from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import UPLOAD_DIR
from app.database import SessionLocal
from app.models import Achievement, AchievementStatus, ClaimNature, Material, Role, User
from app.security import hash_password
from app.services.storage import safe_extension


def _login_admin(client: TestClient) -> None:
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )


def _create_user(db, username: str) -> User:
    user = User(
        username=username,
        full_name=username,
        department="Test",
        role=Role.teacher.value,
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.flush()
    return user


def _complete_process_achievement(user_id: int, title: str) -> Achievement:
    return Achievement(
        user_id=user_id,
        year=2026,
        category="Other",
        subcategory="Custom",
        claim_nature=ClaimNature.process.value,
        title=title,
        current_stage="Completed",
        claimed_score=2,
    )


def test_safe_extension_accepts_allowed_extensions():
    assert safe_extension("proof.PDF") == ".pdf"
    assert safe_extension("photo.JPG") == ".jpg"


def test_safe_extension_rejects_unsupported_extension():
    try:
        safe_extension("installer.exe")
    except ValueError as exc:
        assert "Unsupported file extension" in str(exc)
    else:
        raise AssertionError("safe_extension should reject .exe files")


def test_authenticated_user_can_upload_material_to_owned_achievement(app):
    client = TestClient(app)
    _login_admin(client)

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = _complete_process_achievement(admin.id, "Upload owned proof")
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.post(
        "/materials/upload",
        data={
            "achievement_id": str(achievement_id),
            "display_name": "Proof PDF",
            "description": "Signed proof",
        },
        files={"file": ("proof.PDF", BytesIO(b"%PDF-1.4 proof"), "application/pdf")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/achievements/{achievement_id}"

    db = SessionLocal()
    try:
        material = db.query(Material).filter_by(achievement_id=achievement_id).one()
        achievement = db.get(Achievement, achievement_id)

        assert material.material_no == f"{achievement_id}-1"
        assert material.display_name == "Proof PDF"
        assert material.original_filename == "proof.PDF"
        assert material.file_ext == ".pdf"
        assert material.file_size == len(b"%PDF-1.4 proof")
        assert Path(material.stored_path).exists()
        assert Path(material.stored_path).is_relative_to(UPLOAD_DIR)
        assert achievement.status == AchievementStatus.ready.value
    finally:
        db.close()


def test_uploading_to_another_users_achievement_is_blocked(app):
    client = TestClient(app)
    _login_admin(client)

    db = SessionLocal()
    try:
        other_user = _create_user(db, f"other-material-owner-{uuid4().hex}")
        achievement = _complete_process_achievement(other_user.id, "Other owned proof")
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.post(
        "/materials/upload",
        data={
            "achievement_id": str(achievement_id),
            "display_name": "Forbidden proof",
            "description": "",
        },
        files={"file": ("proof.pdf", BytesIO(b"not yours"), "application/pdf")},
        follow_redirects=False,
    )

    assert response.status_code in {303, 403, 404}

    db = SessionLocal()
    try:
        assert db.query(Material).filter_by(achievement_id=achievement_id).count() == 0
    finally:
        db.close()


def _create_material_file(filename: str, content: bytes) -> Path:
    directory = UPLOAD_DIR / "test-material-lifecycle" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    source_path = directory / filename
    source_path.write_bytes(content)
    return source_path


def _create_owned_material(db, user_id: int, source_path: Path) -> tuple[int, int]:
    achievement = _complete_process_achievement(user_id, f"Material lifecycle {uuid4().hex}")
    db.add(achievement)
    db.flush()
    material = Material(
        achievement_id=achievement.id,
        material_no=f"{achievement.id}-1",
        display_name="Original proof",
        description="Original description",
        original_filename=source_path.name,
        stored_path=str(source_path),
        file_ext=source_path.suffix,
        file_size=source_path.stat().st_size,
    )
    achievement.materials.append(material)
    achievement.status = AchievementStatus.ready.value
    db.add(material)
    db.commit()
    return achievement.id, material.id


def test_owner_can_download_material(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("download-proof.pdf", b"%PDF-1.4 downloadable")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        _, material_id = _create_owned_material(db, admin.id, source_path)
    finally:
        db.close()

    response = client.get(f"/materials/{material_id}/download")

    assert response.status_code == 200
    assert response.content == source_path.read_bytes()
    assert "download-proof.pdf" in response.headers["content-disposition"]


def test_material_detail_shows_file_management_actions(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("detail-proof.pdf", b"detail proof")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, material_id = _create_owned_material(db, admin.id, source_path)
    finally:
        db.close()

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert f"/materials/{material_id}/download" in response.text
    assert f"/materials/{material_id}/replace" in response.text
    assert f"/materials/{material_id}/delete" in response.text


def test_owner_can_replace_material_without_changing_material_number(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("old-proof.pdf", b"old proof")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, material_id = _create_owned_material(db, admin.id, source_path)
        original_number = db.get(Material, material_id).material_no
    finally:
        db.close()

    response = client.post(
        f"/materials/{material_id}/replace",
        files={"file": ("new-proof.docx", BytesIO(b"new proof"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/achievements/{achievement_id}"
    db = SessionLocal()
    try:
        material = db.get(Material, material_id)
        assert material.material_no == original_number
        assert material.original_filename == "new-proof.docx"
        assert material.file_ext == ".docx"
        assert Path(material.stored_path).read_bytes() == b"new proof"
        assert not source_path.exists()
    finally:
        db.close()


def test_owner_can_delete_material_and_achievement_returns_to_needs_info(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("delete-proof.pdf", b"delete me")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, material_id = _create_owned_material(db, admin.id, source_path)
    finally:
        db.close()

    response = client.post(
        f"/materials/{material_id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/achievements/{achievement_id}"
    db = SessionLocal()
    try:
        assert db.get(Material, material_id) is None
        assert db.get(Achievement, achievement_id).status == AchievementStatus.needs_info.value
        assert not source_path.exists()
    finally:
        db.close()


def test_user_cannot_download_replace_or_delete_another_users_material(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("other-proof.pdf", b"private proof")

    db = SessionLocal()
    try:
        other_user = _create_user(db, f"other-owner-{uuid4().hex}")
        _, material_id = _create_owned_material(db, other_user.id, source_path)
    finally:
        db.close()

    download = client.get(f"/materials/{material_id}/download", follow_redirects=False)
    replace = client.post(
        f"/materials/{material_id}/replace",
        files={"file": ("replacement.pdf", BytesIO(b"forbidden"), "application/pdf")},
        follow_redirects=False,
    )
    delete = client.post(f"/materials/{material_id}/delete", follow_redirects=False)

    assert download.status_code == 404
    assert replace.status_code == 404
    assert delete.status_code == 404
    assert source_path.exists()
