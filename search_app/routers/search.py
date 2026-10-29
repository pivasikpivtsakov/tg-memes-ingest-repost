from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from search_app.dependencies import StoreDep, get_user_auth
from search_app.web.templates import templates

_SEARCH_LIMIT = 20

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_class=HTMLResponse, dependencies=[Depends(get_user_auth)])
async def search(
    request: Request,
    store: StoreDep,
    query: Annotated[str, Form()],
) -> HTMLResponse:
    hits, timings = await store.search.search(query, limit=_SEARCH_LIMIT)
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={"hits": hits, "timings": timings, "media_base_url": store.media_base_url},
    )
