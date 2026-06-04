from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.config import EXPORT_DIR
from app.models import Achievement, Material, User


CATEGORY_ORDER = [
    "师德师风及党建思政工作",
    "教师发展",
    "教学",
    "产教融合工作",
    "学生工作",
    "科研与社会服务工作",
    "国际交流与合作",
    "育人成效",
    "监管类工作",
    "其他有价值工作（自定义）",
]

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


def build_personal_export(db: Session, user: User, year: int) -> Path:
    export_dir = EXPORT_DIR / str(year) / str(user.id)
    export_dir.mkdir(parents=True, exist_ok=True)

    application_path = export_dir / "01_个人项目申报表.xlsx"
    catalog_path = export_dir / "04_材料目录.xlsx"
    zip_path = export_dir / f"{year}年度绩效申报材料_{user.full_name}.zip"

    achievements = (
        db.query(Achievement)
        .filter(Achievement.user_id == user.id, Achievement.year == year)
        .order_by(Achievement.id)
        .all()
    )

    _write_application_workbook(application_path, achievements)
    _write_material_catalog(catalog_path, achievements)
    _write_zip(zip_path, application_path, catalog_path, achievements)
    return zip_path


def _write_application_workbook(path: Path, achievements: list[Achievement]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "个人项目申报表"
    sheet.append(APPLICATION_HEADERS)

    for index, achievement in enumerate(achievements, start=1):
        materials = "；".join(
            f"{material.material_no}+{material.display_name}"
            for material in achievement.materials
        )
        sheet.append(
            [
                index,
                achievement.category,
                achievement.subcategory,
                achievement.claim_nature,
                achievement.title,
                achievement.level,
                achievement.personal_role,
                achievement.claimed_score,
                materials,
                "完整" if achievement.materials else "缺少材料",
                achievement.notes,
            ]
        )

    workbook.save(path)


def _write_material_catalog(path: Path, achievements: list[Achievement]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "材料目录"
    sheet.append(CATALOG_HEADERS)

    for achievement_index, achievement in enumerate(achievements, start=1):
        for material in achievement.materials:
            sheet.append(
                [
                    material.material_no,
                    achievement_index,
                    achievement.category,
                    achievement.subcategory,
                    achievement.title,
                    achievement.claim_nature,
                    material.display_name,
                    material.original_filename,
                    material.file_ext,
                    material.uploaded_at,
                ]
            )

    workbook.save(path)


def _write_zip(
    zip_path: Path,
    application_path: Path,
    catalog_path: Path,
    achievements: list[Achievement],
) -> None:
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.write(application_path, application_path.name)
        archive.write(catalog_path, catalog_path.name)

        for achievement_index, achievement in enumerate(achievements, start=1):
            folder = _category_folder(achievement.category)
            for material in achievement.materials:
                source = Path(material.stored_path)
                if not source.exists():
                    continue
                archive.write(
                    source,
                    f"{folder}/{_material_archive_name(achievement_index, achievement, material)}",
                )


def _category_folder(category: str) -> str:
    category_no = CATEGORY_ORDER.index(category) + 1 if category in CATEGORY_ORDER else 99
    return f"05_支撑材料/{category_no:02d}_{_safe_name(category)}"


def _material_archive_name(
    achievement_index: int,
    achievement: Achievement,
    material: Material,
) -> str:
    extension = _original_extension(material)
    name = "_".join(
        [
            f"{achievement_index:03d}",
            achievement.claim_nature,
            achievement.subcategory,
            material.display_name,
        ]
    )
    return f"{_safe_name(name)}{extension}"


def _original_extension(material: Material) -> str:
    if material.file_ext:
        return material.file_ext if material.file_ext.startswith(".") else f".{material.file_ext}"
    return Path(material.original_filename).suffix or Path(material.stored_path).suffix


def _safe_name(value: str) -> str:
    return str(value).replace("/", "_").replace("\\", "_").strip()
