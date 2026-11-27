import os
from pathlib import Path


class StorageConfigurationError(RuntimeError):
    pass


class StorageError(RuntimeError):
    pass


def _content_type(filename):
    return {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    }.get(Path(filename).suffix.lower(), "application/octet-stream")


def _save_to_s3(upload, filename, bucket):
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if bool(access_key) != bool(secret_key):
        raise StorageConfigurationError(
            "Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
        )
    if os.getenv("VERCEL") == "1" and (not access_key or not secret_key):
        raise StorageConfigurationError(
            "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for Vercel uploads."
        )

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as error:
        raise StorageConfigurationError(
            "S3 uploads require the boto3 package."
        ) from error

    client_options = {}
    region = os.getenv("S3_REGION")
    endpoint_url = os.getenv("S3_ENDPOINT_URL")
    if region:
        client_options["region_name"] = region
    if endpoint_url:
        client_options["endpoint_url"] = endpoint_url
    if access_key:
        client_options["aws_access_key_id"] = access_key
        client_options["aws_secret_access_key"] = secret_key

    try:
        client = boto3.client("s3", **client_options)
        client.upload_fileobj(
            upload.stream,
            bucket,
            f"resumes/{filename}",
            ExtraArgs={"ContentType": _content_type(filename)},
        )
    except (BotoCoreError, ClientError) as error:
        raise StorageError(
            "The configured object storage rejected the upload."
        ) from error


def save_upload(upload, filename, local_directory):
    if Path(filename).name != filename:
        raise StorageError("Invalid upload filename.")

    bucket = os.getenv("S3_BUCKET")
    if bucket:
        _save_to_s3(upload, filename, bucket)
        return

    if os.getenv("VERCEL") == "1":
        raise StorageConfigurationError(
            "Set S3_BUCKET and S3 credentials to enable durable Vercel uploads."
        )

    destination = Path(local_directory) / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    upload.save(destination)
