import logging

from telethon import TelegramClient

from sender_tg_app.config import config
from sender_tg_app.services import MemesSender
from shared.sender_base import AbstractSenderApp

logger = logging.getLogger(__name__)


class TelegramSenderApp(AbstractSenderApp):
    async def _run_sender(self) -> int:
        client = TelegramClient(
            self.config.session_name,
            self.config.api_id,
            self.config.api_hash
        )
        
        logger.info("Starting Telegram client...")
        
        async with client:
            logger.info("Client connected successfully!")
            
            me = await client.get_me()
            username = f"@{me.username}" if me.username else "No username"
            logger.info(f"Logged in as: {me.first_name} {username} (ID: {me.id})")
            
            sender = MemesSender(
                client=client,
                storage=self.storage,
                target_chat_id=self.config.target_chat_id,
                include_caption=self.config.include_caption
            )
            
            sent = await sender.send_meme()
            
            if sent is None:
                logger.info("No memes to send. Exiting.")
                return 0
            
            if sent:
                logger.info("Successfully sent a meme. Exiting.")
                return 0

            logger.error("Failed to send the meme. Exiting.")
            return 1

    def _log_startup_info(self) -> None:
        logger.info("Memes Sender App Starting")
        logger.info(f"Target channel: {self.config.target_chat_id}")
        logger.info(f"Include caption: {self.config.include_caption}")


def run() -> None:
    app = TelegramSenderApp(config)
    app.run()


if __name__ == '__main__':
    run()
