from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from search_app.dependencies import StoreDep, get_user_auth
from search_app.web.templates import templates
from shared.search.ranking import CANDIDATE_LIMIT

router = APIRouter(prefix="/api", tags=["search"])

_PAGE_SIZE = 20


@router.post("/search", response_class=HTMLResponse, dependencies=[Depends(get_user_auth)])
async def search(
    request: Request,
    store: StoreDep,
    query: Annotated[str, Form()],
    limit: Annotated[int, Form(ge=1, le=_PAGE_SIZE)],
    offset: Annotated[int, Form(ge=0, le=CANDIDATE_LIMIT - _PAGE_SIZE)] = 0,
) -> HTMLResponse:
    hits, timings = await store.search.search(query, limit=limit, offset=offset)
    has_more = len(hits) == limit and offset + len(hits) < CANDIDATE_LIMIT
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "hits": hits,
            "timings": timings,
            "media_base_url": store.media_base_url,
            "query": query,
            "offset": offset,
            "page_size": limit,
            "has_more": has_more,
        },
    )
