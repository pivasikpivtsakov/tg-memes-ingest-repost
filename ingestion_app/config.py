from typing import Optional

from shared.config import BaseConfig


class IngestionConfig(BaseConfig):
    """
    Configuration for ingestion_app.
    
    Extends BaseConfig with ingestion-specific settings.
    """
    
    def __init__(self):
        super().__init__()
        
        # Ingestion-specific settings
        self._session_name = self._config_data.get('ingestion_session_name', 'ingestion')
        self._allowed_chat_ids = self._config_data.get('allowed_chat_ids')

    @property
    def session_name(self) -> str:
        """Return absolute path to session file in project root."""
        return str(self.project_root / self._session_name)

    @property
    def allowed_chat_ids(self) -> Optional[list[int]]:
        """
        Get allowed chat/channel IDs from config.
        Works for channels, groups, and private chats.
        Returns None if not set (allows all chats).
        """
        return self._allowed_chat_ids if self._allowed_chat_ids else None


config = IngestionConfig()

