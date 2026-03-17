#!/usr/bin/env python3
"""
Script to list all allowed channels from config.json with their names and IDs.
Uses the sender_tg_app Telegram session.
"""
import asyncio
import json
from pathlib import Path
from telethon import TelegramClient


async def main():
    # Load config
    config_path = Path(__file__).parent.parent / 'config.json'
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Extract necessary config values
    api_id = config['telegram_api_id']
    api_hash = config['telegram_api_hash']
    session_name = config['sender_session_name']
    allowed_chat_ids = config['allowed_chat_ids']
    
    # Create Telegram client with sender session
    client = TelegramClient(session_name, api_id, api_hash)
    
    print(f"Connecting using session: {session_name}")
    print(f"Found {len(allowed_chat_ids)} channels in config.json\n")
    print("=" * 70)
    
    try:
        async with client:
            # Get current user info
            me = await client.get_me()
            username = f"@{me.username}" if me.username else "No username"
            print(f"Logged in as: {me.first_name} {username} (ID: {me.id})")
            print("=" * 70)
            print()
            
            # Iterate through all allowed chat IDs
            for idx, chat_id in enumerate(allowed_chat_ids, 1):
                try:
                    # Get the entity (channel/chat) information
                    entity = await client.get_entity(chat_id)
                    
                    # Get the title/name of the channel
                    channel_name = getattr(entity, 'title', 'Unknown')
                    username_str = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else "No username"
                    
                    print(f"{idx}. {channel_name}")
                    print(f"   ID: {chat_id}")
                    print(f"   Username: {username_str}")
                    print()
                    
                except Exception as e:
                    print(f"{idx}. ❌ Error fetching channel {chat_id}: {e}")
                    print()
            
            print("=" * 70)
            print(f"Total: {len(allowed_chat_ids)} channels")
    
    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

