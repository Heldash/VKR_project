from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.deps import get_database_service
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.request_context import reset_request_id, set_request_id
from app.ui.router import router as ui_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Bootstraps app-scoped infrastructure before serving requests."""
    get_database_service().initialize()
    yield


def create_app() -> FastAPI:
    """Assemble the FastAPI application."""
    app = FastAPI(title=settings.project_name, version=settings.version, lifespan=lifespan)

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        token = set_request_id(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers["X-Request-ID"] = request_id
        return response

    app.mount("/ui/static", StaticFiles(directory="app/ui/static"), name="ui-static")
    app.include_router(ui_router)
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
