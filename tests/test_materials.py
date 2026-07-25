from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import UPLOAD_DIR
from app.database import SessionLocal
from app.models import Achievement, AchievementStatus, ClaimNature, Material, Role, User
from app.security import hash_password
from app.services.storage import safe_extension, save_material_file


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


def test_save_material_file_rejects_empty_file_without_creating_file(app):
    user_id = int(uuid4().hex[:8], 16)
    achievement_id = int(uuid4().hex[:8], 16)
    upload = type(
        "Upload",
        (),
        {
            "filename": "empty.pdf",
            "file": BytesIO(b""),
        },
    )()

    try:
        save_material_file(2026, user_id, achievement_id, upload)
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("empty material files should be rejected")

    upload_dir = UPLOAD_DIR / "2026" / str(user_id) / str(achievement_id)
    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


def test_save_material_file_rejects_file_above_configured_limit_without_leftover(app, monkeypatch):
    user_id = int(uuid4().hex[:8], 16)
    achievement_id = int(uuid4().hex[:8], 16)
    monkeypatch.setattr("app.services.storage.MAX_UPLOAD_BYTES", 4)
    upload = type(
        "Upload",
        (),
        {
            "filename": "too-large.pdf",
            "file": BytesIO(b"12345"),
        },
    )()

    try:
        save_material_file(2026, user_id, achievement_id, upload)
    except ValueError as exc:
        assert "exceeds" in str(exc).lower()
    else:
        raise AssertionError("oversized material files should be rejected")

    upload_dir = UPLOAD_DIR / "2026" / str(user_id) / str(achievement_id)
    assert not upload_dir.exists() or list(upload_dir.iterdir()) == []


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
    assert response.headers["location"].startswith(f"/achievements/{achievement_id}")
    assert "uploaded=1" in response.headers["location"]

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

    detail_response = client.get(response.headers["location"])

    assert detail_response.status_code == 200
    assert "当前成果已满足基础申报条件" in detail_response.text
    assert "最终认定仍以线下审核为准" in detail_response.text


