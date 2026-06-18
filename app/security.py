from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import SECRET_KEY
from app.database import get_db
from app.models import Role, User


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
auth_serializer = URLSafeSerializer(SECRET_KEY, salt="teacher-achievement-auth")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_auth_cookie(user_id: int) -> str:
    return auth_serializer.dumps({"user_id": user_id})


def parse_auth_cookie(cookie_value: str) -> int | None:
    try:
        data = auth_serializer.loads(cookie_value)
    except BadSignature:
        return None
    user_id = data.get("user_id") if isinstance(data, dict) else None
    return user_id if isinstance(user_id, int) else None


def get_current_user(
    request: Request,
    auth_user_id: str | None = Cookie(default=None, alias="user_id"),
    db: Session = Depends(get_db),
) -> User:
    if not auth_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    parsed_user_id = parse_auth_cookie(auth_user_id)
    if parsed_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication cookie",
        )

    user = db.query(User).filter(User.id == parsed_user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if (
        user.must_change_password
        and request.url.path not in {"/change-password", "/logout"}
    ):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/change-password"},
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != Role.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user
