from typing import Any


def get_sender_name(sender: Any) -> str:
    """Extract a display name from a Telegram sender entity."""
    if getattr(sender, 'first_name', None) and getattr(sender, 'last_name', None):
        first_last_name = getattr(sender, 'first_name', '') + " " + getattr(sender, 'last_name', '')
        return first_last_name
    elif getattr(sender, 'title', None):
        return getattr(sender, 'title', 'Unknown')
    else:
        return 'Unknown'

