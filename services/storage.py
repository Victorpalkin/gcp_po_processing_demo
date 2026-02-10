"""Google Cloud Storage service for PO file uploads."""

import os
import uuid
from datetime import datetime, timedelta

from google.cloud import storage


def _get_client() -> storage.Client:
    return storage.Client(project=os.environ["PROJECT_ID"])


def _get_bucket() -> storage.Bucket:
    client = _get_client()
    return client.bucket(os.environ["GCS_BUCKET"])


def upload_file(file_bytes: bytes, filename: str, mime_type: str) -> str:
    """Upload a file to GCS.

    Returns the GCS URI (gs://bucket/path).
    """
    bucket = _get_bucket()
    date_prefix = datetime.utcnow().strftime("%Y/%m/%d")
    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    blob_path = f"uploads/{date_prefix}/{unique_name}"

    blob = bucket.blob(blob_path)
    blob.upload_from_string(file_bytes, content_type=mime_type)

    return f"gs://{bucket.name}/{blob_path}"


def get_signed_url(gcs_uri: str, expiration_minutes: int = 60) -> str:
    """Generate a temporary signed URL for viewing a file."""
    bucket_name, blob_path = _parse_gcs_uri(gcs_uri)
    client = _get_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiration_minutes),
        method="GET",
    )
    return url


def download_file(gcs_uri: str) -> bytes:
    """Download file bytes from GCS."""
    bucket_name, blob_path = _parse_gcs_uri(gcs_uri)
    client = _get_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.download_as_bytes()


def delete_file(gcs_uri: str) -> None:
    """Delete a file from GCS."""
    bucket_name, blob_path = _parse_gcs_uri(gcs_uri)
    client = _get_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.delete()


def _parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """Parse gs://bucket/path into (bucket, path)."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    parts = gcs_uri[5:].split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    return parts[0], parts[1]
