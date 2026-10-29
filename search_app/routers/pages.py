from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from search_app.web.templates import templates

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")
