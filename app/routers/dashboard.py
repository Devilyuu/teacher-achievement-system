from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR
from app.models import User
from app.security import get_current_user


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/")
def dashboard(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user},
    )
