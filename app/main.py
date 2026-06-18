from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, DATA_DIR
from app.database import Base, engine
from app.routers import achievements, admin, auth, dashboard, exports, feedback, materials
from app.schema_updates import apply_schema_updates
from app.seed_rules import seed_initial_data


templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def create_app() -> FastAPI:
    DATA_DIR.mkdir(exist_ok=True)
    app = FastAPI(title="教师成果管理系统")
    Base.metadata.create_all(bind=engine)
    apply_schema_updates()
    seed_initial_data()

    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "app" / "static")),
        name="static",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(HTTPException)
    async def redirect_unauthenticated_pages(request: Request, exc: HTTPException):
        if (
            exc.status_code == status.HTTP_401_UNAUTHORIZED
            and request.method == "GET"
            and request.url.path != "/login"
        ):
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

        return await http_exception_handler(request, exc)

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)
    app.include_router(achievements.router)
    app.include_router(materials.router)
    app.include_router(exports.router)
    app.include_router(feedback.router)

    return app


app = create_app()
