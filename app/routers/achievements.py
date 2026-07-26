from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import (
    BASE_DIR,
    MAX_BATCH_UPLOAD_FILES,
    MAX_BATCH_UPLOAD_MB,
    MAX_UPLOAD_MB,
)
from app.database import get_db
from app.models import (
    Achievement,
    AchievementStatus,
    ClaimNature,
    FeishuSyncRecord,
    PerformanceRule,
    User,
)
from app.security import get_current_user
from app.services.achievement_readiness import missing_reasons
from app.services.achievement_draft_parser import parse_achievement_draft
from app.services.achievement_search import AchievementFilters, search_achievements
from app.services.achievement_status import calculate_status
from app.services.feishu_client import FeishuError
from app.services.feishu_sync import SyncResult, sync_achievement
from app.services.material_preview import PREVIEW_EXTENSIONS
from app.services.personal_integration import integration_status
from app.services.performance_rule_guidance import (
    LEVEL_OPTIONS,
    assignment_mode,
    find_rule,
    rule_for_level,
)
from app.services.reporting_year import (
    get_user_default_year,
    get_user_reporting_years,
)


router = APIRouter(prefix="/achievements", tags=["achievements"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

FEISHU_STATUS_NOTICES = {
    "synced": "飞书同步已完成。",
    "pending": "同步任务正在处理中，请稍后再查看。",
    "failed": "飞书同步未完成，本地成果不受影响，可稍后重试。",
    "conflict": "飞书中存在重复记录，请先人工处理后再重试。",
}
FEISHU_NOT_CONFIGURED_NOTICE = (
    "飞书同步尚未配置完整，请联系管理员补充服务器端配置。"
)


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


def _sync_after_local_commit(
    db: Session,
    achievement: Achievement,
    user: User,
) -> SyncResult | None:
    personal_status = integration_status(user.username)
    if not (personal_status.user_enabled and personal_status.feishu_ready):
        return None
    try:
        return sync_achievement(db, achievement)
    except FeishuError:
        db.rollback()
        return SyncResult(status="failed")


def _feishu_attempt_notice(
    request: Request,
    *,
    user_enabled: bool,
    feishu_ready: bool,
    sync_record: FeishuSyncRecord | None,
) -> str | None:
    if (
        not user_enabled
        or request.query_params.get("feishu") != "attempted"
    ):
        return None
    if not feishu_ready:
        return FEISHU_NOT_CONFIGURED_NOTICE
    sync_status = sync_record.sync_status if sync_record else "pending"
    return FEISHU_STATUS_NOTICES.get(
        sync_status,
        FEISHU_STATUS_NOTICES["pending"],
    )


def _form_context(
    request: Request,
    user: User,
    db: Session,
    achievement: Achievement | None = None,
    action: str = "/achievements",
    selected_year: int | None = None,
):
    form_year = (
        achievement.year
        if achievement
        else selected_year or get_user_default_year(db, user.id)
    )
    personal_status = integration_status(user.username)
    return {
        "request": request,
        "user": user,
        "achievement": achievement,
        "rules": [_rule_data(rule) for rule in _active_rules(db)],
        "claim_natures": [nature.value for nature in ClaimNature],
        "level_options": LEVEL_OPTIONS,
        "readiness_reasons": missing_reasons(achievement) if achievement else [],
        "selected_year": form_year,
        "available_years": get_user_reporting_years(
            db,
            user.id,
            form_year,
        ),
        "personal_integration": personal_status,
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
    selected_year = year or get_user_default_year(db, user.id)
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
            "available_years": get_user_reporting_years(
                db,
                user.id,
                selected_year,
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
    year: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "achievements/form.html",
        _form_context(request, user, db, selected_year=year),
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
    _sync_after_local_commit(db, achievement, user)
    return RedirectResponse(
        f"/achievements/{achievement.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/intelligent-draft")
def create_intelligent_draft(
    description: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    personal_status = integration_status(user.username)
    if not personal_status.user_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Intelligent entry is not available for this user",
        )
    try:
        draft = parse_achievement_draft(
            description,
            _active_rules(db),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请输入 1 至 2000 个字符的成果描述",
        ) from exc
    return {
        "draft": draft.model_dump(mode="json"),
        "mode": "ai" if personal_status.ai_ready else "rule",
    }


@router.post("/{achievement_id}/feishu-sync")
def retry_feishu_sync(
    achievement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    personal_status = integration_status(user.username)
    if not personal_status.user_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feishu sync is not available for this user",
        )
    if not personal_status.feishu_ready:
        return RedirectResponse(
            f"/achievements/{achievement.id}?feishu=attempted",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        sync_achievement(db, achievement)
    except FeishuError:
        db.rollback()
    return RedirectResponse(
        f"/achievements/{achievement.id}?feishu=attempted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{achievement_id}")
def achievement_detail(
    request: Request,
    achievement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    achievement = _achievement_for_user(db, achievement_id, user)
    rule = find_rule(db, achievement.category, achievement.subcategory)
    personal_status = integration_status(user.username)
    sync_record = None
    if personal_status.user_enabled:
        sync_record = (
            db.query(FeishuSyncRecord)
            .filter(FeishuSyncRecord.achievement_id == achievement.id)
            .first()
        )
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
            "max_batch_upload_files": MAX_BATCH_UPLOAD_FILES,
            "max_batch_upload_mb": MAX_BATCH_UPLOAD_MB,
            "preview_extensions": PREVIEW_EXTENSIONS,
            "readiness_reasons": missing_reasons(achievement),
            "personal_integration": personal_status,
            "feishu_sync_record": sync_record,
            "feishu_notice": _feishu_attempt_notice(
                request,
                user_enabled=personal_status.user_enabled,
                feishu_ready=personal_status.feishu_ready,
                sync_record=sync_record,
            ),
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
    _sync_after_local_commit(db, achievement, user)
    return RedirectResponse(
        f"/achievements/{achievement.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


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
