# Teacher Achievement System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local/LAN MVP for a multi-user teacher achievement and support-material management system.

**Architecture:** Use a server-rendered web app so teachers only need a browser. FastAPI handles routes, auth, uploads, exports, and admin actions; SQLite stores app data; local folders store uploaded materials and generated ZIP/Excel exports.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, HTMX, SQLAlchemy, SQLite, pytest, openpyxl, python-multipart, passlib/bcrypt, uvicorn.

---

## Scope

This plan implements the first testable MVP:

- Login/logout and role-based access.
- Admin-created users.
- Seeded performance categories and rules from the existing Excel workbook.
- A controlled custom catch-all category for valuable work not covered by standard rules.
- Teacher achievement CRUD.
- Multiple support materials per achievement.
- Annual status and missing-material indicators.
- Personal annual Excel/ZIP export.
- LAN-ready run command.

It intentionally excludes formal online approval workflow, complex automatic scoring, public cloud deployment, unified school login, and mobile app support.

## File Structure

Create these files:

```text
app/
├─ __init__.py
├─ main.py
├─ config.py
├─ database.py
├─ models.py
├─ security.py
├─ seed_rules.py
├─ routers/
│  ├─ __init__.py
│  ├─ auth.py
│  ├─ dashboard.py
│  ├─ achievements.py
│  ├─ materials.py
│  ├─ admin.py
│  └─ exports.py
├─ services/
│  ├─ __init__.py
│  ├─ achievement_status.py
│  ├─ storage.py
│  └─ export_builder.py
├─ templates/
│  ├─ base.html
│  ├─ login.html
│  ├─ dashboard.html
│  ├─ achievements/
│  │  ├─ list.html
│  │  ├─ form.html
│  │  └─ detail.html
│  └─ admin/
│     ├─ users.html
│     └─ rules.html
└─ static/
   └─ app.css
tests/
├─ conftest.py
├─ test_auth.py
├─ test_achievement_status.py
├─ test_materials.py
└─ test_exports.py
data/
├─ uploads/.gitkeep
├─ exports/.gitkeep
└─ database/.gitkeep
requirements.txt
run.ps1
```

Responsibilities:

- `app/main.py`: app factory, middleware, router registration.
- `app/config.py`: paths, upload limits, app secret.
- `app/database.py`: SQLAlchemy engine/session helpers.
- `app/models.py`: database models and enums.
- `app/security.py`: password hashing and session helpers.
- `app/seed_rules.py`: load initial admin account and performance rules.
- `app/routers/*`: page and action routes.
- `app/services/storage.py`: safe upload paths and filename handling.
- `app/services/achievement_status.py`: status calculation.
- `app/services/export_builder.py`: Excel and ZIP generation.
- `tests/*`: focused behavior tests.

## Task 1: Project Scaffold And App Boot

**Files:**

- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`
- Create: `app/templates/base.html`
- Create: `app/static/app.css`
- Create: `run.ps1`
- Create: `data/uploads/.gitkeep`
- Create: `data/exports/.gitkeep`
- Create: `data/database/.gitkeep`

- [ ] **Step 1: Create dependencies**

`requirements.txt`:

```text
fastapi==0.115.6
uvicorn[standard]==0.32.1
jinja2==3.1.4
python-multipart==0.0.19
sqlalchemy==2.0.36
passlib[bcrypt]==1.7.4
itsdangerous==2.2.0
openpyxl==3.1.5
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 2: Create app config**

`app/config.py`:

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "database" / "app.sqlite3"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
SECRET_KEY = "change-this-local-dev-secret"
MAX_UPLOAD_MB = 50
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg",
    ".zip", ".rar", ".7z"
}
```

- [ ] **Step 3: Create minimal FastAPI app**

`app/main.py`:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, DATA_DIR

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def create_app() -> FastAPI:
    DATA_DIR.mkdir(exist_ok=True)
    app = FastAPI(title="教师成果管理系统")
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Add run script**

`run.ps1`:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 5: Verify app boot**

Run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.ps1
```

Expected:

