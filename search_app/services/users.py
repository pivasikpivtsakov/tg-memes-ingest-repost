from search_app.schemas import AuthResponse, TelegramUser
from search_app.services.tokens import TokensService
from shared.db.repositories import UserRepository
from shared.db.session import AsyncDatabaseManager


class UsersService:
    def __init__(self, *, db: AsyncDatabaseManager, tokens: TokensService) -> None:
        self._users = UserRepository(db)
        self._tokens = tokens

    async def sign_in(self, tg_user: TelegramUser) -> AuthResponse:
        await self._users.ensure(
            user_id=tg_user.id,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            username=tg_user.username,
        )
        token = self._tokens.issue(tg_user.id)
        return AuthResponse(token=token, user=tg_user)
