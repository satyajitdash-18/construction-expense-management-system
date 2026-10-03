"""MinIO object storage service for evidence files."""

import hashlib
import io
import mimetypes
from collections.abc import Mapping
from datetime import timedelta
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class StorageService:
    """Service for managing object storage with MinIO."""

    def __init__(self, client: Minio | None = None) -> None:
        self.bucket_name = settings.MINIO_BUCKET
        if client is not None:
            self.client = client
        else:
            self.client = Minio(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
            self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info("Created bucket", bucket=self.bucket_name)
        except S3Error as e:
            logger.error("Failed to create bucket", bucket=self.bucket_name, error=str(e))
            raise

    def _compute_checksum(self, data: bytes) -> str:
        """Compute SHA-256 checksum of data."""
        return hashlib.sha256(data).hexdigest()

    def upload_file(
        self,
        object_name: str,
        data: bytes,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> tuple[str, str]:
        """
        Upload a file to MinIO.

        Args:
            object_name: Object key in bucket
            data: File content as bytes
            content_type: MIME type (auto-detected if None)
            metadata: Additional metadata

        Returns:
            Tuple of (object_name, checksum)
        """
        if content_type is None:
            content_type, _ = mimetypes.guess_type(object_name)
            if content_type is None:
                content_type = "application/octet-stream"

        checksum = self._compute_checksum(data)

        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type,
                metadata=dict(metadata) if metadata else None,
            )
            logger.info("Uploaded file", object_name=object_name, size=len(data), checksum=checksum)
            return object_name, checksum
        except S3Error as e:
            logger.error("Failed to upload file", object_name=object_name, error=str(e))
            raise

    def upload_stream(
        self,
        object_name: str,
        stream: BinaryIO,
        length: int,
        checksum: str,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> tuple[str, str]:
        """
        Stream a file-like object directly to MinIO without reading full content into memory.
        """
        if content_type is None:
            content_type, _ = mimetypes.guess_type(object_name)
            if content_type is None:
                content_type = "application/octet-stream"

        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=stream,
                length=length,
                content_type=content_type,
                metadata=dict(metadata) if metadata else None,
            )
            logger.info("Streamed file upload to MinIO", object_name=object_name, size=length, checksum=checksum)
            return object_name, checksum
        except S3Error as e:
            logger.error("Failed to stream file to MinIO", object_name=object_name, error=str(e))
            raise

    def upload_fileobj(
        self,
        object_name: str,
        fileobj: BinaryIO,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> tuple[str, str]:
        """
        Upload a file-like object to MinIO with stream length calculation.
        """
        fileobj.seek(0, io.SEEK_END)
        length = fileobj.tell()
        fileobj.seek(0)
        
        hasher = hashlib.sha256()
        while chunk := fileobj.read(64 * 1024):
            hasher.update(chunk)
        checksum = hasher.hexdigest()
        fileobj.seek(0)

        return self.upload_stream(
            object_name=object_name,
            stream=fileobj,
            length=length,
            checksum=checksum,
            content_type=content_type,
            metadata=metadata,
        )

    def download_file(self, object_name: str) -> bytes:
        """Download a file from MinIO."""
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            logger.info("Downloaded file", object_name=object_name, size=len(data))
            return data
        except S3Error as e:
            logger.error("Failed to download file", object_name=object_name, error=str(e))
            raise

    def delete_file(self, object_name: str) -> None:
        """Delete a file from MinIO."""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info("Deleted file", object_name=object_name)
        except S3Error as e:
            logger.error("Failed to delete file", object_name=object_name, error=str(e))
            raise

    def generate_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
        method: str = "GET",
    ) -> str:
        """
        Generate a presigned URL for an object.

        Args:
            object_name: Object key in bucket
            expires: Expiration time
            method: HTTP method (GET, PUT, etc.)

        Returns:
            Presigned URL
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=expires,
            )
            logger.info("Generated presigned URL", object_name=object_name, expires=str(expires))
            return url
        except S3Error as e:
            logger.error("Failed to generate presigned URL", object_name=object_name, error=str(e))
            raise

    def generate_presigned_put_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Generate a presigned PUT URL for direct upload."""
        try:
            url = self.client.presigned_put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=expires,
            )
            logger.info("Generated presigned PUT URL", object_name=object_name)
            return url
        except S3Error as e:
            logger.error("Failed to generate presigned PUT URL", object_name=object_name, error=str(e))
            raise

    def file_exists(self, object_name: str) -> bool:
        """Check if a file exists in MinIO."""
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False

    def get_file_info(self, object_name: str) -> dict | None:
        """Get file metadata and info."""
        try:
            stat = self.client.stat_object(self.bucket_name, object_name)
            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "etag": stat.etag,
                "last_modified": stat.last_modified,
                "metadata": stat.metadata,
            }
        except S3Error:
            return None


def create_storage_service() -> StorageService:
    """Factory for creating StorageService."""
    return StorageService()
