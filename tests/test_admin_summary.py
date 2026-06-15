from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import UPLOAD_DIR
from app.database import SessionLocal
from app.models import Achievement, AchievementStatus, ClaimNature, Material, Role, User
from app.security import hash_password
from app.services.admin_summary import (
    SummaryFilters,
    build_admin_summary,
    missing_reasons,
)


def _login_admin(client: TestClient) -> None:
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )


def _create_teacher(
    db,
    *,
    department: str,
    full_name: str,
    is_active: bool = True,
) -> User:
    user = User(
        username=f"summary-{uuid4().hex}",
        full_name=full_name,
        department=department,
        role=Role.teacher.value,
        password_hash=hash_password("password123"),
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def _create_material_file(filename: str, content: bytes = b"proof") -> Path:
    directory = UPLOAD_DIR / "test-admin-summary" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(content)
    return path


def _add_achievement(
    db,
    *,
    user: User,
    year: int,
    title: str,
    status: str,
    claimed_score: float = 3,
    category: str = "教学",
    subcategory: str = "教学成果奖申报及获奖",
    claim_nature: str = ClaimNature.result.value,
    current_stage: str = "",
    material_path: Path | None = None,
) -> Achievement:
    achievement = Achievement(
        user_id=user.id,
        year=year,
        category=category,
        subcategory=subcategory,
        claim_nature=claim_nature,
        title=title,
        claimed_score=claimed_score,
        current_stage=current_stage,
        status=status,
    )
    db.add(achievement)
    db.flush()

    if material_path:
        material = Material(
            achievement_id=achievement.id,
            material_no=f"{achievement.id}-1",
            display_name="获奖证明",
            original_filename=material_path.name,
            stored_path=str(material_path),
            file_ext=material_path.suffix,
            file_size=material_path.stat().st_size if material_path.exists() else 0,
        )
        achievement.materials.append(material)
        db.add(material)
        db.flush()
    return achievement


def test_summary_filters_intersect_and_aggregate_matching_records(app):
    db = SessionLocal()
    try:
        art_teacher = _create_teacher(
            db,
            department="艺术学院",
            full_name=f"艺术教师{uuid4().hex[:5]}",
        )
        other_teacher = _create_teacher(
            db,
            department="信息学院",
            full_name=f"信息教师{uuid4().hex[:5]}",
        )
        matching_material = _create_material_file("matching.pdf")
        matching = _add_achievement(
            db,
            user=art_teacher,
            year=2026,
            title="筛选命中的成果",
            status=AchievementStatus.ready.value,
            claimed_score=8,
            material_path=matching_material,
        )
        _add_achievement(
            db,
            user=art_teacher,
            year=2026,
            title="状态不匹配",
            status=AchievementStatus.needs_info.value,
        )
        _add_achievement(
            db,
            user=art_teacher,
            year=2027,
            title="年度不匹配",
            status=AchievementStatus.ready.value,
            material_path=_create_material_file("future.pdf"),
        )
        _add_achievement(
            db,
            user=other_teacher,
            year=2026,
            title="部门和教师不匹配",
            status=AchievementStatus.ready.value,
            material_path=_create_material_file("other.pdf"),
        )
        db.commit()

        result = build_admin_summary(
            db,
            SummaryFilters(
                year=2026,
                department="艺术学院",
                teacher_id=art_teacher.id,
                status=AchievementStatus.ready.value,
            ),
        )

        assert [item.id for item in result.achievements] == [matching.id]
        assert result.metrics.teacher_count == 1
        assert result.metrics.achievement_count == 1
        assert result.metrics.claimed_score == 8
        assert result.metrics.needs_info_count == 0
        assert result.metrics.material_count == 1
        assert len(result.teachers) == 1
        assert result.teachers[0].user.id == art_teacher.id
        assert result.teachers[0].ready_count == 1
    finally:
        db.close()


def test_summary_keeps_inactive_teacher_history_and_reports_missing_reasons(app):
    db = SessionLocal()
    try:
        inactive_teacher = _create_teacher(
            db,
            department="艺术学院",
            full_name=f"停用教师{uuid4().hex[:5]}",
            is_active=False,
        )
        missing_file = (
            UPLOAD_DIR
            / "test-admin-summary"
            / uuid4().hex
            / "missing-proof.pdf"
        )
        achievement = _add_achievement(
            db,
            user=inactive_teacher,
            year=2026,
            title="",
            status=AchievementStatus.needs_info.value,
            claimed_score=0,
            claim_nature=ClaimNature.process.value,
            current_stage="",
            material_path=missing_file,
        )
        db.commit()

        result = build_admin_summary(
            db,
            SummaryFilters(year=2026, department="艺术学院"),
        )
        reasons = missing_reasons(achievement)

        assert achievement.id in [item.id for item in result.achievements]
        teacher_row = next(
            row for row in result.teachers if row.user.id == inactive_teacher.id
        )
        assert teacher_row.user.is_active is False
        assert teacher_row.needs_info_count == 1
        assert "申报信息不完整" in reasons
        assert "申报积分未填写或不大于零" in reasons
        assert "过程性工作缺少进展说明" in reasons
        assert "材料文件不存在" in reasons
        assert "未上传支撑材料" not in reasons
    finally:
        db.close()


def test_summary_excludes_achievements_owned_by_admin_accounts(app):
    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        admin_achievement = _add_achievement(
            db,
            user=admin,
            year=2026,
            title=f"管理员测试成果{uuid4().hex[:5]}",
            status=AchievementStatus.ready.value,
            material_path=_create_material_file("admin-proof.pdf"),
        )
        db.commit()

        result = build_admin_summary(db, SummaryFilters(year=2026))

        assert admin_achievement.id not in [
            achievement.id for achievement in result.achievements
        ]
    finally:
        db.close()


def test_admin_summary_page_requires_admin(app):
    unauthenticated = TestClient(app).get(
        "/admin/summary",
        follow_redirects=False,
    )
    assert unauthenticated.status_code in {303, 401}

    db = SessionLocal()
    try:
        teacher = _create_teacher(
            db,
            department="权限测试学院",
            full_name=f"普通教师{uuid4().hex[:5]}",
        )
        db.commit()
        teacher_id = teacher.id
    finally:
        db.close()

    teacher_client = TestClient(app)
    teacher_client.cookies.set("user_id", str(teacher_id))
    forbidden = teacher_client.get("/admin/summary")
    assert forbidden.status_code == 403


def test_admin_summary_page_renders_filtered_metrics_rows_and_export_links(app):
    client = TestClient(app)
    _login_admin(client)
    department = f"汇总学院{uuid4().hex[:5]}"

    db = SessionLocal()
    try:
        teacher = _create_teacher(
            db,
            department=department,
            full_name=f"汇总教师{uuid4().hex[:5]}",
        )
        matching = _add_achievement(
            db,
            user=teacher,
            year=2026,
            title=f"页面命中成果{uuid4().hex[:5]}",
            status=AchievementStatus.ready.value,
            claimed_score=6,
            material_path=_create_material_file("page-proof.pdf"),
        )
        excluded = _add_achievement(
            db,
            user=teacher,
            year=2026,
            title=f"页面排除成果{uuid4().hex[:5]}",
            status=AchievementStatus.needs_info.value,
        )
        db.commit()
        teacher_id = teacher.id
        teacher_name = teacher.full_name
        matching_title = matching.title
        excluded_title = excluded.title
    finally:
        db.close()

    response = client.get(
        "/admin/summary",
        params={
            "year": 2026,
            "department": department,
            "teacher_id": teacher_id,
            "status": AchievementStatus.ready.value,
        },
    )

    assert response.status_code == 200
    assert "年度汇总" in response.text
    assert teacher_name in response.text
    assert matching_title in response.text
    assert excluded_title not in response.text
    assert 'data-metric="teacher-count">1<' in response.text
    assert 'data-metric="achievement-count">1<' in response.text
    assert 'data-metric="claimed-score">6.0<' in response.text
    assert "/admin/summary/export.xlsx?" in response.text
    assert "/admin/summary/materials.zip?" in response.text
    assert "year=2026" in response.text
    assert f"teacher_id={teacher_id}" in response.text
    assert f"department={quote(department)}" in response.text
    assert f"status={quote(AchievementStatus.ready.value)}" in response.text


def test_admin_can_open_teacher_achievement_as_read_only(app):
    client = TestClient(app)
    _login_admin(client)

    db = SessionLocal()
    try:
        teacher = _create_teacher(
            db,
            department="只读学院",
            full_name=f"只读教师{uuid4().hex[:5]}",
        )
        achievement = _add_achievement(
            db,
            user=teacher,
            year=2026,
            title=f"只读成果{uuid4().hex[:5]}",
            status=AchievementStatus.ready.value,
            material_path=_create_material_file("readonly.pdf"),
        )
        db.commit()
        achievement_id = achievement.id
        title = achievement.title
        teacher_name = teacher.full_name
    finally:
        db.close()

    response = client.get(f"/admin/achievements/{achievement_id}")

    assert response.status_code == 200
    assert title in response.text
    assert teacher_name in response.text
    assert f"/achievements/{achievement_id}/edit" not in response.text
    assert 'action="/materials/upload"' not in response.text
    assert f'action="/achievements/{achievement_id}/delete"' not in response.text
