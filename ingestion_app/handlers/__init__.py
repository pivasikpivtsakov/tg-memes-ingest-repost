import logging
from telethon import TelegramClient

from ingestion_app.handlers.message import register_message_handler

logger = logging.getLogger(__name__)


def register_handlers(client: TelegramClient) -> None:
    """Register all event handlers."""
    register_message_handler(client)
    
    # Add more handlers here as needed:
    # register_edited_message_handler(client)
    # register_channel_post_handler(client)
    
    logger.info("All event handlers registered successfully")

