from datetime import timedelta

from shared.config import BaseConfig
from shared.device import DeviceChoice, validate_device


class SearchAppConfig(BaseConfig):
    def __init__(self):
        super().__init__()

        self._search_device = self._config_data.get('search_device', 'auto')
        self._search_host = self._config_data.get('search_host', '127.0.0.1')
        self._search_port = self._config_data.get('search_port', 8080)
        self._search_jwt_expiration_hours = self._config_data.get('search_jwt_expiration_hours', 168)

    @property
    def search_device(self) -> DeviceChoice:
        """'auto' (CUDA when PyTorch can see a GPU), 'cuda' or 'cpu'."""
        return validate_device(str(self._search_device), name='search_device')

    @property
    def search_host(self) -> str:
        return str(self._search_host)

    @property
    def search_port(self) -> int:
        return int(self._search_port)

    @property
    def search_bot_token(self) -> str:
        return str(self._required('search_bot_token'))

    @property
    def search_jwt_secret(self) -> str:
        return str(self._required('search_jwt_secret'))

    @property
    def search_jwt_expiration(self) -> timedelta:
        return timedelta(hours=float(self._search_jwt_expiration_hours))

    @property
    def minio_public_base_url(self) -> str:
        """Public base of the bucket; a meme is served from {base}/{file_path}."""
        return str(self._required('minio_public_base_url')).rstrip('/')


config = SearchAppConfig()
