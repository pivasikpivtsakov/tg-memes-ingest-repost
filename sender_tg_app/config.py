from shared.sender_base import BaseSenderConfig


class TelegramSenderConfig(BaseSenderConfig):
    def __init__(self):
        super().__init__()
        
        # Sender-specific settings
        self._session_name = self._config_data.get('sender_session_name', 'sender')
        self._include_caption = self._config_data.get('include_caption', True)
    
    @property
    def session_name(self) -> str:
        """Return absolute path to session file in project root."""
        return str(self.project_root / self._session_name)

    @property
    def include_caption(self) -> bool:
        """Whether to include original caption when sending memes (default: True)."""
        return bool(self._include_caption)


config = TelegramSenderConfig()
