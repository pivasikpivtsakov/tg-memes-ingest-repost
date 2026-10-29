import argparse
import asyncio
import logging
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from shared.db.repositories.media import MediaMetadata
from shared.db.repositories.media_index import IndexOrder, MediaIndexRepository
from shared.device import DeviceChoice, add_device_argument
from shared.indexer_base.config import BaseIndexerConfig
from shared.logger import setup_logging
from shared.services.media_index import MediaIndexService

logger = logging.getLogger(__name__)

# Stays below the default boto3 connection pool size of 10.
_DOWNLOAD_CONCURRENCY = 8
_LOG_MISSING_EVERY_BATCHES = 50


@dataclass(frozen=True)
class IndexerArgs:
    once: bool
    order: IndexOrder


@dataclass(frozen=True)
class DownloadedMedia:
    media: MediaMetadata
    data: bytes


@dataclass(frozen=True)
class IndexBatchResult[RowT]:
    rows: list[RowT]
    failed_ids: list[int]


class AbstractIndexerApp[RowT, ConfigT: BaseIndexerConfig](ABC):
    """Indexes medias that have no row in the app's table yet; the database is the only queue."""

    repository_cls: type[MediaIndexRepository[RowT]]
    config: ConfigT

    def __init__(self, config: ConfigT):
        self.config = config
        self.index_service = self._create_index_service()
        # Undecodable or missing files; retried after a restart.
        self._failed_ids: set[int] = set()
        self._idle_max_media_id: int | None = None
        self._batches_done = 0

    def _create_index_service(self) -> MediaIndexService[RowT]:
        index_service = MediaIndexService(
            repository_cls=self.repository_cls,
            database_url=self.config.database_url,
            minio_endpoint=self.config.minio_endpoint,
            minio_access_key=self.config.minio_access_key,
            minio_secret_key=self.config.minio_secret_key,
            minio_bucket=self.config.minio_bucket,
            minio_secure=self.config.minio_secure,
        )
        logger.info("Index service initialized with MinIO")
        return index_service

    @abstractmethod
    def _load_model(self) -> None:
        """Runs in a worker thread at startup; the model stays loaded until exit."""

    @abstractmethod
    def _index_batch(self, items: list[DownloadedMedia]) -> IndexBatchResult[RowT]:
        """Runs in a worker thread. Medias that cannot be decoded go to failed_ids."""

    @abstractmethod
    def _log_startup_info(self) -> None:
        pass

    async def _run_indexer(self, args: IndexerArgs) -> int:
        logger.info("Loading model...")
        await asyncio.to_thread(self._load_model)
        logger.info(f"{await self.index_service.count_missing()} medias are waiting to be indexed")

        while True:
            try:
                found = await self._index_next_batch(args.order)
            except Exception as e:
                logger.error(
                    f"Indexing batch failed, retrying in {self.config.poll_interval:.0f}s: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(self.config.poll_interval)
                continue

            if found:
                continue
            if args.once:
                self._log_failed()
                logger.info("Nothing left to index. Exiting.")
                return 0
            await asyncio.sleep(self.config.poll_interval)

    async def _index_next_batch(self, order: IndexOrder) -> bool:
        # The anti-join scans the whole table, so skip it while no new media arrived.
        max_media_id = await self.index_service.get_max_media_id()
        if max_media_id == self._idle_max_media_id:
            return False

        medias = await self.index_service.list_missing(
            limit=self.config.batch_size,
            order=order,
            exclude_ids=self._failed_ids,
        )
        if not medias:
            self._idle_max_media_id = max_media_id
            return False

        started = time.perf_counter()
        items = await self._download(medias)
        result = await asyncio.to_thread(self._index_batch, items)
        saved = await self.index_service.save(result.rows)
        self._failed_ids.update(result.failed_ids)

        logger.info(
            f"Indexed {saved}/{len(medias)} medias #{medias[0].id}..#{medias[-1].id} "
            f"in {time.perf_counter() - started:.1f}s"
        )
        self._batches_done += 1
        if self._batches_done % _LOG_MISSING_EVERY_BATCHES == 0:
            logger.info(f"{await self.index_service.count_missing()} medias left to index")
        return True

    async def _download(self, medias: list[MediaMetadata]) -> list[DownloadedMedia]:
        semaphore = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)

        async def fetch(media: MediaMetadata) -> bytes | None:
            async with semaphore:
                return await asyncio.to_thread(self.index_service.get_media_data, media.file_path)

        datas = await asyncio.gather(*(fetch(media) for media in medias))
        items = []
        for media, data in zip(medias, datas, strict=True):
            if data is None:
                logger.warning(
                    f"{media.media_type.capitalize()} #{media.id} is missing from MinIO "
                    f"(key: {media.file_path}), skipping"
                )
                self._failed_ids.add(media.id)
                continue
            items.append(DownloadedMedia(media=media, data=data))
        return items

    def _log_failed(self) -> None:
        if not self._failed_ids:
            return
        failed = sorted(self._failed_ids)
        preview = ", ".join(f"#{media_id}" for media_id in failed[:20])
        more = f" and {len(failed) - 20} more" if len(failed) > 20 else ""
        logger.warning(f"{len(failed)} medias could not be indexed: {preview}{more}")

    async def main(self, args: IndexerArgs) -> int:
        try:
            return await self._run_indexer(args)
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            return 1
        finally:
            await self.index_service.dispose()

    def _extend_parser(self, parser: argparse.ArgumentParser) -> None:
        pass

    def _apply_device(self, device: DeviceChoice) -> None:
        raise RuntimeError(f"{type(self).__name__} does not accept --device")

    def _apply_args(self, args: argparse.Namespace) -> None:
        pass

    def _parse_args(self) -> IndexerArgs:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--once",
            action="store_true",
            help="index everything that is missing, then exit instead of polling",
        )
        parser.add_argument(
            "--order",
            type=IndexOrder,
            choices=list(IndexOrder),
            default=IndexOrder.DESC,
            help="desc: newest medias first (daemon); asc: oldest first (archive backfill)",
        )
        add_device_argument(parser)
        self._extend_parser(parser)
        args = parser.parse_args()
        if args.device is not None:
            self._apply_device(args.device)
        self._apply_args(args)
        return IndexerArgs(once=args.once, order=args.order)

    def run(self) -> None:
        args = self._parse_args()
        setup_logging()

        try:
            logger.info("=" * 60)
            self._log_startup_info()
            logger.info(f"Mode: {'once' if args.once else 'daemon'}, order: {args.order}")
            logger.info("=" * 60)

            exit_code = asyncio.run(self.main(args))
            sys.exit(exit_code)
        except KeyboardInterrupt:
            logger.info("Application stopped by user")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
            sys.exit(1)
