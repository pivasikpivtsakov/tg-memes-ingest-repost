#!/usr/bin/env python3
"""
Script to join a Telegram channel by username and turn off notifications.
Uses the sender_tg_app Telegram session.

Usage:
    python join_channel.py <channel_username>
    
Example:
    python join_channel.py @mychannel
    python join_channel.py mychannel
"""
import asyncio
import json5
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telethon import TelegramClient, functions, types

from ingestion_app.config import config as app_config
from shared.redis import AllowedChatsRepository, create_redis


async def join_channel_and_mute(channel_username: str):
    """
    Join a Telegram channel and turn off notifications.
    
    Args:
        channel_username: Channel username (with or without @)
    """
    # Normalize username
    if not channel_username.startswith('@'):
        channel_username = f'@{channel_username}'
    
    # Load config
    config_path = Path(__file__).parent.parent / 'config.json'
    with open(config_path, 'r') as f:
        config = json5.load(f)
    
    # Extract necessary config values
    api_id = config['telegram_api_id']
    api_hash = config['telegram_api_hash']
    session_name = config['sender_session_name']
    
    # Create Telegram client with sender session
    client = TelegramClient(session_name, api_id, api_hash)

    redis = create_redis(app_config.redis_url)
    allowed_chats = AllowedChatsRepository(redis=redis)

    print(f"Connecting using session: {session_name}")
    print(f"Target channel: {channel_username}\n")
    print("=" * 70)
    
    try:
        async with client:
            # Get current user info
            me = await client.get_me()
            username = f"@{me.username}" if me.username else "No username"
            print(f"Logged in as: {me.first_name} {username} (ID: {me.id})")
            print("=" * 70)
            print()
            
            # Step 1: Get the channel entity
            print(f"🔍 Looking up channel: {channel_username}")
            try:
                channel = await client.get_entity(channel_username)
                print(f"✅ Found channel: {channel.title}")
                print(f"   ID: {channel.id}")
                print()
            except Exception as e:
                print(f"❌ Error: Could not find channel '{channel_username}'")
                print(f"   Details: {e}")
                return
            
            # Step 2: Join the channel
            print(f"📥 Joining channel...")
            try:
                result = await client(functions.channels.JoinChannelRequest(
                    channel=channel
                ))
                print(f"✅ Successfully joined '{channel.title}'")
                print()
            except Exception as e:
                # Check if already a member
                if "already" in str(e).lower():
                    print(f"ℹ️  Already a member of '{channel.title}'")
                    print()
                else:
                    print(f"❌ Error joining channel: {e}")
                    return
            
            # Step 3: Turn off notifications (mute)
            print(f"🔕 Turning off notifications...")
            try:
                await client(functions.account.UpdateNotifySettingsRequest(
                    peer=channel,
                    settings=types.InputPeerNotifySettings(
                        show_previews=False,
                        silent=True,
                        mute_until=2147483647  # Max timestamp (mute forever)
                    )
                ))
                print(f"✅ Notifications disabled for '{channel.title}'")
                print()
            except Exception as e:
                print(f"❌ Error disabling notifications: {e}")
                return
            
            # Step 4: Add channel to the Redis allowed-chats hash
            print(f"📝 Adding channel to Redis allowed_chats...")
            try:
                # Get the proper channel ID (convert if needed)
                # For channels, the ID should be in format -100XXXXXXXXX
                if hasattr(channel, 'id'):
                    # If it's already in the correct format, use it
                    if str(channel.id).startswith('-100'):
                        channel_id = channel.id
                    else:
                        # Convert to the broadcast format
                        channel_id = int(f"-100{channel.id}")
                else:
                    print(f"⚠️  Warning: Channel has no ID attribute")
                    return

                username_part = f"@{channel.username}" if hasattr(channel, 'username') and channel.username else "no username"
                label = f"{channel.title} ({username_part})"
                await allowed_chats.add(chat_id=channel_id, label=label)
                print(f"✅ Channel added to Redis allowed_chats: {channel_id} // {label}")
                print()
            except Exception as e:
                print(f"⚠️  Warning: Could not update Redis allowed_chats: {e}")
                print()
            
            print("=" * 70)
            print(f"🎉 All done! Channel '{channel.title}' joined and muted.")
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise
    finally:
        await redis.aclose()


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python join_channel.py <channel_username>")
        print("\nExample:")
        print("  python join_channel.py @mychannel")
        print("  python join_channel.py mychannel")
        sys.exit(1)
    
    channel_username = sys.argv[1]
    asyncio.run(join_channel_and_mute(channel_username))


if __name__ == "__main__":
    main()

