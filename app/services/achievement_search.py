from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models import Achievement


@dataclass(frozen=True)
class AchievementFilters:
    year: int
    status: str = ""
    category: str = ""
    subcategory: str = ""
    keyword: str = ""


def search_achievements(
    db: Session,
    user_id: int,
    filters: AchievementFilters,
) -> list[Achievement]:
    query = (
        db.query(Achievement)
        .options(joinedload(Achievement.materials))
        .filter(
            Achievement.user_id == user_id,
            Achievement.year == filters.year,
        )
    )
    if filters.status.strip():
        query = query.filter(Achievement.status == filters.status.strip())
    if filters.category.strip():
        query = query.filter(Achievement.category == filters.category.strip())
    if filters.subcategory.strip():
        query = query.filter(
            Achievement.subcategory == filters.subcategory.strip()
        )
    keyword = filters.keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                Achievement.title.ilike(pattern),
                Achievement.subcategory.ilike(pattern),
                Achievement.current_stage.ilike(pattern),
                Achievement.notes.ilike(pattern),
            )
        )
    return query.order_by(
        Achievement.updated_at.desc(),
        Achievement.id.desc(),
    ).all()