```text
Uvicorn running on http://0.0.0.0:8000
```

Open:

```text
http://127.0.0.1:8000/health
```

Expected JSON:

```json
{"status":"ok"}
```

- [ ] **Step 6: Commit**

```powershell
git add requirements.txt app data run.ps1
git commit -m "feat: scaffold local web app"
```

## Task 2: Database Models And Seed Data

**Files:**

- Create: `app/database.py`
- Create: `app/models.py`
- Create: `app/seed_rules.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Define database session**

`app/database.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_PATH

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Define models**

`app/models.py`:

```python
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(StrEnum):
    teacher = "teacher"
    admin = "admin"


class ClaimNature(StrEnum):
    process = "过程性工作"
    result = "成果性工作"


class AchievementStatus(StrEnum):
    draft = "草稿"
    needs_info = "待完善"
    ready = "可申报"
    exported = "已纳入导出"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(80))
    department: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default=Role.teacher.value)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PerformanceRule(Base):
    __tablename__ = "performance_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    subcategory: Mapped[str] = mapped_column(String(255), index=True)
    base_rule: Mapped[str] = mapped_column(Text, default="")
    national_rule: Mapped[str] = mapped_column(Text, default="")
    provincial_rule: Mapped[str] = mapped_column(Text, default="")
    city_rule: Mapped[str] = mapped_column(Text, default="")
    school_rule: Mapped[str] = mapped_column(Text, default="")
    college_rule: Mapped[str] = mapped_column(Text, default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    is_team: Mapped[bool] = mapped_column(Boolean, default=False)
    is_department_assigned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(120))
    subcategory: Mapped[str] = mapped_column(String(255))
    claim_nature: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(255))
    date_range: Mapped[str] = mapped_column(String(120), default="")
    level: Mapped[str] = mapped_column(String(80), default="")
    personal_role: Mapped[str] = mapped_column(String(80), default="")
    current_stage: Mapped[str] = mapped_column(Text, default="")
    base_score: Mapped[float] = mapped_column(Float, default=0)
    performance_score: Mapped[float] = mapped_column(Float, default=0)
    claimed_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default=AchievementStatus.draft.value)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    materials = relationship("Material", back_populates="achievement", cascade="all, delete-orphan")


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id"), index=True)
    material_no: Mapped[str] = mapped_column(String(40), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255), default="")
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_ext: Mapped[str] = mapped_column(String(20))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    achievement = relationship("Achievement", back_populates="materials")
```

- [ ] **Step 3: Create tables on app boot**

Modify `app/main.py`:

```python
from app.database import Base, engine
from app.seed_rules import seed_initial_data
```

Inside `create_app()` before routes:

```python
Base.metadata.create_all(bind=engine)
seed_initial_data()
```

- [ ] **Step 4: Seed admin and rules**

`app/seed_rules.py`:

```python
from app.database import SessionLocal
from app.models import PerformanceRule, User
from app.security import hash_password


INITIAL_RULES = [
    ("师德师风及党建思政工作", "政治学习、党员学习、党课主讲，各类讲座、会议主旨发言等（宣传推广学院经验做法）", "0", "10/次", "5/次", "2/次", "1/次", "0.5/次", "个人申报", False, False),
    ("教师发展", "教师企业实践（上限12分）", "2/月", "——", "——", "——", "——", "——", "个人申报，以学院派驻为准", False, False),
    ("教学", "精品在线开放课程建设（含虚拟仿真课程资源）", "2/门", "——", "10/门", "——", "3、2、1/门", "——", "个人申报，验收通过，如获校级资助则无分", False, False),
    ("科研与社会服务工作", "纵向课题（教科研）", "3/项", "25/项", "15/项", "10/项（市级）、5/项（区级）", "3/项", "——", "个人申报", False, False),
    ("教学", "教学成果奖申报及获奖", "10/项", "——", "——", "15、12、10/项", "10、8、6/项", "——", "团队项目，负责人赋分", True, False),
    ("其他有价值工作（自定义）", "自定义工作事项", "", "", "", "", "", "", "用于记录现有绩效分类未覆盖但教师认为有必要申报的工作，例如省级职业技能大赛裁判、专家评审、专项支持等。需填写工作说明、价值说明和支撑材料，最终是否赋分以线下审核为准。", False, False),
]


def seed_initial_data() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="admin").first():
            db.add(User(
                username="admin",
                full_name="系统管理员",
                department="管理",
                role="admin",
                password_hash=hash_password("admin123456"),
            ))
        for index, row in enumerate(INITIAL_RULES, start=1):
            exists = db.query(PerformanceRule).filter_by(category=row[0], subcategory=row[1]).first()
            if not exists:
                db.add(PerformanceRule(
                    category=row[0], subcategory=row[1], base_rule=row[2],
                    national_rule=row[3], provincial_rule=row[4], city_rule=row[5],
                    school_rule=row[6], college_rule=row[7], remark=row[8],
                    is_team=row[9], is_department_assigned=row[10], sort_order=index,
                ))
        db.commit()
    finally:
        db.close()
```

