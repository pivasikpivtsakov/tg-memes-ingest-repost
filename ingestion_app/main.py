import asyncio
import logging
from telethon import TelegramClient

from ingestion_app.config import config
from shared.logger import setup_logging
from ingestion_app.handlers import register_handlers

logger = logging.getLogger(__name__)


async def main() -> None:
    # Create the client with credentials from config
    client = TelegramClient(
        config.session_name,
        config.api_id,
        config.api_hash
    )
    
    logger.info("Starting Telegram client...")
    
    try:
        # Use async context manager (handles start and disconnect automatically)
        async with client:
            logger.info("Client started successfully!")
            
            # Get information about the current user
            me = await client.get_me()
            username = f"@{me.username}" if me.username else "No username"
            logger.info(f"Logged in as: {me.first_name} {username} (ID: {me.id})")
            
            # Register all event handlers
            register_handlers(client)
            
            logger.info("Listening for incoming messages... Press Ctrl+C to stop.")
            
            # Keep the client running until disconnected
            await client.run_until_disconnected()
        
        logger.info("Shutting down client...")
        
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
        raise


def run() -> None:
    setup_logging()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        exit(1)


if __name__ == '__main__':
    run()