def test_authenticated_user_can_upload_multiple_materials_with_filename_names(app):
    client = TestClient(app)
    _login_admin(client)

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = _complete_process_achievement(admin.id, "Batch upload proofs")
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.post(
        "/materials/upload",
        data={
            "achievement_id": str(achievement_id),
            "display_name": "",
            "description": "batch upload",
        },
        files=[
            ("file", ("award-certificate.pdf", BytesIO(b"award"), "application/pdf")),
            ("file", ("platform screenshot.PNG", BytesIO(b"image"), "image/png")),
        ],
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/achievements/{achievement_id}")
    assert "uploaded=2" in response.headers["location"]

    db = SessionLocal()
    try:
        materials = (
            db.query(Material)
            .filter_by(achievement_id=achievement_id)
            .order_by(Material.material_no)
            .all()
        )
        achievement = db.get(Achievement, achievement_id)

        assert [material.material_no for material in materials] == [
            f"{achievement_id}-1",
            f"{achievement_id}-2",
        ]
        assert [material.display_name for material in materials] == [
            "award-certificate",
            "platform screenshot",
        ]
        assert [material.original_filename for material in materials] == [
            "award-certificate.pdf",
            "platform screenshot.PNG",
        ]
        assert achievement.status == AchievementStatus.ready.value
    finally:
        db.close()


def test_batch_upload_rejects_more_than_ten_files_without_storing_anything(app):
    client = TestClient(app)
    _login_admin(client)

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = _complete_process_achievement(admin.id, "Oversized batch")
        db.add(achievement)
        db.commit()
        admin_id = admin.id
        achievement_id = achievement.id
    finally:
        db.close()

    upload_dir = UPLOAD_DIR / "2026" / str(admin_id) / str(achievement_id)
    existing_paths = set(upload_dir.iterdir()) if upload_dir.exists() else set()

    response = client.post(
        "/materials/upload",
        data={"achievement_id": str(achievement_id)},
        files=[
            (
                "file",
                (f"proof-{index}.pdf", BytesIO(b"valid"), "application/pdf"),
            )
            for index in range(11)
        ],
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/achievements/{achievement_id}")
    assert "uploaded=0" in response.headers["location"]
    assert "failed=11" in response.headers["location"]

    detail_response = client.get(response.headers["location"])
    assert "单次批量上传最多支持 10 个文件，总大小不超过 500MB" in detail_response.text

    db = SessionLocal()
    try:
        assert db.query(Material).filter_by(achievement_id=achievement_id).count() == 0
    finally:
        db.close()

    current_paths = set(upload_dir.iterdir()) if upload_dir.exists() else set()
    assert current_paths == existing_paths


def test_batch_upload_keeps_valid_files_and_reports_invalid_files(app):
    client = TestClient(app)
    _login_admin(client)

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = _complete_process_achievement(admin.id, "Partial batch upload")
        db.add(achievement)
        db.commit()
        admin_id = admin.id
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.post(
        "/materials/upload",
        data={"achievement_id": str(achievement_id)},
        files=[
            ("file", ("valid-proof.pdf", BytesIO(b"valid"), "application/pdf")),
            ("file", ("unsafe.exe", BytesIO(b"nope"), "application/octet-stream")),
        ],
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/achievements/{achievement_id}")
    assert "uploaded=1" in response.headers["location"]
    assert "failed=1" in response.headers["location"]
    assert "unsafe.exe" in response.headers["location"]

    db = SessionLocal()
    try:
        material = db.query(Material).filter_by(achievement_id=achievement_id).one()
        assert material.display_name == "valid-proof"
        assert material.original_filename == "valid-proof.pdf"
        assert Path(material.stored_path).exists()
        assert not list((UPLOAD_DIR / "2026" / str(admin_id) / str(achievement_id)).glob("*.exe"))
    finally:
        db.close()


def test_batch_upload_continues_from_highest_existing_material_number(app):
    client = TestClient(app)
    _login_admin(client)

    first_path = _create_material_file("first.pdf", b"first")
    third_path = _create_material_file("third.pdf", b"third")
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = _complete_process_achievement(admin.id, "Continue material number")
        db.add(achievement)
        db.flush()
        first = Material(
            achievement_id=achievement.id,
            material_no=f"{achievement.id}-1",
            display_name="First",
            original_filename=first_path.name,
            stored_path=str(first_path),
            file_ext=first_path.suffix,
            file_size=first_path.stat().st_size,
        )
        third = Material(
            achievement_id=achievement.id,
            material_no=f"{achievement.id}-3",
            display_name="Third",
            original_filename=third_path.name,
            stored_path=str(third_path),
            file_ext=third_path.suffix,
            file_size=third_path.stat().st_size,
        )
        achievement.materials.extend([first, third])
        db.add_all([first, third])
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.post(
        "/materials/upload",
        data={"achievement_id": str(achievement_id)},
        files={"file": ("new-proof.pdf", BytesIO(b"new"), "application/pdf")},
        follow_redirects=False,
    )

    assert response.status_code == 303

    db = SessionLocal()
    try:
        numbers = [
            material.material_no
            for material in db.query(Material)
            .filter_by(achievement_id=achievement_id)
            .order_by(Material.material_no)
            .all()
        ]
        assert numbers == [
            f"{achievement_id}-1",
            f"{achievement_id}-3",
            f"{achievement_id}-4",
        ]
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


def test_owner_can_preview_pdf_material_inline(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("preview-proof.pdf", b"%PDF-1.4 preview")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        _, material_id = _create_owned_material(db, admin.id, source_path)
    finally:
        db.close()

    response = client.get(f"/materials/{material_id}/preview")

    assert response.status_code == 200
    assert response.content == source_path.read_bytes()
    assert response.headers["content-type"].startswith("application/pdf")
    assert "inline" in response.headers["content-disposition"]
    assert "preview-proof.pdf" in response.headers["content-disposition"]


def test_owner_cannot_preview_unsupported_material(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("word-proof.docx", b"word")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        _, material_id = _create_owned_material(db, admin.id, source_path)
    finally:
        db.close()

    response = client.get(f"/materials/{material_id}/preview")

    assert response.status_code == 404


def test_preview_missing_material_file_returns_404(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("missing-preview.pdf", b"missing")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        _, material_id = _create_owned_material(db, admin.id, source_path)
        source_path.unlink()
    finally:
        db.close()

    response = client.get(f"/materials/{material_id}/preview")

    assert response.status_code == 404


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


def test_material_detail_shows_preview_only_for_supported_files(app):
    client = TestClient(app)
    _login_admin(client)
    preview_path = _create_material_file("detail-preview.png", b"png")
    unsupported_path = _create_material_file("detail-word.docx", b"docx")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, preview_id = _create_owned_material(db, admin.id, preview_path)
        material = Material(
            achievement_id=achievement_id,
            material_no=f"{achievement_id}-2",
            display_name="Word proof",
            original_filename=unsupported_path.name,
            stored_path=str(unsupported_path),
            file_ext=unsupported_path.suffix,
            file_size=unsupported_path.stat().st_size,
        )
        db.add(material)
        db.commit()
        unsupported_id = material.id
    finally:
        db.close()

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert f"/materials/{preview_id}/preview" in response.text
    assert f"/materials/{unsupported_id}/preview" not in response.text


def test_material_detail_shows_batch_upload_controls_and_results(app):
    client = TestClient(app)
    _login_admin(client)

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = _complete_process_achievement(admin.id, "Upload result page")
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.get(
        f"/achievements/{achievement_id}?uploaded=2&failed=1&errors=bad.exe%EF%BC%9AUnsupported"
    )

    assert response.status_code == 200
    assert 'input type="file" name="file" multiple required' in response.text
    assert "单次最多上传 10 个文件" in response.text
    assert "每个文件不超过 50MB" in response.text
    assert "总大小不超过 500MB" in response.text
    assert "已上传 2 份材料" in response.text
    assert "1 份材料上传失败" in response.text
    assert "bad.exe：Unsupported" in response.text


def test_material_detail_shows_rename_action_and_messages(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("rename-detail.pdf", b"detail rename")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, material_id = _create_owned_material(db, admin.id, source_path)
    finally:
        db.close()

    response = client.get(
        f"/achievements/{achievement_id}?renamed=1&rename_error=%E6%9D%90%E6%96%99%E5%90%8D%E7%A7%B0%E4%B8%8D%E8%83%BD%E4%B8%BA%E7%A9%BA"
    )

    assert response.status_code == 200
    assert "材料名称已更新" in response.text
    assert "重命名失败：材料名称不能为空" in response.text
    assert f'action="/materials/{material_id}/rename"' in response.text
    assert 'name="display_name"' in response.text
    assert 'name="description"' in response.text
    assert "修改材料名称" in response.text


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


def test_owner_can_rename_material_without_changing_file_identity(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("rename-source.pdf", b"rename content")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, material_id = _create_owned_material(db, admin.id, source_path)
        material = db.get(Material, material_id)
        original_number = material.material_no
        original_filename = material.original_filename
        original_stored_path = material.stored_path
    finally:
        db.close()

    response = client.post(
        f"/materials/{material_id}/rename",
        data={
            "display_name": "省赛二等奖证书",
            "description": "用于年度绩效申报",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/achievements/{achievement_id}")
    assert "renamed=1" in response.headers["location"]

    db = SessionLocal()
    try:
        material = db.get(Material, material_id)
        assert material.display_name == "省赛二等奖证书"
        assert material.description == "用于年度绩效申报"
        assert material.material_no == original_number
        assert material.original_filename == original_filename
        assert material.stored_path == original_stored_path
        assert Path(material.stored_path).read_bytes() == b"rename content"
    finally:
        db.close()


def test_blank_material_rename_keeps_original_display_name(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("blank-rename.pdf", b"original name")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, material_id = _create_owned_material(db, admin.id, source_path)
        original_name = db.get(Material, material_id).display_name
    finally:
        db.close()

    response = client.post(
        f"/materials/{material_id}/rename",
        data={"display_name": "   ", "description": "will not save"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/achievements/{achievement_id}")
    assert "rename_error=" in response.headers["location"]

    db = SessionLocal()
    try:
        material = db.get(Material, material_id)
        assert material.display_name == original_name
        assert material.description == "Original description"
    finally:
        db.close()


def test_user_cannot_rename_another_users_material(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("other-rename.pdf", b"private rename")

    db = SessionLocal()
    try:
        other_user = _create_user(db, f"other-rename-owner-{uuid4().hex}")
        _, material_id = _create_owned_material(db, other_user.id, source_path)
    finally:
        db.close()

    response = client.post(
        f"/materials/{material_id}/rename",
        data={"display_name": "不应成功", "description": ""},
        follow_redirects=False,
    )

    assert response.status_code == 404

    db = SessionLocal()
    try:
        material = db.get(Material, material_id)
        assert material.display_name == "Original proof"
    finally:
        db.close()


def test_invalid_replacement_keeps_original_material_file(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("keep-original.pdf", b"original")

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement_id, material_id = _create_owned_material(db, admin.id, source_path)
        original_stored_path = db.get(Material, material_id).stored_path
    finally:
        db.close()

    response = client.post(
        f"/materials/{material_id}/replace",
        files={"file": ("bad.exe", BytesIO(b"bad"), "application/octet-stream")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/achievements/{achievement_id}")
    assert "replace_error=" in response.headers["location"]

    db = SessionLocal()
    try:
        material = db.get(Material, material_id)
        assert material.original_filename == "keep-original.pdf"
        assert material.stored_path == original_stored_path
        assert Path(material.stored_path).read_bytes() == b"original"
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


def test_user_cannot_preview_another_users_material(app):
    client = TestClient(app)
    _login_admin(client)
    source_path = _create_material_file("other-preview.pdf", b"private preview")

    db = SessionLocal()
    try:
        other_user = _create_user(db, f"other-preview-owner-{uuid4().hex}")
        _, material_id = _create_owned_material(db, other_user.id, source_path)
    finally:
        db.close()

    response = client.get(f"/materials/{material_id}/preview", follow_redirects=False)

    assert response.status_code == 404
    assert source_path.exists()
