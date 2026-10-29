from fastapi import Request, Response
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException

from search_app.web.templates import templates


async def htmx_http_exception_handler(request: Request, exc: HTTPException) -> Response:
    if request.headers.get("HX-Request") != "true":
        response = await http_exception_handler(request, exc)
        return response
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": exc.status_code, "detail": exc.detail},
        status_code=exc.status_code,
        headers=exc.headers,
    )
