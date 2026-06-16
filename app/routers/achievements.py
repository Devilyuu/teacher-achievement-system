from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR, MAX_UPLOAD_MB
from app.database import get_db
from app.models import (
    Achievement,
    AchievementStatus,
    ClaimNature,
    PerformanceRule,
    User,
)
from app.security import get_current_user
from app.services.achievement_search import AchievementFilters, search_achievements
from app.services.achievement_status import calculate_status
from app.services.material_preview import PREVIEW_EXTENSIONS
from app.services.performance_rule_guidance import (
    LEVEL_OPTIONS,
    assignment_mode,
    find_rule,
    rule_for_level,
)


router = APIRouter(prefix="/achievements", tags=["achievements"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _active_rules(db: Session) -> list[PerformanceRule]:
    return (
        db.query(PerformanceRule)
        .filter(PerformanceRule.is_active.is_(True))
        .order_by(PerformanceRule.sort_order, PerformanceRule.id)
        .all()
    )


def _rule_data(rule: PerformanceRule) -> dict[str, str | bool]:
    return {
        "category": rule.category,
        "subcategory": rule.subcategory,
        "base_rule": rule.base_rule,
        "national_rule": rule.national_rule,
        "provincial_rule": rule.provincial_rule,
        "city_rule": rule.city_rule,
        "school_rule": rule.school_rule,
        "college_rule": rule.college_rule,
        "remark": rule.remark,
        "is_team": rule.is_team,
        "is_department_assigned": rule.is_department_assigned,
    }


def _group_achievements(
    achievements: list[Achievement],
    rules: list[PerformanceRule],
) -> list[dict]:
    category_order = list(dict.fromkeys(rule.category for rule in rules))
    by_category: dict[str, list[Achievement]] = {}
    for achievement in achievements:
        by_category.setdefault(achievement.category, []).append(achievement)

    ordered_categories = [
        category
        for category in category_order
        if category in by_category
    ]
    ordered_categories.extend(
        category
        for category in by_category
        if category not in category_order
    )
    return [
        {
            "category": category,
            "achievements": by_category[category],
        }
        for category in ordered_categories
    ]


def _achievement_for_user(db: Session, achievement_id: int, user: User) -> Achievement:
    achievement = (
        db.query(Achievement)
        .filter(Achievement.id == achievement_id, Achievement.user_id == user.id)
        .first()
    )
    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Achievement not found",
        )
    return achievement


def _form_context(
    request: Request,
    user: User,
    db: Session,
    achievement: Achievement | None = None,
    action: str = "/achievements",
):
    return {
        "request": request,
        "user": user,
        "achievement": achievement,
        "rules": [_rule_data(rule) for rule in _active_rules(db)],
        "claim_natures": [nature.value for nature in ClaimNature],
        "level_options": LEVEL_OPTIONS,
        "current_year": datetime.now().year,
        "action": action,
    }


def _assign_form_values(
    achievement: Achievement,
    year: int,
    category: str,
    subcategory: str,
    claim_nature: str,
    title: str,
    date_range: str,
    level: str,
    personal_role: str,
    current_stage: str,
    base_score: float,
    performance_score: float,
    claimed_score: float,
    notes: str,
) -> None:
    achievement.year = year
    achievement.category = category.strip()
    achievement.subcategory = subcategory.strip()
    achievement.claim_nature = claim_nature.strip()
    achievement.title = title.strip()
    achievement.date_range = date_range.strip()
    achievement.level = level.strip()
    achievement.personal_role = personal_role.strip()
    achievement.current_stage = current_stage.strip()
    achievement.base_score = base_score
    achievement.performance_score = performance_score
    achievement.claimed_score = claimed_score
    achievement.notes = notes.strip()
    achievement.updated_at = datetime.utcnow()
    achievement.status = calculate_status(achievement)


@router.get("")
def list_achievements(
    request: Request,
    year: int | None = Query(default=None),
    achievement_status: str = Query(default="", alias="status"),
    category: str = Query(default=""),
    subcategory: str = Query(default=""),
    q: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
    selected_year = year or datetime.now().year
    filters = AchievementFilters(
        year=selected_year,
        status=achievement_status.strip(),
        category=category.strip(),
        subcategory=subcategory.strip(),
        keyword=q.strip(),
    )
    achievements = search_achievements(db, user.id, filters)
    active_rules = _active_rules(db)
    category_options = list(dict.fromkeys(rule.category for rule in active_rules))
    return templates.TemplateResponse(
        request,
        "achievements/list.html",
        {
            "user": user,
            "achievements": achievements,
            "achievement_groups": _group_achievements(achievements, active_rules),
            "available_years": sorted(
                set([selected_year, datetime.now().year, *available_years]),
                reverse=True,
            ),
            "selected_year": selected_year,
            "filters": filters,
            "statuses": [item.value for item in AchievementStatus],
            "category_options": category_options,
            "rules": active_rules,
            "is_filtered": any(
                [
                    filters.status,
                    filters.category,
                    filters.subcategory,
                    filters.keyword,
                ]
            ),
        },
    )


@router.get("/new")
def new_achievement(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "achievements/form.html",
        _form_context(request, user, db),
    )


@router.post("")
def create_achievement(
    year: int = Form(...),
    category: str = Form(...),
    subcategory: str = Form(...),
    claim_nature: str = Form(...),
    title: str = Form(...),
    date_range: str = Form(""),
    level: str = Form(""),
    personal_role: str = Form(""),
    current_stage: str = Form(""),
    base_score: float = Form(0),
    performance_score: float = Form(0),
    claimed_score: float = Form(0),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = Achievement(user_id=user.id)
    _assign_form_values(
        achievement,
        year,
        category,
        subcategory,
        claim_nature,
        title,
        date_range,
        level,
        personal_role,
        current_stage,
        base_score,
        performance_score,
        claimed_score,
        notes,
    )
    db.add(achievement)
    db.commit()
    return RedirectResponse("/achievements", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{achievement_id}")
def achievement_detail(
    request: Request,
    achievement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    rule = find_rule(db, achievement.category, achievement.subcategory)
    return templates.TemplateResponse(
        request,
        "achievements/detail.html",
        {
            "user": user,
            "achievement": achievement,
            "rule": rule,
            "level_rule": rule_for_level(rule, achievement.level),
            "assignment_mode": assignment_mode(rule),
            "max_upload_mb": MAX_UPLOAD_MB,
            "preview_extensions": PREVIEW_EXTENSIONS,
        },
    )


@router.get("/{achievement_id}/edit")
def edit_achievement(
    request: Request,
    achievement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    return templates.TemplateResponse(
        request,
        "achievements/form.html",
        _form_context(
            request,
            user,
            db,
            achievement=achievement,
            action=f"/achievements/{achievement.id}/edit",
        ),
    )


@router.post("/{achievement_id}/edit")
def update_achievement(
    achievement_id: int,
    year: int = Form(...),
    category: str = Form(...),
    subcategory: str = Form(...),
    claim_nature: str = Form(...),
    title: str = Form(...),
    date_range: str = Form(""),
    level: str = Form(""),
    personal_role: str = Form(""),
    current_stage: str = Form(""),
    base_score: float = Form(0),
    performance_score: float = Form(0),
    claimed_score: float = Form(0),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    _assign_form_values(
        achievement,
        year,
        category,
        subcategory,
        claim_nature,
        title,
        date_range,
        level,
        personal_role,
        current_stage,
        base_score,
        performance_score,
        claimed_score,
        notes,
    )
    db.commit()
    return RedirectResponse(f"/achievements/{achievement.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{achievement_id}/delete")
def delete_achievement(
    achievement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    db.delete(achievement)
    db.commit()
    return RedirectResponse("/achievements", status_code=status.HTTP_303_SEE_OTHER)
