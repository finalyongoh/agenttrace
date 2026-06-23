from __future__ import annotations

from fastapi import FastAPI

from agenttrace.api.analysis import repository_router as repository_analysis_router
from agenttrace.api.analysis import router as analysis_router
from agenttrace.app.routers.health import router as health_router
from agenttrace.app.routers.reports import router as reports_router
from agenttrace.app.routers.summaries import router as summaries_router
from agenttrace.config import configure_runtime_environment


from contextlib import asynccontextmanager
from agenttrace.services.database import init_database
from agenttrace.api.analysis import init_api_stores


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = configure_runtime_environment()
    init_database(settings.database_url)
    init_api_stores(settings.database_url)
    yield


def create_app() -> FastAPI:
    settings = configure_runtime_environment()
    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(summaries_router, prefix="/v1")
    app.include_router(reports_router, prefix="/v1")
    app.include_router(analysis_router)
    app.include_router(repository_analysis_router)
    return app


app = create_app()