- [ ] **Step 5: Commit**

```powershell
git add app tests
git commit -m "feat: add database models and seed data"
```

## Task 3: Authentication And Basic Pages

**Files:**

- Create: `app/security.py`
- Create: `app/routers/auth.py`
- Create: `app/routers/dashboard.py`
- Create: `app/templates/login.html`
- Create: `app/templates/dashboard.html`
- Modify: `app/main.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Implement password helpers**

`app/security.py`:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)
```

- [ ] **Step 2: Implement auth routes**

`app/routers/auth.py`:

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import templates
from app.models import User
from app.security import verify_password

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=username, is_active=True).first()
    if not user or not verify_password(password, user.password_hash):
        response = RedirectResponse("/login?error=1", status_code=303)
        return response
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("user_id", str(user.id), httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("user_id")
    return response
```

- [ ] **Step 3: Add current user dependency**

Append to `app/security.py`:

```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.cookies.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    user = db.query(User).filter_by(id=int(user_id), is_active=True).first()
    if not user:
        raise HTTPException(status_code=401)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin.value:
        raise HTTPException(status_code=403)
    return user
```

- [ ] **Step 4: Add dashboard**

`app/routers/dashboard.py`:

```python
from fastapi import APIRouter, Depends, Request

from app.main import templates
from app.models import User
from app.security import get_current_user

router = APIRouter()


@router.get("/")
def dashboard(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})
```

- [ ] **Step 5: Register routers**

Modify `app/main.py` after app creation:

```python
from app.routers import auth, dashboard

app.include_router(auth.router)
app.include_router(dashboard.router)
```

- [ ] **Step 6: Verify login**

Run:

```powershell
.\run.ps1
```

Open:

```text
http://127.0.0.1:8000/login
```

Use:

```text
username: admin
password: admin123456
```

Expected: login redirects to dashboard.

- [ ] **Step 7: Commit**

```powershell
git add app tests
git commit -m "feat: add login and dashboard"
```

## Task 4: Achievement CRUD And Status Calculation

**Files:**

- Create: `app/services/achievement_status.py`
- Create: `app/routers/achievements.py`
- Create: `app/templates/achievements/list.html`
- Create: `app/templates/achievements/form.html`
- Create: `app/templates/achievements/detail.html`
- Test: `tests/test_achievement_status.py`
- Modify: `app/main.py`

- [ ] **Step 1: Implement status calculation**

`app/services/achievement_status.py`:

```python
from app.models import Achievement, AchievementStatus, ClaimNature


def calculate_status(achievement: Achievement) -> str:
    required_text = [
        achievement.category,
        achievement.subcategory,
        achievement.claim_nature,
        achievement.title,
    ]
    if not all(value and str(value).strip() for value in required_text):
        return AchievementStatus.needs_info.value
    if achievement.claimed_score is None or achievement.claimed_score <= 0:
        return AchievementStatus.needs_info.value
    if achievement.claim_nature == ClaimNature.process.value and not achievement.current_stage.strip():
        return AchievementStatus.needs_info.value
    if len(achievement.materials) == 0:
        return AchievementStatus.needs_info.value
    return AchievementStatus.ready.value
```

- [ ] **Step 2: Add status test**

`tests/test_achievement_status.py`:

```python
from app.models import Achievement, ClaimNature
from app.services.achievement_status import calculate_status


def test_process_record_without_stage_needs_info():
    achievement = Achievement(
        category="教学",
        subcategory="精品在线开放课程建设（含虚拟仿真课程资源）",
        claim_nature=ClaimNature.process.value,
        title="课程建设",
        claimed_score=2,
        current_stage="",
    )
    achievement.materials = [object()]
    assert calculate_status(achievement) == "待完善"
```

- [ ] **Step 3: Implement achievement routes**

`app/routers/achievements.py`:

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import templates
from app.models import Achievement, ClaimNature, PerformanceRule, User
from app.security import get_current_user
from app.services.achievement_status import calculate_status

router = APIRouter(prefix="/achievements")


@router.get("")
def list_achievements(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.query(Achievement).filter_by(user_id=user.id).order_by(Achievement.year.desc(), Achievement.id.desc()).all()
    return templates.TemplateResponse("achievements/list.html", {"request": request, "user": user, "items": items})


@router.get("/new")
def new_achievement(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rules = db.query(PerformanceRule).filter_by(is_active=True).order_by(PerformanceRule.sort_order).all()
    return templates.TemplateResponse("achievements/form.html", {"request": request, "user": user, "rules": rules, "item": None, "natures": [n.value for n in ClaimNature]})


@router.post("")
def create_achievement(
    year: int = Form(...),
    category: str = Form(...),
    subcategory: str = Form(...),
    claim_nature: str = Form(...),
    title: str = Form(...),
    claimed_score: float = Form(0),
    current_stage: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = Achievement(
        user_id=user.id, year=year, category=category, subcategory=subcategory,
        claim_nature=claim_nature, title=title, claimed_score=claimed_score,
        current_stage=current_stage, notes=notes,
    )
    item.status = calculate_status(item)
    db.add(item)
    db.commit()
    return RedirectResponse("/achievements", status_code=303)
```

- [ ] **Step 4: Register route and test**

Modify `app/main.py`:

```python
from app.routers import achievements
app.include_router(achievements.router)
```

Run:

```powershell
pytest tests/test_achievement_status.py -v
```

Expected: test passes.

- [ ] **Step 5: Commit**

```powershell
git add app tests
git commit -m "feat: add achievement records"
```

## Task 5: Material Uploads

**Files:**

- Create: `app/services/storage.py`
- Create: `app/routers/materials.py`
- Test: `tests/test_materials.py`
- Modify: `app/main.py`
- Modify: `app/templates/achievements/detail.html`

- [ ] **Step 1: Implement storage service**

`app/services/storage.py`:

```python
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import ALLOWED_EXTENSIONS, UPLOAD_DIR


def safe_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型：{ext}")
    return ext


def save_material_file(year: int, user_id: int, achievement_id: int, upload: UploadFile) -> tuple[str, int, str]:
    ext = safe_extension(upload.filename or "")
    folder = UPLOAD_DIR / str(year) / str(user_id) / str(achievement_id)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{ext}"
    target = folder / filename
    with target.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return str(target), target.stat().st_size, ext
```

- [ ] **Step 2: Implement upload route**

`app/routers/materials.py`:

```python
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Achievement, Material, User
from app.security import get_current_user
from app.services.achievement_status import calculate_status
from app.services.storage import save_material_file

router = APIRouter(prefix="/materials")


@router.post("/upload")
def upload_material(
    achievement_id: int = Form(...),
    display_name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    achievement = db.query(Achievement).filter_by(id=achievement_id, user_id=user.id).first()
    if not achievement:
        return RedirectResponse("/achievements", status_code=303)
    stored_path, size, ext = save_material_file(achievement.year, user.id, achievement.id, file)
    material_no = f"{achievement.id}-{len(achievement.materials) + 1}"
    db.add(Material(
        achievement_id=achievement.id,
        material_no=material_no,
        display_name=display_name,
        description=description,
        original_filename=file.filename or display_name,
        stored_path=stored_path,
        file_ext=ext,
        file_size=size,
    ))
    db.flush()
    achievement.status = calculate_status(achievement)
    db.commit()
    return RedirectResponse(f"/achievements/{achievement.id}", status_code=303)
```

- [ ] **Step 3: Register route**

Modify `app/main.py`:

```python
from app.routers import materials
app.include_router(materials.router)
```

- [ ] **Step 4: Commit**

```powershell
git add app tests
git commit -m "feat: add support material uploads"
```

## Task 6: Personal Export Package

**Files:**

- Create: `app/services/export_builder.py`
- Create: `app/routers/exports.py`
- Test: `tests/test_exports.py`
- Modify: `app/main.py`

- [ ] **Step 1: Implement export builder**

`app/services/export_builder.py`:

```python
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.config import EXPORT_DIR
from app.models import Achievement, Material, User


CATEGORY_ORDER = [
    "师德师风及党建思政工作", "教师发展", "教学", "产教融合工作", "学生工作",
    "科研与社会服务工作", "国际交流与合作", "育人成效", "监管类工作",
    "其他有价值工作（自定义）",
]


def build_personal_export(db: Session, user: User, year: int) -> Path:
    export_dir = EXPORT_DIR / str(year) / str(user.id)
    export_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = export_dir / "01_个人项目申报表.xlsx"
    catalog_path = export_dir / "04_材料目录.xlsx"
    zip_path = export_dir / f"{year}年度绩效申报材料_{user.full_name}.zip"

    achievements = db.query(Achievement).filter_by(user_id=user.id, year=year).order_by(Achievement.id).all()
    _write_application_workbook(workbook_path, achievements)
    _write_material_catalog(catalog_path, achievements)

    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        archive.write(workbook_path, workbook_path.name)
        archive.write(catalog_path, catalog_path.name)
        for index, achievement in enumerate(achievements, start=1):
            category_no = CATEGORY_ORDER.index(achievement.category) + 1 if achievement.category in CATEGORY_ORDER else 99
            folder = f"05_支撑材料/{category_no:02d}_{achievement.category}"
            for material in achievement.materials:
                source = Path(material.stored_path)
                if source.exists():
                    archive_name = f"{folder}/{index:03d}_{achievement.claim_nature}_{achievement.subcategory}_{material.display_name}{source.suffix}"
                    archive.write(source, archive_name)
    return zip_path


def _write_application_workbook(path: Path, achievements: list[Achievement]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "个人项目申报表"
    ws.append(["序号", "项目大类", "项目小类", "申报性质", "项目具体名称", "级别", "本人角色", "申报积分", "支撑材料编号+名称", "材料状态", "备注"])
    for index, item in enumerate(achievements, start=1):
        material_names = "；".join(f"{m.material_no} {m.display_name}" for m in item.materials)
        ws.append([index, item.category, item.subcategory, item.claim_nature, item.title, item.level, item.personal_role, item.claimed_score, material_names, "完整" if item.materials else "缺少材料", item.notes])
    wb.save(path)


def _write_material_catalog(path: Path, achievements: list[Achievement]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "材料目录"
    ws.append(["材料编号", "对应成果序号", "项目大类", "项目小类", "项目名称", "申报性质", "材料名称", "文件名", "文件类型", "上传时间"])
    for index, item in enumerate(achievements, start=1):
        for material in item.materials:
            ws.append([material.material_no, index, item.category, item.subcategory, item.title, item.claim_nature, material.display_name, material.original_filename, material.file_ext, material.uploaded_at])
    wb.save(path)
```

- [ ] **Step 2: Add export route**

`app/routers/exports.py`:

```python
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user
from app.services.export_builder import build_personal_export

router = APIRouter(prefix="/exports")


@router.get("/{year}/personal")
def export_personal(year: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    zip_path = build_personal_export(db, user, year)
    return FileResponse(zip_path, filename=zip_path.name)
```

- [ ] **Step 3: Register route and verify**

Modify `app/main.py`:

