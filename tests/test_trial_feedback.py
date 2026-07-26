from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.models import (
    Achievement,
    AchievementStatus,
    ClaimNature,
    ExportRecord,
    Material,
    Role,
    User,
)
from app.security import hash_password


def _login_admin(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create_teacher(
    *,
    username: str | None = None,
    full_name: str | None = None,
    department: str = "试用学院",
    password: str = "teacher-pass-123",
    must_change_password: bool = False,
) -> tuple[int, str, str]:
    username = username or f"trial-feedback-{uuid4().hex}"
    full_name = full_name or f"试用教师{uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        teacher = User(
            username=username,
            full_name=full_name,
            department=department,
            role=Role.teacher.value,
            password_hash=hash_password(password),
            must_change_password=must_change_password,
        )
        db.add(teacher)
        db.commit()
        return teacher.id, username, full_name
    finally:
        db.close()


def test_successful_login_records_last_login_for_trial_progress(app):
    teacher_id, username, _ = _create_teacher()
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"username": username, "password": "teacher-pass-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db = SessionLocal()
    try:
        teacher = db.get(User, teacher_id)
        assert teacher.last_login_at is not None
    finally:
        db.close()


def test_teacher_can_submit_trial_feedback_and_admin_can_update_status(app):
    teacher_id, username, full_name = _create_teacher()
    teacher_client = TestClient(app)
    teacher_client.post(
        "/login",
        data={"username": username, "password": "teacher-pass-123"},
        follow_redirects=False,
    )

    form_page = teacher_client.get("/feedback")
    assert form_page.status_code == 200
    assert "提交试用反馈" in form_page.text

    submitted = teacher_client.post(
        "/feedback",
        data={
            "issue_type": "上传材料",
            "current_page": "/achievements/1",
            "related_title": "江苏省职业技能竞赛数字艺术赛项二等奖",
            "description": "上传后不知道是否成功",
        },
        follow_redirects=False,
    )
    assert submitted.status_code == 303
    assert submitted.headers["location"] == "/feedback?submitted=1"

    admin_client = TestClient(app)
    _login_admin(admin_client)
    trial_page = admin_client.get("/admin/trial")
    assert trial_page.status_code == 200
    assert full_name in trial_page.text
    assert "上传材料" in trial_page.text
    assert "上传后不知道是否成功" in trial_page.text
    assert "待处理" in trial_page.text

    db = SessionLocal()
    try:
        feedback_id = db.execute(
            text("SELECT id FROM trial_feedback WHERE user_id = :user_id"),
            {"user_id": teacher_id},
        ).scalar_one()
    finally:
        db.close()

    updated = admin_client.post(
        f"/admin/feedback/{feedback_id}/status",
        data={"status": "已解决", "admin_note": "已优化上传提示"},
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert updated.headers["location"] == "/admin/trial"

    updated_page = admin_client.get("/admin/trial")
    assert "已解决" in updated_page.text
    assert "已优化上传提示" in updated_page.text


def test_admin_trial_dashboard_summarizes_public_trial_progress(app, tmp_path):
    started_id, _, started_name = _create_teacher(full_name="已开始教师")
    changed_id, _, changed_name = _create_teacher(full_name="已改密教师")
    idle_id, _, idle_name = _create_teacher(
        full_name="未开始教师",
        must_change_password=True,
    )
    material_path = tmp_path / "proof.pdf"
    material_path.write_bytes(b"%PDF-1.4 proof")

    db = SessionLocal()
    try:
        started = db.get(User, started_id)
        changed = db.get(User, changed_id)
        started.last_login_at = changed.created_at
        changed.last_login_at = changed.created_at

        achievement = Achievement(
            user_id=changed_id,
            year=2026,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="试用进度成果",
            claimed_score=3,
            status=AchievementStatus.ready.value,
        )
        db.add(achievement)
        db.flush()
        material = Material(
            achievement_id=achievement.id,
            material_no=f"{achievement.id}-1",
            display_name="证明材料",
            original_filename=material_path.name,
            stored_path=str(material_path),
            file_ext=".pdf",
            file_size=material_path.stat().st_size,
        )
        achievement.materials.append(material)
        db.add(material)
        db.add(
            ExportRecord(
                user_id=changed_id,
                year=2026,
                file_name="2026.zip",
                file_path=str(tmp_path / "2026.zip"),
                achievement_count=1,
                material_count=1,
                file_size=100,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    _login_admin(client)
    response = client.get("/admin/trial")

    assert response.status_code == 200
    assert "试用进度" in response.text
    assert 'data-metric="teacher-count">3<' in response.text
    assert 'data-metric="logged-in-count">2<' in response.text
    assert 'data-metric="password-changed-count">2<' in response.text
    assert 'data-metric="achievement-user-count">1<' in response.text
    assert 'data-metric="material-user-count">1<' in response.text
    assert 'data-metric="exported-user-count">1<' in response.text
    assert started_name in response.text
    assert changed_name in response.text
    assert idle_name in response.text
