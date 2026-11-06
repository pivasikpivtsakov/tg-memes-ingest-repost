from botocore.exceptions import ClientError

from shared.s3.repositories.base import S3Repository

_MISSING_OBJECT_CODES = frozenset({"NoSuchKey", "404"})


class ObjectRepository(S3Repository):
    @classmethod
    def is_missing(cls, exc: ClientError) -> bool:
        return cls._error_code(exc) in _MISSING_OBJECT_CODES

    def get(self, key: str) -> bytes:
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def get_head(self, key: str, *, size: int) -> bytes:
        response = self._s3.get_object(Bucket=self._bucket, Key=key, Range=f"bytes=0-{size - 1}")
        return response["Body"].read()

    def put(self, key: str, *, body: bytes, content_type: str) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    @staticmethod
    def key_for(file_hash: str, extension: str) -> str:
        return f"{file_hash}.{extension}"
