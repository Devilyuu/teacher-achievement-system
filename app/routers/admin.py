from datetime import datetime
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, or_
from sqlalchemy.orm import Session

from app.config import (
    BASE_DIR,
    DATABASE_PATH,
    EXPORT_DIR,
    SECRET_KEY,
    UPLOAD_DIR,
    USER_IMPORT_DIR,
)
from app.database import get_db
from app.models import (
    Achievement,
    AchievementStatus,
    ExportRecord,
    Material,
    PerformanceRule,
    Role,
    TrialFeedback,
    User,
)
from app.security import hash_password, require_admin
from app.services.admin_export_builder import (
    build_admin_material_package,
    build_admin_summary_workbook,
)
from app.services.admin_summary import SummaryFilters, build_admin_summary
from app.services.annual_submission import ANNUAL_STATUS_OPTIONS
from app.services.backup_builder import build_system_backup
from app.services.performance_rule_guidance import (
    assignment_mode,
    find_rule,
    rule_for_level,
)
from app.services.reporting_year import default_reporting_year
from app.services.material_preview import (
    PREVIEW_EXTENSIONS,
    preview_media_type,
    safe_material_path,
)
from app.services.user_import import (
    build_user_import_template,
    consume_import_batch,
    parse_user_import_workbook,
    store_import_batch,
)


router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

RULE_ASSIGNMENT_MODES = {
    "personal": ("个人申报", False, False),
    "team": ("团队负责人申报并分配", True, False),
    "assigned": ("项目负责人统一赋分", False, True),
}

FEEDBACK_STATUSES = ["待处理", "已确认", "已解决", "暂不处理"]


def _summary_filters(
    year: int | None,
    department: str,
    teacher_id: int | None,
    achievement_status: str,
    annual_status: str,
) -> SummaryFilters:
    return SummaryFilters(
        year=year or default_reporting_year(),
        department=department.strip(),
        teacher_id=teacher_id,
        status=achievement_status.strip(),
        annual_status=annual_status.strip(),
    )


def _summary_query_string(filters: SummaryFilters) -> str:
    values: dict[str, str | int] = {"year": filters.year}
    if filters.department:
        values["department"] = filters.department
    if filters.teacher_id is not None:
        values["teacher_id"] = filters.teacher_id
    if filters.status:
        values["status"] = filters.status
    if filters.annual_status:
        values["annual_status"] = filters.annual_status
    return urlencode(values)


def _trial_progress(db: Session) -> dict[str, int]:
    teacher_query = db.query(User).filter(User.role == Role.teacher.value)
    teacher_ids = [row[0] for row in teacher_query.with_entities(User.id).all()]
    if not teacher_ids:
        return {
            "teacher_count": 0,
            "logged_in_count": 0,
            "password_changed_count": 0,
            "achievement_user_count": 0,
            "material_user_count": 0,
            "exported_user_count": 0,
            "feedback_count": 0,
            "open_feedback_count": 0,
        }

    return {
        "teacher_count": teacher_query.count(),
        "logged_in_count": teacher_query.filter(User.last_login_at.is_not(None)).count(),
        "password_changed_count": teacher_query.filter(
            User.must_change_password.is_(False)
        ).count(),
        "achievement_user_count": db.query(distinct(Achievement.user_id))
        .filter(Achievement.user_id.in_(teacher_ids))
        .count(),
        "material_user_count": db.query(distinct(Achievement.user_id))
        .join(Material)
        .filter(Achievement.user_id.in_(teacher_ids))
        .count(),
        "exported_user_count": db.query(distinct(ExportRecord.user_id))
        .filter(ExportRecord.user_id.in_(teacher_ids))
        .count(),
        "feedback_count": db.query(TrialFeedback)
        .filter(TrialFeedback.user_id.in_(teacher_ids))
        .count(),
        "open_feedback_count": db.query(TrialFeedback)
        .filter(
            TrialFeedback.user_id.in_(teacher_ids),
            TrialFeedback.status.in_(["待处理", "已确认"]),
        )
        .count(),
    }


