import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["dashboard"])

# Load HTML content from templates directory relative to this file
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(HERE, "templates", "dashboard.html")


@router.get("/")
def index_redirect() -> RedirectResponse:
    """Redirect root access to the dashboard."""
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard() -> HTMLResponse:
    """Serve the self-contained AgentGuard dashboard console."""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)
