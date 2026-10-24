import logging
from collections.abc import Collection

from botocore.exceptions import ClientError

from shared.db.repositories.media import MediaMetadata
from shared.db.repositories.media_index import IndexOrder, MediaIndexRepository
from shared.db.session import AsyncDatabaseManager
from shared.s3.client import create_s3_client
from shared.s3.repositories import ObjectRepository

logger = logging.getLogger(__name__)

_MISSING_OBJECT_CODES = frozenset({"NoSuchKey", "404"})


class MediaIndexService[RowT]:
    """Finds medias missing from one index table, fetches their files and stores results."""

    def __init__(
        self,
        *,
        repository_cls: type[MediaIndexRepository[RowT]],
        database_url: str,
        minio_endpoint: str,
        minio_access_key: str,
        minio_secret_key: str,
        minio_bucket: str,
        minio_secure: bool = False,
    ):
        self._db = AsyncDatabaseManager(database_url)
        self._index = repository_cls(self._db)
        self._objects = ObjectRepository(
            client=create_s3_client(
                endpoint=minio_endpoint,
                access_key=minio_access_key,
                secret_key=minio_secret_key,
                secure=minio_secure,
            ),
            bucket=minio_bucket,
        )

    async def dispose(self) -> None:
        await self._db.dispose()

    async def list_missing(
        self,
        *,
        limit: int,
        order: IndexOrder,
        exclude_ids: Collection[int] = (),
    ) -> list[MediaMetadata]:
        return await self._index.list_missing(limit=limit, order=order, exclude_ids=exclude_ids)

    async def count_missing(self) -> int:
        return await self._index.count_missing()

    async def get_max_media_id(self) -> int | None:
        return await self._index.get_max_media_id()

    def get_media_data(self, file_path: str) -> bytes | None:
        """File bytes, or None if the object is gone from MinIO. Other S3 errors propagate."""
        try:
            return self._objects.get(file_path)
        except ClientError as e:
            if e.response["Error"]["Code"] in _MISSING_OBJECT_CODES:
                return None
            raise

    async def save(self, rows: list[RowT]) -> int:
        return await self._index.insert_many(rows)
