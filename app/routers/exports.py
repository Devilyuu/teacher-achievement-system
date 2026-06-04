from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user
from app.services.export_builder import build_personal_export


router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{year}/personal")
def export_personal(
    year: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    zip_path = build_personal_export(db, user, year)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )
