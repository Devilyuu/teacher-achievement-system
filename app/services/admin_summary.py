from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from app.models import Achievement, AchievementStatus, Role, User
from app.services.achievement_readiness import missing_reasons
from app.services.annual_submission import (
    ANNUAL_STATUS_EXPORTED,
    ANNUAL_STATUS_SUBMITTED,
    AnnualSubmissionState,
    get_annual_submission_state,
)


@dataclass(frozen=True)
class SummaryFilters:
    year: int
    department: str = ""
    teacher_id: int | None = None
    status: str = ""
    annual_status: str = ""


@dataclass(frozen=True)
class SummaryMetrics:
    teacher_count: int
    achievement_count: int
    claimed_score: float
    needs_info_count: int
    material_count: int
    submitted_teacher_count: int


@dataclass
class TeacherSummaryRow:
    user: User
    achievement_count: int = 0
    ready_count: int = 0
    needs_info_count: int = 0
    material_count: int = 0
    claimed_score: float = 0
    annual_state: AnnualSubmissionState | None = None


@dataclass
class AdminSummary:
    filters: SummaryFilters
    achievements: list[Achievement]
    teachers: list[TeacherSummaryRow]
    metrics: SummaryMetrics


def build_admin_summary(db: Session, filters: SummaryFilters) -> AdminSummary:
    teacher_query = db.query(User).filter(User.role == Role.teacher.value)
    if filters.department:
        teacher_query = teacher_query.filter(User.department == filters.department)
    if filters.teacher_id is not None:
        teacher_query = teacher_query.filter(User.id == filters.teacher_id)
    candidate_teachers = teacher_query.order_by(User.department, User.full_name).all()
    states_by_user = {
        teacher.id: get_annual_submission_state(db, teacher.id, filters.year)
        for teacher in candidate_teachers
    }
    if filters.annual_status:
        candidate_teachers = [
            teacher
            for teacher in candidate_teachers
            if states_by_user[teacher.id].status == filters.annual_status
        ]
    candidate_teacher_ids = [teacher.id for teacher in candidate_teachers]
    query = (
        db.query(Achievement)
        .join(Achievement.user)
        .options(
            joinedload(Achievement.user),
            joinedload(Achievement.materials),
        )
        .filter(
            Achievement.year == filters.year,
            User.role == Role.teacher.value,
            Achievement.user_id.in_(candidate_teacher_ids),
        )
    )
    if filters.status:
        query = query.filter(Achievement.status == filters.status)

    achievements = []
    if candidate_teacher_ids:
        achievements = (
            query.order_by(
                User.department,
                User.full_name,
                Achievement.category,
                Achievement.id,
            )
            .all()
        )
    teacher_rows = _teacher_rows(
        candidate_teachers,
        achievements,
        states_by_user,
        require_matching_achievement=bool(filters.status),
    )
    metrics = SummaryMetrics(
        teacher_count=len(teacher_rows),
        achievement_count=len(achievements),
        claimed_score=sum(item.claimed_score or 0 for item in achievements),
        needs_info_count=sum(
            item.status == AchievementStatus.needs_info.value
            for item in achievements
        ),
        material_count=sum(len(item.materials) for item in achievements),
        submitted_teacher_count=sum(
            row.annual_state is not None
            and row.annual_state.status
            in {ANNUAL_STATUS_SUBMITTED, ANNUAL_STATUS_EXPORTED}
            for row in teacher_rows
        ),
    )
    return AdminSummary(
        filters=filters,
        achievements=achievements,
        teachers=teacher_rows,
        metrics=metrics,
    )


def _teacher_rows(
    teachers: list[User],
    achievements: list[Achievement],
    states_by_user: dict[int, AnnualSubmissionState],
    *,
    require_matching_achievement: bool = False,
) -> list[TeacherSummaryRow]:
    rows_by_user: dict[int, TeacherSummaryRow] = {
        teacher.id: TeacherSummaryRow(
            user=teacher,
            annual_state=states_by_user.get(teacher.id),
        )
        for teacher in teachers
    }
    for achievement in achievements:
        row = rows_by_user.setdefault(
            achievement.user_id,
            TeacherSummaryRow(
                user=achievement.user,
                annual_state=states_by_user.get(achievement.user_id),
            ),
        )
        row.achievement_count += 1
        row.ready_count += achievement.status == AchievementStatus.ready.value
        row.needs_info_count += (
            achievement.status == AchievementStatus.needs_info.value
        )
        row.material_count += len(achievement.materials)
        row.claimed_score += achievement.claimed_score or 0
    rows = list(rows_by_user.values())
    if require_matching_achievement:
        rows = [row for row in rows if row.achievement_count > 0]
    return rows
