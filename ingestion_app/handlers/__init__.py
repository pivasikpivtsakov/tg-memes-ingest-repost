import logging
from telethon import TelegramClient

from ingestion_app.handlers.message import register_message_handler

logger = logging.getLogger(__name__)


def register_handlers(client: TelegramClient) -> None:
    register_message_handler(client)
    logger.info("All event handlers registered successfully")
