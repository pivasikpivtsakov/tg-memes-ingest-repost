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
import re
import sys
from pathlib import Path
from telethon import TelegramClient, functions, types


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
            
            # Step 4: Add channel to config.json
            print(f"📝 Adding channel to config.json...")
            try:
                # Read the current config file
                with open(config_path, 'r') as f:
                    config_content = f.read()
                
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
                
                if str(channel_id) in config_content:
                    print(f"ℹ️  Channel already exists in config.json")
                else:
                    # Prepare the comment with channel name and username
                    username_part = f"@{channel.username}" if hasattr(channel, 'username') and channel.username else "no username"
                    comment = f"  {channel_id},  // {channel.title} ({username_part})"
                    
                    # Find the allowed_chat_ids section and add the new entry
                    # Find the last entry in allowed_chat_ids array
                    pattern = r'("allowed_chat_ids":\s*\[)(.*?)(\s*\],)'
                    match = re.search(pattern, config_content, re.DOTALL)
                    
                    if match:
                        # Get the existing entries
                        before = match.group(1)
                        entries = match.group(2)
                        after = match.group(3)
                        
                        # Add the new entry at the end
                        new_entries = entries.rstrip() + '\n' + comment + '\n  '
                        new_config_content = config_content[:match.start()] + before + new_entries + after + config_content[match.end():]
                        
                        # Write back to file
                        with open(config_path, 'w') as f:
                            f.write(new_config_content)
                        
                        print(f"✅ Channel added to config.json")
                    else:
                        print(f"⚠️  Warning: Could not find allowed_chat_ids in config.json")
                
                print()
            except Exception as e:
                print(f"⚠️  Warning: Could not update config.json: {e}")
                print()
            
            print("=" * 70)
            print(f"🎉 All done! Channel '{channel.title}' joined and muted.")
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise


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

