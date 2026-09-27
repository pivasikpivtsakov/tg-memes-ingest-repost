#!/usr/bin/env python3
"""
Script to list all allowed channels from config.json with their names and IDs.
Uses the sender_tg_app Telegram session.
"""
import asyncio
import json5
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient

from ingestion_app.config import config as app_config
from shared.redis import AllowedChatsRepository, create_redis


async def main() -> None:
    # Load config
    config_path = Path(__file__).parent.parent / 'config.json'
    with open(config_path, 'r') as f:
        config = json5.load(f)
    
    # Extract necessary config values
    api_id = config['telegram_api_id']
    api_hash = config['telegram_api_hash']
    session_name = config['sender_session_name']

    redis = create_redis(app_config.redis_url)
    allowed_chats = AllowedChatsRepository(redis=redis)
    stored_chats = await allowed_chats.all()

    # Create Telegram client with sender session
    client = TelegramClient(session_name, api_id, api_hash)
    
    print(f"Connecting using session: {session_name}")
    print(f"Found {len(stored_chats)} channels in Redis allowed_chats\n")
    print("=" * 70)
    
    try:
        async with client:
            # Get current user info
            me = await client.get_me()
            username = f"@{me.username}" if me.username else "No username"
            print(f"Logged in as: {me.first_name} {username} (ID: {me.id})")
            print("=" * 70)
            print()
            
            # Iterate through all stored chat IDs
            for idx, (chat_id, label) in enumerate(stored_chats.items(), 1):
                try:
                    # Optionally enrich with live channel info
                    entity = await client.get_entity(chat_id)
                    channel_name = getattr(entity, 'title', label or 'Unknown')
                    username_str = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else "No username"
                    
                    print(f"{idx}. {channel_name}")
                    print(f"   ID: {chat_id}")
                    print(f"   Label: {label}")
                    print(f"   Username: {username_str}")
                    print()
                    
                except Exception as e:
                    print(f"{idx}. {label or chat_id}")
                    print(f"   ID: {chat_id}")
                    print(f"   ⚠️  Could not enrich via Telegram: {e}")
                    print()
            
            print("=" * 70)
            print(f"Total: {len(stored_chats)} channels")
    
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())

