from shared.s3.repositories.base import S3Repository


class ObjectRepository(S3Repository):
    def get(self, key: str) -> bytes:
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
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
