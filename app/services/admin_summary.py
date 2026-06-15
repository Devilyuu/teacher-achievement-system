from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, joinedload

from app.models import Achievement, AchievementStatus, ClaimNature, User


@dataclass(frozen=True)
class SummaryFilters:
    year: int
    department: str = ""
    teacher_id: int | None = None
    status: str = ""


@dataclass(frozen=True)
class SummaryMetrics:
    teacher_count: int
    achievement_count: int
    claimed_score: float
    needs_info_count: int
    material_count: int


@dataclass
class TeacherSummaryRow:
    user: User
    achievement_count: int = 0
    ready_count: int = 0
    needs_info_count: int = 0
    material_count: int = 0
    claimed_score: float = 0


@dataclass
class AdminSummary:
    filters: SummaryFilters
    achievements: list[Achievement]
    teachers: list[TeacherSummaryRow]
    metrics: SummaryMetrics


def build_admin_summary(db: Session, filters: SummaryFilters) -> AdminSummary:
    query = (
        db.query(Achievement)
        .join(Achievement.user)
        .options(
            joinedload(Achievement.user),
            joinedload(Achievement.materials),
        )
        .filter(Achievement.year == filters.year)
    )
    if filters.department:
        query = query.filter(User.department == filters.department)
    if filters.teacher_id is not None:
        query = query.filter(Achievement.user_id == filters.teacher_id)
    if filters.status:
        query = query.filter(Achievement.status == filters.status)

    achievements = (
        query.order_by(
            User.department,
            User.full_name,
            Achievement.category,
            Achievement.id,
        )
        .all()
    )
    teacher_rows = _teacher_rows(achievements)
    metrics = SummaryMetrics(
        teacher_count=len(teacher_rows),
        achievement_count=len(achievements),
        claimed_score=sum(item.claimed_score or 0 for item in achievements),
        needs_info_count=sum(
            item.status == AchievementStatus.needs_info.value
            for item in achievements
        ),
        material_count=sum(len(item.materials) for item in achievements),
    )
    return AdminSummary(
        filters=filters,
        achievements=achievements,
        teachers=teacher_rows,
        metrics=metrics,
    )


def missing_reasons(achievement: Achievement) -> list[str]:
    reasons: list[str] = []
    required_text = [
        achievement.category,
        achievement.subcategory,
        achievement.claim_nature,
        achievement.title,
    ]
    if not all(value and str(value).strip() for value in required_text):
        reasons.append("申报信息不完整")
    if achievement.claimed_score is None or achievement.claimed_score <= 0:
        reasons.append("申报积分未填写或不大于零")
    if (
        achievement.claim_nature == ClaimNature.process.value
        and not (achievement.current_stage or "").strip()
    ):
        reasons.append("过程性工作缺少进展说明")
    if not achievement.materials:
        reasons.append("未上传支撑材料")
    elif any(not Path(material.stored_path).is_file() for material in achievement.materials):
        reasons.append("材料文件不存在")
    return reasons


def _teacher_rows(achievements: list[Achievement]) -> list[TeacherSummaryRow]:
    rows_by_user: dict[int, TeacherSummaryRow] = {}
    for achievement in achievements:
        row = rows_by_user.setdefault(
            achievement.user_id,
            TeacherSummaryRow(user=achievement.user),
        )
        row.achievement_count += 1
        row.ready_count += achievement.status == AchievementStatus.ready.value
        row.needs_info_count += (
            achievement.status == AchievementStatus.needs_info.value
        )
        row.material_count += len(achievement.materials)
        row.claimed_score += achievement.claimed_score or 0
    return list(rows_by_user.values())