def _trial_teacher_rows(db: Session) -> list[dict]:
    teachers = (
        db.query(User)
        .filter(User.role == Role.teacher.value)
        .order_by(User.department, User.full_name)
        .all()
    )
    rows: list[dict] = []
    for teacher in teachers:
        achievements = (
            db.query(Achievement)
            .filter(Achievement.user_id == teacher.id)
            .all()
        )
        achievement_ids = [achievement.id for achievement in achievements]
        material_count = (
            db.query(Material)
            .filter(Material.achievement_id.in_(achievement_ids))
            .count()
            if achievement_ids
            else 0
        )
        export_count = (
            db.query(ExportRecord)
            .filter(ExportRecord.user_id == teacher.id)
            .count()
        )
        rows.append(
            {
                "teacher": teacher,
                "achievement_count": len(achievements),
                "material_count": material_count,
                "export_count": export_count,
            }
        )
    return rows


@router.get("/trial")
def trial_dashboard(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    feedback_items = (
        db.query(TrialFeedback)
        .join(User)
        .order_by(TrialFeedback.created_at.desc(), TrialFeedback.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/trial.html",
        {
            "user": user,
            "metrics": _trial_progress(db),
            "teacher_rows": _trial_teacher_rows(db),
            "feedback_items": feedback_items,
            "feedback_statuses": FEEDBACK_STATUSES,
        },
    )


@router.post("/feedback/{feedback_id}/status")
def update_feedback_status(
    feedback_id: int,
    feedback_status: str = Form(alias="status"),
    admin_note: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    feedback = db.get(TrialFeedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    feedback.status = (
        feedback_status if feedback_status in FEEDBACK_STATUSES else "待处理"
    )
    feedback.admin_note = admin_note.strip()
    feedback.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/admin/trial", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/summary")
def annual_summary(
    request: Request,
    year: int | None = Query(default=None),
    department: str = Query(default=""),
    teacher_id: int | None = Query(default=None),
    achievement_status: str = Query(default="", alias="status"),
    annual_status: str = Query(default=""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = _summary_filters(
        year,
        department,
        teacher_id,
        achievement_status,
        annual_status,
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
                set(
                    [
                        filters.year,
                        default_reporting_year(),
                        datetime.now().year,
                        *available_years,
                    ]
                ),
                reverse=True,
            ),
            "departments": departments,
            "teachers": teachers,
            "statuses": [item.value for item in AchievementStatus],
            "annual_statuses": ANNUAL_STATUS_OPTIONS,
            "export_query": _summary_query_string(filters),
        },
    )


@router.get("/summary/export.xlsx")
def export_annual_summary_workbook(
    year: int | None = Query(default=None),
    department: str = Query(default=""),
    teacher_id: int | None = Query(default=None),
    achievement_status: str = Query(default="", alias="status"),
    annual_status: str = Query(default=""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = _summary_filters(
        year,
        department,
        teacher_id,
        achievement_status,
        annual_status,
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
    annual_status: str = Query(default=""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    filters = _summary_filters(
        year,
        department,
        teacher_id,
        achievement_status,
        annual_status,
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
            "preview_extensions": PREVIEW_EXTENSIONS,
        },
    )


@router.get("/materials/{material_id}/preview")
def admin_preview_material(
    material_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(
        safe_material_path(material),
        filename=material.original_filename,
        media_type=preview_media_type(material),
        content_disposition_type="inline",
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


@router.get("/users/import-template.xlsx")
def download_user_import_template(
    user: User = Depends(require_admin),
):
    return Response(
        content=build_user_import_template(),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="teacher_user_import_template.xlsx"'
            )
        },
    )


@router.post("/users/import-preview")
async def preview_user_import(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return templates.TemplateResponse(
            request,
            "admin/user_import_preview.html",
            {
                "user": user,
                "result": None,
                "batch_token": "",
                "file_error": "请上传 .xlsx 格式的 Excel 文件",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        result = parse_user_import_workbook(
            await file.read(),
            {
                row[0]
                for row in db.query(User.username).all()
            },
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "admin/user_import_preview.html",
            {
                "user": user,
                "result": None,
                "batch_token": "",
                "file_error": str(exc),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    file_error = "" if result.rows else "Excel 中没有可导入的账号"
    batch_token = ""
    if not result.has_errors and result.rows:
        batch_token = store_import_batch(
            result.rows,
            USER_IMPORT_DIR,
            SECRET_KEY,
        )
    return templates.TemplateResponse(
        request,
        "admin/user_import_preview.html",
        {
            "user": user,
            "result": result,
            "batch_token": batch_token,
            "file_error": file_error,
        },
    )


@router.post("/users/import-confirm")
def confirm_user_import(
    batch_token: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        rows = consume_import_batch(
            batch_token,
            USER_IMPORT_DIR,
            SECRET_KEY,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/users?{urlencode({'error': str(exc)})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    usernames = [row["username"] for row in rows]
    duplicate = (
        db.query(User.username)
        .filter(User.username.in_(usernames))
        .first()
    )
    if duplicate:
        return RedirectResponse(
            f"/admin/users?{urlencode({'error': f'账号 {duplicate[0]} 已存在，请重新预检'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    db.add_all(
        [
            User(
                username=row["username"],
                full_name=row["full_name"],
                department=row["department"],
                role=row["role"],
                password_hash=row["password_hash"],
                must_change_password=True,
            )
            for row in rows
        ]
    )
    db.commit()
    return RedirectResponse(
        f"/admin/users?{urlencode({'success': f'已批量导入 {len(rows)} 个账号'})}",
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
    status_filter: str = Query(default="active", alias="status"),
    q: str = Query(default=""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(PerformanceRule)
    if status_filter == "inactive":
        query = query.filter(PerformanceRule.is_active.is_(False))
    elif status_filter != "all":
        status_filter = "active"
        query = query.filter(PerformanceRule.is_active.is_(True))
    keyword = q.strip()
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                PerformanceRule.category.ilike(pattern),
                PerformanceRule.subcategory.ilike(pattern),
                PerformanceRule.remark.ilike(pattern),
            )
        )
    rules = query.order_by(PerformanceRule.sort_order, PerformanceRule.id).all()
    return templates.TemplateResponse(
        request,
        "admin/rules.html",
        {
            "user": user,
            "rules": rules,
            "assignment_mode": assignment_mode,
            "status_filter": status_filter,
            "q": keyword,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


def _rule_assignment_key(rule: PerformanceRule | None) -> str:
    if rule and rule.is_team:
        return "team"
    if rule and rule.is_department_assigned:
        return "assigned"
    return "personal"


def _rule_form_context(
    request: Request,
    user: User,
    rule: PerformanceRule | None,
    action: str,
):
    return {
        "request": request,
        "user": user,
        "rule": rule,
        "action": action,
        "assignment_modes": RULE_ASSIGNMENT_MODES,
        "assignment_mode_key": _rule_assignment_key(rule),
    }


def _managed_rule(db: Session, rule_id: int) -> PerformanceRule:
    rule = db.get(PerformanceRule, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return rule


def _duplicate_rule(
    db: Session,
    category: str,
    subcategory: str,
    exclude_id: int | None = None,
) -> PerformanceRule | None:
    query = db.query(PerformanceRule).filter(
        PerformanceRule.category == category,
        PerformanceRule.subcategory == subcategory,
    )
    if exclude_id is not None:
        query = query.filter(PerformanceRule.id != exclude_id)
    return query.first()


def _assign_rule_values(
    rule: PerformanceRule,
    category: str,
    subcategory: str,
    base_rule: str,
    national_rule: str,
    provincial_rule: str,
    city_rule: str,
    school_rule: str,
    college_rule: str,
    assignment_mode_key: str,
    remark: str,
    sort_order: int,
) -> None:
    _, is_team, is_department_assigned = RULE_ASSIGNMENT_MODES[
        assignment_mode_key
    ]
    rule.category = category
    rule.subcategory = subcategory
    rule.base_rule = base_rule.strip()
    rule.national_rule = national_rule.strip()
    rule.provincial_rule = provincial_rule.strip()
    rule.city_rule = city_rule.strip()
    rule.school_rule = school_rule.strip()
    rule.college_rule = college_rule.strip()
    rule.is_team = is_team
    rule.is_department_assigned = is_department_assigned
    rule.remark = remark.strip()
    rule.sort_order = sort_order


@router.get("/rules/new")
def new_rule_form(
    request: Request,
    user: User = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "admin/rule_form.html",
        _rule_form_context(request, user, None, "/admin/rules"),
    )


@router.post("/rules")
def create_rule(
    category: str = Form(...),
    subcategory: str = Form(...),
    base_rule: str = Form(default=""),
    national_rule: str = Form(default=""),
    provincial_rule: str = Form(default=""),
    city_rule: str = Form(default=""),
    school_rule: str = Form(default=""),
    college_rule: str = Form(default=""),
    assignment_mode_key: str = Form(alias="assignment_mode"),
    remark: str = Form(default=""),
    sort_order: int = Form(default=0),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_category = category.strip()
    normalized_subcategory = subcategory.strip()
    if not normalized_category or not normalized_subcategory:
        return RedirectResponse(
            f"/admin/rules?{urlencode({'error': '大类和小类不能为空'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if assignment_mode_key not in RULE_ASSIGNMENT_MODES:
        return RedirectResponse(
            f"/admin/rules?{urlencode({'error': '赋分方式无效'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if _duplicate_rule(db, normalized_category, normalized_subcategory):
        return RedirectResponse(
            f"/admin/rules?{urlencode({'error': '该大类与小类规则已存在'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    rule = PerformanceRule(is_active=True)
    _assign_rule_values(
        rule,
        normalized_category,
        normalized_subcategory,
        base_rule,
        national_rule,
        provincial_rule,
        city_rule,
        school_rule,
        college_rule,
        assignment_mode_key,
        remark,
        sort_order,
    )
    db.add(rule)
    db.commit()
    return RedirectResponse(
        f"/admin/rules?{urlencode({'success': '绩效规则已创建'})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/rules/{rule_id}/edit")
def edit_rule_form(
    request: Request,
    rule_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rule = _managed_rule(db, rule_id)
    return templates.TemplateResponse(
        request,
        "admin/rule_form.html",
        _rule_form_context(
            request,
            user,
            rule,
            f"/admin/rules/{rule.id}/edit",
        ),
    )


@router.post("/rules/{rule_id}/edit")
def update_rule(
    rule_id: int,
    category: str = Form(...),
    subcategory: str = Form(...),
    base_rule: str = Form(default=""),
    national_rule: str = Form(default=""),
    provincial_rule: str = Form(default=""),
    city_rule: str = Form(default=""),
    school_rule: str = Form(default=""),
    college_rule: str = Form(default=""),
    assignment_mode_key: str = Form(alias="assignment_mode"),
    remark: str = Form(default=""),
    sort_order: int = Form(default=0),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rule = _managed_rule(db, rule_id)
    normalized_category = category.strip()
    normalized_subcategory = subcategory.strip()
    if not normalized_category or not normalized_subcategory:
        return RedirectResponse(
            f"/admin/rules?{urlencode({'error': '大类和小类不能为空'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if assignment_mode_key not in RULE_ASSIGNMENT_MODES:
        return RedirectResponse(
            f"/admin/rules?{urlencode({'error': '赋分方式无效'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if _duplicate_rule(
        db,
        normalized_category,
        normalized_subcategory,
        exclude_id=rule.id,
    ):
        return RedirectResponse(
            f"/admin/rules?{urlencode({'error': '该大类与小类规则已存在'})}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    _assign_rule_values(
        rule,
        normalized_category,
        normalized_subcategory,
        base_rule,
        national_rule,
        provincial_rule,
        city_rule,
        school_rule,
        college_rule,
        assignment_mode_key,
        remark,
        sort_order,
    )
    db.commit()
    return RedirectResponse(
        f"/admin/rules?{urlencode({'success': '绩效规则已更新'})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/rules/{rule_id}/toggle-active")
def toggle_rule_active(
    rule_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rule = _managed_rule(db, rule_id)
    rule.is_active = not rule.is_active
    db.commit()
    message = "绩效规则已启用" if rule.is_active else "绩效规则已停用"
    return RedirectResponse(
        f"/admin/rules?{urlencode({'success': message})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
