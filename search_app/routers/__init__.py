from search_app.routers.auth import router as auth_router
from search_app.routers.pages import router as pages_router
from search_app.routers.search import router as search_router

__all__ = ["auth_router", "pages_router", "search_router"]
