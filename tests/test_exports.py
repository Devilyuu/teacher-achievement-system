from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.config import EXPORT_DIR
from app.database import SessionLocal
from app.models import Achievement, ClaimNature, Material, Role, User
from app.security import hash_password
from app.services.export_builder import build_personal_export


APPLICATION_HEADERS = [
    "序号",
    "项目大类",
    "项目小类",
    "申报性质",
    "项目具体名称",
    "级别",
    "本人角色",
    "申报积分",
    "支撑材料编号+名称",
    "材料状态",
    "备注",
]

CATALOG_HEADERS = [
    "材料编号",
    "对应成果序号",
    "项目大类",
    "项目小类",
    "项目名称",
    "申报性质",
    "材料名称",
    "文件名",
    "文件类型",
    "上传时间",
]


def _create_user(db, username: str) -> User:
    user = User(
        username=username,
        full_name=f"导出教师{uuid4().hex[:6]}",
        department="Test",
        role=Role.teacher.value,
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.flush()
    return user


def _add_achievement_with_material(
    db,
    user: User,
    year: int,
    category: str,
    subcategory: str,
    source_path: Path,
    material_no: str,
) -> Achievement:
    achievement = Achievement(
        user_id=user.id,
        year=year,
        category=category,
        subcategory=subcategory,
        claim_nature=ClaimNature.result.value,
        title=f"{subcategory}成果",
        level="校级",
        personal_role="负责人",
        claimed_score=3,
        notes="测试导出",
    )
    db.add(achievement)
    db.flush()
    material = Material(
        achievement_id=achievement.id,
        material_no=material_no,
        display_name=f"{subcategory}证明",
        original_filename=source_path.name,
        stored_path=str(source_path),
        file_ext=source_path.suffix,
        file_size=source_path.stat().st_size,
        uploaded_at=datetime(2026, 5, 1, 9, 30),
    )
    achievement.materials.append(material)
    db.add(material)
    db.flush()
    return achievement


def _headers_from_zip(zip_path: Path, workbook_name: str, sheet_name: str) -> list[str]:
    with ZipFile(zip_path) as archive:
        workbook_bytes = BytesIO(archive.read(workbook_name))
    workbook = load_workbook(workbook_bytes)
    sheet = workbook[sheet_name]
    return [cell.value for cell in sheet[1]]


def test_build_personal_export_creates_zip_workbooks_and_category_materials(app, tmp_path):
    year = 2026
    standard_source = tmp_path / "standard-proof.pdf"
    custom_source = tmp_path / "custom-proof.docx"
    standard_source.write_bytes(b"%PDF-1.4 standard proof")
    custom_source.write_bytes(b"custom proof")

    db = SessionLocal()
    try:
        user = _create_user(db, f"export-builder-{uuid4().hex}")
        _add_achievement_with_material(
            db,
            user,
            year,
            "教学",
            "精品在线开放课程建设（含虚拟仿真课程资源）",
            standard_source,
            "1-1",
        )
        _add_achievement_with_material(
            db,
            user,
            year,
            "其他有价值工作（自定义）",
            "自定义工作事项",
            custom_source,
            "2-1",
        )
        db.commit()

        zip_path = build_personal_export(db, user, year)
        user_id = user.id
    finally:
        db.close()

    assert zip_path.exists()
    assert zip_path.parent == EXPORT_DIR / str(year) / str(user_id)

    with ZipFile(zip_path) as archive:
        names = archive.namelist()

    assert "01_个人项目申报表.xlsx" in names
    assert "04_材料目录.xlsx" in names
    assert any(
        name.startswith("05_支撑材料/03_教学/") and name.endswith(".pdf")
        for name in names
    )
    assert any(
        name.startswith("05_支撑材料/10_其他有价值工作（自定义）/") and name.endswith(".docx")
        for name in names
    )
    assert _headers_from_zip(zip_path, "01_个人项目申报表.xlsx", "个人项目申报表") == APPLICATION_HEADERS
    assert _headers_from_zip(zip_path, "04_材料目录.xlsx", "材料目录") == CATALOG_HEADERS


def test_export_route_requires_auth_and_authenticated_user_can_download(app, tmp_path):
    client = TestClient(app)

    unauthenticated = client.get("/exports/2026/personal", follow_redirects=False)
    assert unauthenticated.status_code in {401, 303}

    source_path = tmp_path / "route-proof.pdf"
    source_path.write_bytes(b"%PDF-1.4 route proof")

    db = SessionLocal()
    try:
        user = _create_user(db, f"export-route-{uuid4().hex}")
        _add_achievement_with_material(
            db,
            user,
            2026,
            "教学",
            "精品在线开放课程建设（含虚拟仿真课程资源）",
            source_path,
            "1-1",
        )
        db.commit()
        user_id = user.id
    finally:
        db.close()

    client.cookies.set("user_id", str(user_id))
    response = client.get("/exports/2026/personal")

    assert response.status_code == 200
    assert response.headers["content-type"] in {"application/zip", "application/x-zip-compressed"}
    assert "filename" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith(".zip")
    with ZipFile(BytesIO(response.content)) as archive:
        assert "01_个人项目申报表.xlsx" in archive.namelist()
