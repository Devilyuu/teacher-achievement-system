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
