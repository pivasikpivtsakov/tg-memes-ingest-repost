from fastapi import APIRouter

from search_app.dependencies import StoreDep, TelegramUserDep
from search_app.schemas import AuthResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/telegram")
async def telegram_auth(store: StoreDep, tg_user: TelegramUserDep) -> AuthResponse:
    response = await store.users.sign_in(tg_user)
    return response
