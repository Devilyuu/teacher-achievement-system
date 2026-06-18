from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR
from app.models import User
from app.security import get_current_user
from app.services.reporting_year import default_reporting_year


router = APIRouter(prefix="/trial-guide", tags=["trial"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("")
def trial_guide(
    request: Request,
    user: User = Depends(get_current_user),
):
    reporting_year = default_reporting_year()
    return templates.TemplateResponse(
        request,
        "trial_guide.html",
        {
            "user": user,
            "reporting_year": reporting_year,
        },
    )
