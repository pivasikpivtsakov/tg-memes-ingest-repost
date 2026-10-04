from aiogram import Dispatcher
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.i18n import FSMI18nMiddleware, I18n
from redis.asyncio import Redis
from telethon import TelegramClient

from admin_bot.handlers import admins, channels, fallback, language, meme_info, start
from admin_bot.middlewares.access import AccessMiddleware
from admin_bot.middlewares.menu import MenuMiddleware
from admin_bot.services.media import MediaLookup
from shared.redis import AdminIdsRepository, AllowedChatsRepository


def build_dispatcher(
    *,
    redis: Redis,
    redis_url: str,
    i18n: I18n,
    media_lookup: MediaLookup,
    target_chat_id: str,
    tg_client: TelegramClient,
) -> Dispatcher:
    storage = RedisStorage.from_url(
        redis_url,
        key_builder=DefaultKeyBuilder(prefix="admin_bot_fsm", with_destiny=True),
    )
    dispatcher = Dispatcher(storage=storage)
    admins_repo = AdminIdsRepository(redis=redis)
    allowed_chats = AllowedChatsRepository(redis=redis)
    dispatcher.workflow_data.update(
        {
            "admins": admins_repo,
            "allowed_chats": allowed_chats,
            "tg_client": tg_client,
            "media_lookup": media_lookup,
            "config_target_chat_id": target_chat_id,
        }
    )
    dispatcher.update.middleware(FSMI18nMiddleware(i18n=i18n))
    dispatcher.update.middleware(AccessMiddleware(admins=admins_repo))
    dispatcher.message.outer_middleware(MenuMiddleware(i18n=i18n))

    dispatcher.include_router(start.router)
    dispatcher.include_router(channels.router)
    dispatcher.include_router(admins.router)
    dispatcher.include_router(language.router)
    dispatcher.include_router(meme_info.router)
    dispatcher.include_router(fallback.router)
    return dispatcher
