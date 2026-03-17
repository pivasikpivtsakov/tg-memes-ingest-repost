import asyncio
import logging
from abc import ABC, abstractmethod

from shared.logger import setup_logging
from shared.sender_base.config import BaseSenderConfig
from shared.storage import MediaStorage

logger = logging.getLogger(__name__)


class AbstractSenderApp(ABC):
    def __init__(self, config: BaseSenderConfig):
        self.config = config
        self.storage = self._create_storage()
    
    def _create_storage(self) -> MediaStorage:
        storage = MediaStorage(
            self.config.database_url,
            self.config.minio_endpoint,
            self.config.minio_access_key,
            self.config.minio_secret_key,
            self.config.minio_bucket,
            self.config.minio_secure
        )
        logger.info("Media storage initialized with MinIO")
        return storage

    @abstractmethod
    async def _run_sender(self) -> int:
        pass

    @abstractmethod
    def _log_startup_info(self) -> None:
        pass

    async def main(self) -> int:
        try:
            return await self._run_sender()
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            return 1

    def run(self) -> None:
        setup_logging()
        
        logger.info("=" * 60)
        self._log_startup_info()
        logger.info("=" * 60)
        
        try:
            exit_code = asyncio.run(self.main())
            exit(exit_code)
        except KeyboardInterrupt:
            logger.info("Application stopped by user")
            exit(0)
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
            exit(1)

