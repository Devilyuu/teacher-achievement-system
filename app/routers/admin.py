from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import PerformanceRule, Role, User
from app.security import hash_password, require_admin
from app.services.performance_rule_guidance import assignment_mode


router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


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
        {"user": user, "users": users, "roles": [role.value for role in Role]},
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
    db.add(
        User(
            username=username.strip(),
            full_name=full_name.strip(),
            department=department.strip(),
            role=role.strip(),
            password_hash=hash_password(password),
        )
    )
    db.commit()
    return RedirectResponse("/admin/users", status_code=status.HTTP_303_SEE_OTHER)


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
