from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import Achievement, AchievementStatus, Material, User
from app.services.achievement_readiness import missing_reasons
from app.security import get_current_user
from app.services.annual_submission import (
    confirm_annual_submission,
    get_annual_submission_state,
)
from app.services.reporting_year import available_reporting_years, current_reporting_year


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/")
def dashboard(
    request: Request,
    year: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    selected_year = year or current_reporting_year()
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
    pending_achievements = [
        achievement
        for achievement in achievements
        if achievement.status == AchievementStatus.needs_info.value
    ]
    pending_items = [
        {"achievement": achievement, "reasons": missing_reasons(achievement)}
        for achievement in pending_achievements[:6]
    ]
    annual_state = get_annual_submission_state(db, user.id, selected_year)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "selected_year": selected_year,
            "available_years": available_reporting_years(
                available_years,
                selected_year,
            ),
            "recent_achievements": achievements[:6],
            "pending_items": pending_items,
            "pending_total": len(pending_achievements),
            "category_counts": sorted(
                category_counts.items(),
                key=lambda item: (-item[1], item[0]),
            ),
            "annual_state": annual_state,
            "submitted_success": request.query_params.get("submitted") == "1",
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
                "needs_info_status": AchievementStatus.needs_info.value,
            },
        },
    )


@router.post("/annual-submissions/{year}/confirm")
def confirm_annual_submission_route(
    year: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    confirm_annual_submission(db, user, year)
    return RedirectResponse(
        f"/?year={year}&submitted=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )
