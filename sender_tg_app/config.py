from shared.sender_base import BaseSenderConfig


class TelegramSenderConfig(BaseSenderConfig):
    def __init__(self):
        super().__init__()
        
        # Sender-specific settings
        self._session_name = self._config_data.get('sender_session_name', 'sender')
        self._target_chat_id = self._config_data.get('target_chat_id')
        self._memes_per_run = self._config_data.get('memes_per_run', 1)
        self._include_caption = self._config_data.get('include_caption', True)
    
    @property
    def session_name(self) -> str:
        """Return absolute path to session file in project root."""
        return str(self.project_root / self._session_name)

    @property
    def target_chat_id(self) -> str:
        """
        Target chat/channel ID or username where memes will be sent.
        Can be a username (e.g., '@mychannel') or numeric ID (e.g., '-1001234567890').
        """
        return self._target_chat_id
    
    @property
    def memes_per_run(self) -> int:
        """Number of memes to send per execution (default: 1)."""
        return int(self._memes_per_run)
    
    @property
    def include_caption(self) -> bool:
        """Whether to include original caption when sending memes (default: True)."""
        return bool(self._include_caption)


config = TelegramSenderConfig()
