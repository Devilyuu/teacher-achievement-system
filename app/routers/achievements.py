from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import Achievement, ClaimNature, PerformanceRule, User
from app.security import get_current_user
from app.services.achievement_status import calculate_status


router = APIRouter(prefix="/achievements", tags=["achievements"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _active_rules(db: Session) -> list[PerformanceRule]:
    return (
        db.query(PerformanceRule)
        .filter(PerformanceRule.is_active.is_(True))
        .order_by(PerformanceRule.sort_order, PerformanceRule.id)
        .all()
    )


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
        "rules": _active_rules(db),
        "claim_natures": [nature.value for nature in ClaimNature],
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievements = (
        db.query(Achievement)
        .filter(Achievement.user_id == user.id)
        .order_by(Achievement.updated_at.desc(), Achievement.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "achievements/list.html",
        {"user": user, "achievements": achievements},
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
    return templates.TemplateResponse(
        request,
        "achievements/detail.html",
        {"user": user, "achievement": achievement},
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
