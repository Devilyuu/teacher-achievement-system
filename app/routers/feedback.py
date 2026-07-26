from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import TrialFeedback, User
from app.security import get_current_user


router = APIRouter(prefix="/feedback", tags=["feedback"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

ISSUE_TYPES = [
    "登录",
    "填报成果",
    "上传材料",
    "导出材料",
    "页面显示",
    "其他",
]


@router.get("")
def feedback_form(
    request: Request,
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "feedback/form.html",
        {
            "user": user,
            "issue_types": ISSUE_TYPES,
            "submitted": request.query_params.get("submitted") == "1",
        },
    )


@router.post("")
def submit_feedback(
    issue_type: str = Form(...),
    current_page: str = Form(""),
    related_title: str = Form(""),
    description: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_issue_type = issue_type.strip()
    if normalized_issue_type not in ISSUE_TYPES:
        normalized_issue_type = "其他"

    feedback = TrialFeedback(
        user_id=user.id,
        issue_type=normalized_issue_type,
        current_page=current_page.strip(),
        related_title=related_title.strip(),
        description=description.strip(),
        status="待处理",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(feedback)
    db.commit()
    return RedirectResponse(
        "/feedback?submitted=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )
