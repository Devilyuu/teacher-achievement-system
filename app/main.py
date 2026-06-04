from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, DATA_DIR
from app.database import Base, engine
from app.routers import achievements, admin, auth, dashboard, exports, materials
from app.seed_rules import seed_initial_data


templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def create_app() -> FastAPI:
    DATA_DIR.mkdir(exist_ok=True)
    app = FastAPI(title="教师成果管理系统")
    Base.metadata.create_all(bind=engine)
    seed_initial_data()

    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "app" / "static")),
        name="static",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)
    app.include_router(achievements.router)
    app.include_router(materials.router)
    app.include_router(exports.router)

    return app


app = create_app()
