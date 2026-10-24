from shared.config import BaseConfig


class BaseIndexerConfig(BaseConfig):
    """Polling settings of an indexing daemon; config.json keys are prefixed per app."""

    key_prefix: str
    default_batch_size: int

    def __init__(self):
        super().__init__()

        self._poll_interval = self._config_data.get(f'{self.key_prefix}_poll_interval', 5)
        self._batch_size = self._config_data.get(f'{self.key_prefix}_batch_size', self.default_batch_size)

    @property
    def poll_interval(self) -> float:
        """Seconds to wait before polling again when nothing is left to index."""
        return float(self._poll_interval)

    @property
    def batch_size(self) -> int:
        """Medias fetched and processed per iteration."""
        return int(self._batch_size)
