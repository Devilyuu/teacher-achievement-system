from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import User
from app.security import create_auth_cookie, get_current_user, hash_password, verify_password


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"user": None, "error": None},
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username, User.is_active.is_(True)).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "user": None,
                "error": "用户名或密码错误",
                "username": username,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    destination = "/change-password" if user.must_change_password else "/"
    user.last_login_at = datetime.utcnow()
    db.commit()
    response = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        "user_id",
        create_auth_cookie(user.id),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/change-password")
def change_password_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "change_password.html",
        {"user": user, "error": None},
    )


@router.post("/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    error = None
    if not verify_password(current_password, user.password_hash):
        error = "当前密码不正确"
    elif len(new_password) < 8:
        error = "新密码至少需要 8 个字符"
    elif new_password != confirm_password:
        error = "两次输入的新密码不一致"

    if error:
        return templates.TemplateResponse(
            request,
            "change_password.html",
            {"user": user, "error": error},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("user_id")
    return response
