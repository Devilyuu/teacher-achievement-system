from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import Achievement, AchievementStatus, Material, User
from app.security import get_current_user


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/")
def dashboard(
    request: Request,
    year: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    selected_year = year or datetime.now().year
    base_query = db.query(Achievement).filter(
        Achievement.user_id == user.id,
        Achievement.year == selected_year,
    )
    achievements = (
        base_query.order_by(Achievement.updated_at.desc(), Achievement.id.desc())
        .all()
    )
    achievement_ids = [achievement.id for achievement in achievements]
    material_count = (
        db.query(func.count(Material.id))
        .filter(Material.achievement_id.in_(achievement_ids))
        .scalar()
        if achievement_ids
        else 0
    )
    available_years = [
        row[0]
        for row in (
            db.query(Achievement.year)
            .filter(Achievement.user_id == user.id)
            .distinct()
            .order_by(Achievement.year.desc())
            .all()
        )
    ]
    category_counts: dict[str, int] = {}
    for achievement in achievements:
        category_counts[achievement.category] = category_counts.get(achievement.category, 0) + 1

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "selected_year": selected_year,
            "available_years": sorted(
                set([selected_year, datetime.now().year, *available_years]),
                reverse=True,
            ),
            "recent_achievements": achievements[:6],
            "category_counts": sorted(
                category_counts.items(),
                key=lambda item: (-item[1], item[0]),
            ),
            "stats": {
                "total": len(achievements),
                "needs_info": sum(
                    achievement.status == AchievementStatus.needs_info.value
                    for achievement in achievements
                ),
                "materials": material_count,
                "claimed_score": sum(
                    achievement.claimed_score or 0
                    for achievement in achievements
                ),
            },
        },
    )
