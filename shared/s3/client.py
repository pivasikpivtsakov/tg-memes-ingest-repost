import boto3


def create_s3_client(
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool = False,
):
    scheme = "https" if secure else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{endpoint}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )
