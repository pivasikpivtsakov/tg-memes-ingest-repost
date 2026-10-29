from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.exceptions import HTTPException

from search_app.config import SearchAppConfig
from search_app.routers import auth_router, pages_router, search_router
from search_app.store import Store
from search_app.web.errors import htmx_http_exception_handler


def create_app(config: SearchAppConfig) -> FastAPI:
    store = Store(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[dict[str, Store]]:
        await store.connect()
        try:
            yield {"store": store}
        finally:
            await store.disconnect()

    app = FastAPI(
        title="Meme search",
        lifespan=lifespan,
        exception_handlers={HTTPException: htmx_http_exception_handler},
    )
    app.include_router(pages_router)
    app.include_router(auth_router)
    app.include_router(search_router)
    return app
