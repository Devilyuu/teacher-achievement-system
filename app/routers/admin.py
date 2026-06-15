from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR, DATABASE_PATH, EXPORT_DIR, UPLOAD_DIR
from app.database import get_db
from app.models import Achievement, AchievementStatus, PerformanceRule, Role, User
from app.security import hash_password, require_admin
from app.services.admin_export_builder import (
    build_admin_material_package,
    build_admin_summary_workbook,
)
from app.services.admin_summary import SummaryFilters, build_admin_summary
from app.services.backup_builder import build_system_backup
from app.services.performance_rule_guidance import (
    assignment_mode,
    find_rule,
    rule_for_level,
)


router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _summary_filters(
    year: int | None,
    department: str,
    teacher_id: int | None,
    achievement_status: str,
) -> SummaryFilters:
    return SummaryFilters(
        year=year or datetime.now().year,
        department=department.strip(),
        teacher_id=teacher_id,
        status=achievement_status.strip(),
    )


def _summary_query_string(filters: SummaryFilters) -> str:
    values: dict[str, str | int] = {"year": filters.year}
    if filters.department:
        values["department"] = filters.department
    if filters.teacher_id is not None:
        values["teacher_id"] = filters.teacher_id
    if filters.status:
        values["status"] = filters.status
    return urlencode(values)


@router.get("/summary")
def annual_summary(
    request: Request,
    year: int | None = Query(default=None),
    department: str = Query(default=""),
    teacher_id: int | None = Query(default=None),
    achievement_status: str = Query(default="", alias="status"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = _summary_filters(
        year,
        department,
        teacher_id,
        achievement_status,
    )
    summary = build_admin_summary(db, filters)
    available_years = [
        row[0]
        for row in (
            db.query(Achievement.year)
            .join(Achievement.user)
            .filter(User.role == Role.teacher.value)
            .distinct()
            .order_by(Achievement.year.desc())
            .all()
        )
    ]
    departments = [
        row[0]
        for row in (
            db.query(User.department)
            .filter(
                User.role == Role.teacher.value,
                User.department != "",
            )
            .distinct()
            .order_by(User.department)
            .all()
        )
    ]
    teachers = (
        db.query(User)
        .filter(User.role == Role.teacher.value)
        .order_by(User.department, User.full_name)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/summary.html",
        {
            "user": user,
            "summary": summary,
            "filters": filters,
            "available_years": sorted(
                set([filters.year, datetime.now().year, *available_years]),
                reverse=True,
            ),
            "departments": departments,
            "teachers": teachers,
            "statuses": [item.value for item in AchievementStatus],
            "export_query": _summary_query_string(filters),
        },
    )


@router.get("/summary/export.xlsx")
def export_annual_summary_workbook(
    year: int | None = Query(default=None),
    department: str = Query(default=""),
    teacher_id: int | None = Query(default=None),
    achievement_status: str = Query(default="", alias="status"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = _summary_filters(
        year,
        department,
        teacher_id,
        achievement_status,
    )
    path = build_admin_summary_workbook(build_admin_summary(db, filters))
    return FileResponse(
        path,
        filename=path.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )


@router.get("/summary/materials.zip")
def export_annual_material_package(
    year: int | None = Query(default=None),
    department: str = Query(default=""),
    teacher_id: int | None = Query(default=None),
    achievement_status: str = Query(default="", alias="status"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = _summary_filters(
        year,
        department,
        teacher_id,
        achievement_status,
    )
    path = build_admin_material_package(build_admin_summary(db, filters))
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/zip",
    )


@router.get("/achievements/{achievement_id}")
def admin_achievement_detail(
    request: Request,
    achievement_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    achievement = db.get(Achievement, achievement_id)
    if not achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    rule = find_rule(db, achievement.category, achievement.subcategory)
    return templates.TemplateResponse(
        request,
        "admin/achievement_detail.html",
        {
            "user": user,
            "achievement": achievement,
            "rule": rule,
            "level_rule": rule_for_level(rule, achievement.level),
            "assignment_mode": assignment_mode(rule),
        },
    )


@router.get("/backup")
def backup_page(
    request: Request,
    user: User = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "admin/backup.html",
        {"user": user},
    )


@router.get("/backup/download")
def download_system_backup(
    user: User = Depends(require_admin),
):
    path = build_system_backup(DATABASE_PATH, UPLOAD_DIR, EXPORT_DIR)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/zip",
    )


@router.get("/users")
def list_users(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.department, User.full_name).all()
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": user,
            "users": users,
            "roles": [role.value for role in Role],
            "role_names": {
                Role.teacher.value: "教师",
                Role.admin.value: "管理员",
            },
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/users")
def create_user(
    username: str = Form(...),
    full_name: str = Form(...),
    department: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_username = username.strip()
    if db.query(User).filter(User.username == normalized_username).first():
        query = urlencode({"error": "用户名已存在"})
        return RedirectResponse(
            f"/admin/users?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if role not in {item.value for item in Role}:
        query = urlencode({"error": "用户角色无效"})
        return RedirectResponse(
            f"/admin/users?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if len(password) < 8:
        query = urlencode({"error": "初始密码至少需要 8 个字符"})
        return RedirectResponse(
            f"/admin/users?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.add(
        User(
            username=normalized_username,
            full_name=full_name.strip(),
            department=department.strip(),
            role=role.strip(),
            password_hash=hash_password(password),
            must_change_password=True,
        )
    )
    db.commit()
    query = urlencode({"success": "教师账号已创建"})
    return RedirectResponse(
        f"/admin/users?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _managed_user(db: Session, user_id: int) -> User:
    managed_user = db.get(User, user_id)
    if not managed_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return managed_user


@router.post("/users/{user_id}/toggle-active")
def toggle_user_active(
    user_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    managed_user = _managed_user(db, user_id)
    if managed_user.id == user.id:
        query = urlencode({"error": "不能停用当前登录的管理员账号"})
        return RedirectResponse(
            f"/admin/users?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    managed_user.is_active = not managed_user.is_active
    db.commit()
    message = "账号已启用" if managed_user.is_active else "账号已停用"
    return RedirectResponse(
        f"/admin/users?{urlencode({'success': message})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    new_password: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if len(new_password) < 8:
        return RedirectResponse(
            f"/admin/users?{urlencode({'error': '重置密码至少需要 8 个字符'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    managed_user = _managed_user(db, user_id)
    managed_user.password_hash = hash_password(new_password)
    managed_user.must_change_password = True
    db.commit()
    return RedirectResponse(
        f"/admin/users?{urlencode({'success': '密码已重置，用户下次登录需修改密码'})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/rules")
def list_rules(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rules = (
        db.query(PerformanceRule)
        .filter(PerformanceRule.is_active.is_(True))
        .order_by(PerformanceRule.sort_order, PerformanceRule.id)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/rules.html",
        {"user": user, "rules": rules, "assignment_mode": assignment_mode},
    )
