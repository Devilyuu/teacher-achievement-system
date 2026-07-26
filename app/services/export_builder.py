from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.config import EXPORT_DIR
from app.models import Achievement, AchievementStatus, Material, PerformanceRule, User
from app.services.performance_rule_guidance import assignment_mode


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
    "申报级别",
    "审核认定级别",
    "本人角色",
    "基本分",
    "绩效分",
    "赋分方式",
    "申报积分",
    "最终认定积分",
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

    achievements = sort_achievements_for_export(
        db.query(Achievement)
        .filter(Achievement.user_id == user.id, Achievement.year == year)
        .order_by(Achievement.id)
        .all()
    )

    rule_lookup = {
        (rule.category, rule.subcategory): rule
        for rule in db.query(PerformanceRule)
        .filter(PerformanceRule.is_active.is_(True))
        .all()
    }

    _write_application_workbook(application_path, achievements, rule_lookup)
    _write_material_catalog(catalog_path, achievements)
    _write_zip(zip_path, application_path, catalog_path, achievements, user, year)
    return zip_path


def sort_achievements_for_export(achievements: list[Achievement]) -> list[Achievement]:
    return sorted(achievements, key=_achievement_sort_key)


def _achievement_sort_key(achievement: Achievement) -> tuple[int, str, str, int]:
    category_index = (
        CATEGORY_ORDER.index(achievement.category)
        if achievement.category in CATEGORY_ORDER
        else len(CATEGORY_ORDER)
    )
    return (
        category_index,
        achievement.subcategory or "",
        achievement.title or "",
        achievement.id or 0,
    )


def _write_application_workbook(
    path: Path,
    achievements: list[Achievement],
    rule_lookup: dict[tuple[str, str], PerformanceRule],
) -> None:
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
                "",
                achievement.personal_role,
                achievement.base_score,
                achievement.performance_score,
                assignment_mode(
                    rule_lookup.get((achievement.category, achievement.subcategory))
                ),
                achievement.claimed_score,
                "",
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
    user: User,
    year: int,
) -> None:
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("00_导出说明.txt", _summary_text(user, year, achievements))
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


def _summary_text(user: User, year: int, achievements: list[Achievement]) -> str:
    ready_statuses = {
        AchievementStatus.ready.value,
        AchievementStatus.exported.value,
    }
    ready_count = sum(achievement.status in ready_statuses for achievement in achievements)
    needs_attention = [
        achievement
        for achievement in achievements
        if achievement.status not in ready_statuses
    ]
    material_count = sum(len(achievement.materials) for achievement in achievements)
    missing_materials = [
        achievement
        for achievement in achievements
        if not achievement.materials
    ]

    lines = [
        "教师个人年度绩效材料包导出说明",
        f"年度：{year}",
        f"教师：{user.full_name}",
        f"成果总数：{len(achievements)}",
        f"可导出成果：{ready_count}",
        f"待完善成果：{len(needs_attention)}",
        f"支撑材料总数：{material_count}",
        f"缺少材料成果：{len(missing_materials)}",
        "",
        "说明：最终分值和级别认定仍以线下审核为准。",
    ]
    if needs_attention:
        lines.extend(["", "待完善成果清单："])
        for achievement in needs_attention:
            lines.append(
                f"- {achievement.title}｜{achievement.status}｜"
                f"{achievement.category} / {achievement.subcategory}"
            )
    return "\n".join(lines) + "\n"


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
