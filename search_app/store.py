import asyncio
import logging

from search_app.config import SearchAppConfig
from search_app.services import TelegramAuthService, TokensService, UsersService
from shared.db.session import AsyncDatabaseManager
from shared.search.service import SearchService

logger = logging.getLogger(__name__)


class Store:
    def __init__(self, config: SearchAppConfig) -> None:
        self.media_base_url = config.minio_public_base_url
        self.db = AsyncDatabaseManager(config.database_url)
        self.search = SearchService(
            db=self.db,
            models_dir=config.models_dir,
            device=config.search_device,
        )
        self.telegram_auth = TelegramAuthService(
            bot_token=config.search_bot_token,
            mock_init_data=config.mock_init_data,
        )
        if config.mock_init_data:
            logger.warning(
                "mock_init_data is set; every login uses that user and skips the hash check"
            )
        self.tokens = TokensService(
            secret=config.search_jwt_secret,
            expiration=config.search_jwt_expiration,
        )
        self.users = UsersService(db=self.db, tokens=self.tokens)

    async def connect(self) -> None:
        await asyncio.to_thread(self.search.load)

    async def disconnect(self) -> None:
        await self.db.dispose()
