from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user
from app.services.reporting_year import get_user_default_year


router = APIRouter(prefix="/trial-guide", tags=["trial"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("")
def trial_guide(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reporting_year = get_user_default_year(db, user.id)
    return templates.TemplateResponse(
        request,
        "trial_guide.html",
        {
            "user": user,
            "reporting_year": reporting_year,
        },
    )
