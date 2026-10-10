import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient

from admin_bot.app import build_dispatcher
from admin_bot.config import config
from admin_bot.i18n import build_i18n
from admin_bot.services.media import MediaLookup
from shared.logger import setup_logging
from shared.redis import create_redis

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    i18n = build_i18n(default_locale=config.default_locale)
    redis = create_redis(config.redis_url)
    media_lookup = MediaLookup(database_url=config.database_url)
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    client = TelegramClient(
        config.session_name,
        config.api_id,
        config.api_hash,
        receive_updates=False,
    )
    logger.info("Starting admin bot polling")
    dispatcher = None
    try:
        async with client:
            me = await client.get_me()
            username = f"@{me.username}" if me.username else "No username"
            logger.info("Admin Telethon session as: %s %s (ID: %s)", me.first_name, username, me.id)
            dispatcher = build_dispatcher(
                redis=redis,
                redis_url=config.redis_url,
                i18n=i18n,
                media_lookup=media_lookup,
                target_chat_id=config.target_chat_id,
                tg_client=client,
            )
            await dispatcher.start_polling(bot)
    finally:
        if dispatcher is not None:
            await dispatcher.storage.close()
        await media_lookup.dispose()
        await bot.session.close()
        await redis.aclose()


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Admin bot stopped by user")


if __name__ == "__main__":
    run()
