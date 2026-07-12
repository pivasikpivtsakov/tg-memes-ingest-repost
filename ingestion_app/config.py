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

    @property
    def session_name(self) -> str:
        """Return absolute path to session file in project root."""
        return str(self.project_root / self._session_name)


config = IngestionConfig()
