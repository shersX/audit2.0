"""PDF-Audit-API 入口：装配 FastAPI，业务逻辑见 pipeline / services / api。"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router
from config import API_HOST, API_PORT, API_VERSION
from model import resolve_provider
from services.store import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("PDF-Audit-API")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(f"当前默认使用模型 provider: {resolve_provider()}")
    yield


app = FastAPI(
    title="PDF-Audit-API",
    summary="PDF审核API",
    version=API_VERSION,
    lifespan=lifespan,
)
app.include_router(router)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index_page():
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        return {"status": "error", "message": "前端页面未找到，请确认 static/index.html 存在"}
    return FileResponse(index)


if __name__ == "__main__":
    uvicorn.run("app:app", host=API_HOST, port=API_PORT, reload=True)