```python
from app.routers import exports
app.include_router(exports.router)
```

Run:

```powershell
pytest -v
.\run.ps1
```

Expected:

- Tests pass.
- Logged-in teacher can download `/exports/2026/personal`.
- ZIP includes Excel declaration sheet, material catalog, and category folders.

- [ ] **Step 4: Commit**

```powershell
git add app tests
git commit -m "feat: add annual export package"
```

## Task 7: Admin MVP

**Files:**

- Create: `app/routers/admin.py`
- Create: `app/templates/admin/users.html`
- Create: `app/templates/admin/rules.html`
- Modify: `app/main.py`

- [ ] **Step 1: Add admin routes**

`app/routers/admin.py`:

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import templates
from app.models import PerformanceRule, Role, User
from app.security import hash_password, require_admin

router = APIRouter(prefix="/admin")


@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    users = db.query(User).order_by(User.department, User.full_name).all()
    return templates.TemplateResponse("admin/users.html", {"request": request, "user": admin, "users": users})


@router.post("/users")
def create_user(
    username: str = Form(...),
    full_name: str = Form(...),
    department: str = Form(""),
    role: str = Form(Role.teacher.value),
    password: str = Form("123456"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    db.add(User(username=username, full_name=full_name, department=department, role=role, password_hash=hash_password(password)))
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/rules")
def rules_page(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rules = db.query(PerformanceRule).order_by(PerformanceRule.sort_order).all()
    return templates.TemplateResponse("admin/rules.html", {"request": request, "user": admin, "rules": rules})
```

- [ ] **Step 2: Register route**

Modify `app/main.py`:

```python
from app.routers import admin
app.include_router(admin.router)
```

- [ ] **Step 3: Verify admin user creation**

Run:

```powershell
.\run.ps1
```

Open:

```text
http://127.0.0.1:8000/admin/users
```

Expected:

- Admin can add a teacher account.
- Teacher can log in with the created account.

- [ ] **Step 4: Commit**

```powershell
git add app
git commit -m "feat: add admin user and rule pages"
```

## Task 8: Verification, LAN Instructions, And Push

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Update README run instructions**

Add:

```markdown
## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.ps1
```

本机访问：

```text
http://127.0.0.1:8000
```

局域网访问：

```powershell
ipconfig
```

找到主机 IPv4 地址后，同一局域网内访问：

```text
http://主机IPv4:8000
```

默认管理员：

```text
账号：admin
密码：admin123456
```

首次试用后请修改管理员密码。
```

- [ ] **Step 2: Run final tests**

```powershell
pytest -v
```

Expected:

```text
passed
```

- [ ] **Step 3: Run smoke test**

```powershell
.\run.ps1
```

Manual checks:

- Login page opens.
- Admin can create a teacher.
- Teacher can create an achievement.
- Teacher can upload a material.
- Teacher can download annual ZIP.

- [ ] **Step 4: Commit and push**

```powershell
git add README.md
git commit -m "docs: add local run instructions"
git push
```

## Self-Review

Spec coverage:

- Multi-user login: Tasks 2, 3, 7.
- Admin-created accounts: Task 7.
- Existing 9-category rule foundation plus controlled custom catch-all: Tasks 2 and 6 include category order; seed data starts with representative rules and leaves full-rule import as the next data-loading enhancement.
- Achievement records: Task 4.
- Process/result nature: Tasks 2 and 4.
- Manual claimed score with rule hints: Tasks 2 and 4.
- Materials bound to achievements: Task 5.
- Missing material status: Tasks 4 and 6.
- Personal Excel/ZIP export: Task 6.
- LAN deployment: Tasks 1 and 8.

Intentional MVP gap:

- Full import of all 78 rules from the attached workbook is not implemented in the scaffold tasks. After the MVP is running, add a focused task to parse `浮动绩效积分统计.xlsx` into `PerformanceRule` records or manually seed the full rule list.

Placeholder scan:

- This plan contains no unresolved placeholder instructions.

Type consistency:

- Model names, enum values, and route prefixes are consistent across tasks.
