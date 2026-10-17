from botocore.exceptions import ClientError


class S3Repository:
    def __init__(self, *, client, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    @staticmethod
    def _error_code(exc: ClientError) -> str:
        return exc.response["Error"]["Code"]

    def ensure_bucket(self) -> bool:
        try:
            self._s3.head_bucket(Bucket=self._bucket)
            return False
        except ClientError as e:
            if self._error_code(e) != "404":
                raise
            self._s3.create_bucket(Bucket=self._bucket)
            return True
