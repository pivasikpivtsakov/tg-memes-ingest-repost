import json5
from pathlib import Path
from typing import Tuple, Dict, Any


class BaseConfig:
    """
    Base configuration shared by all apps.
    
    Contains common settings: Telegram credentials and database configuration.
    Each app should inherit from this and add its specific settings.
    """
    
    def __init__(self):
        # Get project root directory (parent of shared directory)
        self._project_root = Path(__file__).parent.parent.resolve()
        
        # Load config from JSON file
        self._config_data = self._load_config()

        # Telegram credentials (required for all apps)
        self._api_id = self._config_data.get('telegram_api_id')
        self._api_hash = self._config_data.get('telegram_api_hash')

        # PostgreSQL settings (required for all apps)
        self._db_host = self._config_data.get('db_host', 'localhost')
        self._db_port = self._config_data.get('db_port', '5432')
        self._db_name = self._config_data.get('db_name', 'tg_memes')
        self._db_user = self._config_data.get('db_user', 'postgres')
        self._db_password = self._config_data.get('db_password', '')

        # Redis settings (required for all apps)
        self._redis_host = self._config_data.get('redis_host', 'localhost')
        self._redis_port = self._config_data.get('redis_port', 6379)
        self._redis_db = self._config_data.get('redis_db', 0)
        self._redis_password = self._config_data.get('redis_password', None)

        # MinIO settings (required for all apps)
        self._minio_endpoint = self._config_data.get('minio_endpoint', 'localhost:9000')
        self._minio_access_key = self._config_data.get('minio_access_key', 'minioadmin')
        self._minio_secret_key = self._config_data.get('minio_secret_key', 'minioadmin')
        self._minio_bucket = self._config_data.get('minio_bucket', 'tg-memes')
        self._minio_secure = self._config_data.get('minio_secure', False)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        config_path = self._project_root / 'config.json'
        
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                f"Please create a config.json file in the project root."
            )
        
        with open(config_path, 'r') as f:
            return json5.load(f)
    
    # ===== Telegram Settings =====
    
    @property
    def api_id(self) -> int:
        return int(self._api_id)
    
    @property
    def api_hash(self) -> str:
        return self._api_hash
    
    @property
    def credentials(self) -> Tuple[int, str]:
        return (self.api_id, self.api_hash)
    
    # ===== Database Settings =====
    
    @property
    def db_host(self) -> str:
        return self._db_host
    
    @property
    def db_port(self) -> str:
        return self._db_port
    
    @property
    def db_name(self) -> str:
        return self._db_name
    
    @property
    def db_user(self) -> str:
        return self._db_user
    
    @property
    def db_password(self) -> str:
        return self._db_password
    
    @property
    def database_url(self) -> str:
        """Get PostgreSQL connection string using psycopg (version 3) driver."""
        return f"postgresql+psycopg://{self._db_user}:{self._db_password}@{self._db_host}:{self._db_port}/{self._db_name}"
    
    # ===== Redis Settings =====
    
    @property
    def redis_host(self) -> str:
        return self._redis_host
    
    @property
    def redis_port(self) -> int:
        return int(self._redis_port)
    
    @property
    def redis_db(self) -> int:
        return int(self._redis_db)
    
    @property
    def redis_password(self) -> str | None:
        return self._redis_password
    
    @property
    def redis_url(self) -> str:
        """Get Redis connection string (redis://[:password@]host:port/db)."""
        auth = f":{self._redis_password}@" if self._redis_password else ""
        return f"redis://{auth}{self._redis_host}:{self._redis_port}/{self._redis_db}"
    
    # ===== MinIO Settings =====
    
    @property
    def minio_endpoint(self) -> str:
        return self._minio_endpoint
    
    @property
    def minio_access_key(self) -> str:
        return self._minio_access_key
    
    @property
    def minio_secret_key(self) -> str:
        return self._minio_secret_key
    
    @property
    def minio_bucket(self) -> str:
        return self._minio_bucket
    
    @property
    def minio_secure(self) -> bool:
        return bool(self._minio_secure)
    
    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        return self._project_root

