from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, DATA_DIR


templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def create_app() -> FastAPI:
    DATA_DIR.mkdir(exist_ok=True)
    app = FastAPI(title="教师成果管理系统")
    app.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "app" / "static")),
        name="static",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
