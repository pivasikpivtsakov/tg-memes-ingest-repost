import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from telethon import TelegramClient

from sender_tg_app.config import config
from sender_tg_app.main import TelegramSenderApp
from sender_tg_app.services import MemesSender
from shared.db import Media
from shared.logger import setup_logging
from shared.storage import MediaMetadata, MediaStorage


def load_media(storage: MediaStorage, media_id: int) -> MediaMetadata:
    with storage._get_session() as session:
        media = session.execute(select(Media).where(Media.id == media_id)).scalar_one()
        return MediaMetadata.model_validate(media)


async def main(media_id: int, target_chat_id: str) -> None:
    storage = TelegramSenderApp(config).storage
    media = load_media(storage=storage, media_id=media_id)
    client = TelegramClient(config.session_name, config.api_id, config.api_hash)
    async with client:
        sender = MemesSender(
            client=client,
            storage=storage,
            target_chat_id=target_chat_id,
            include_caption=config.include_caption,
        )
        await sender._ensure_entity_resolved()
        success = await sender._send_single_meme(media)
    print(f"media #{media_id} sent: {success}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('media_id', type=int)
    parser.add_argument('--chat', default=config.target_chat_id)
    args = parser.parse_args()
    setup_logging()
    asyncio.run(main(media_id=args.media_id, target_chat_id=args.chat))
