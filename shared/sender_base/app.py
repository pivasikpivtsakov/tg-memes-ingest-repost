import asyncio
import logging
from abc import ABC, abstractmethod

from shared.logger import setup_logging
from shared.sender_base.config import BaseSenderConfig
from shared.services.media import MediaService

logger = logging.getLogger(__name__)


class AbstractSenderApp(ABC):
    def __init__(self, config: BaseSenderConfig):
        self.config = config
        self.media_service = self._create_media_service()

    def _create_media_service(self) -> MediaService:
        media_service = MediaService(
            self.config.database_url,
            self.config.minio_endpoint,
            self.config.minio_access_key,
            self.config.minio_secret_key,
            self.config.minio_bucket,
            self.config.minio_secure
        )
        logger.info("Media service initialized with MinIO")
        return media_service

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
        finally:
            await self.media_service.dispose()

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

