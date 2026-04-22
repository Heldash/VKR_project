from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse


router = APIRouter(include_in_schema=False)
_STATIC_DIR = Path(__file__).parent / "static"


@router.get("/", summary="Redirect to UI")
async def root_redirect() -> RedirectResponse:
    """Sends the user to the dashboard instead of the raw API root."""
    return RedirectResponse(url="/ui", status_code=307)


@router.get("/ui", summary="Dashboard UI")
async def ui_index() -> FileResponse:
    """Serves the lightweight thesis dashboard."""
    return FileResponse(_STATIC_DIR / "index.html")
