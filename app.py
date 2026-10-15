"""PDF-Audit-API 入口：装配 FastAPI，业务逻辑见 pipeline / services / api。"""

import logging

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from api.routes import router
from config import API_HOST, API_PORT, API_VERSION
from model import resolve_provider
from services.store import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("PDF-Audit-API")


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

if __name__ == "__main__":
    uvicorn.run("app:app", host=API_HOST, port=API_PORT, reload=True)
