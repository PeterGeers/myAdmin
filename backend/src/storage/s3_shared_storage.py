"""
S3SharedStorage: Shared S3 bucket with tenant-prefixed keys.

Key format: {tenant}/{category}/{reference}/{uuid}_{filename}

Categories:
- invoices: uploaded invoice/document PDFs (default)
- branding: logos and letterheads
- templates: invoice and report templates

Requirements: 6.4, 10.1–10.6
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
import uuid
import os
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

from storage.storage_provider import StorageProvider

logger = logging.getLogger(__name__)


class S3SharedStorage(StorageProvider):
    """Shared S3 bucket with tenant-prefixed keys."""

    def __init__(self, tenant: str, parameter_service=None):
        self.tenant = tenant
        self.parameter_service = parameter_service
        bucket = None
        if parameter_service:
            bucket = parameter_service.get_param(
                'storage', 's3_shared_bucket', tenant=tenant
            )
        self.bucket = bucket or os.getenv('S3_SHARED_BUCKET', '')
        if not self.bucket:
            raise ValueError("S3 shared bucket not configured")
        self._client = boto3.client('s3')

    def _make_key(self, path: str, metadata: dict = None, category: str = 'invoices') -> str:
        """Build S3 key: {tenant}/{category}/{reference}/{uuid}_{filename}"""
        metadata = metadata or {}
        ref = metadata.get('reference_number', 'general')
        filename = os.path.basename(path)
        unique = uuid.uuid4().hex[:12]
        return f"{self.tenant}/{category}/{ref}/{unique}_{filename}"

    def upload(self, file_data: bytes, path: str, metadata: dict = None, category: str = 'invoices') -> str:
        """Upload file to shared S3 bucket. Returns the S3 key as reference."""
        key = self._make_key(path, metadata, category=category)
        content_type = (metadata or {}).get('mime_type', 'application/octet-stream')
        self._client.put_object(
            Bucket=self.bucket, Key=key, Body=file_data,
            ContentType=content_type
        )
        logger.info("Uploaded to s3://%s/%s", self.bucket, key)
        return key

    def download(self, reference: str) -> bytes:
        """Download file from S3 by key."""
        response = self._client.get_object(Bucket=self.bucket, Key=reference)
        return response['Body'].read()

    def delete(self, reference: str) -> bool:
        """Delete file from S3 by key."""
        try:
            self._client.delete_object(Bucket=self.bucket, Key=reference)
            return True
        except ClientError as e:
            logger.error("Failed to delete s3://%s/%s: %s", self.bucket, reference, e)
            return False

    def list_files(self, path: str, category: Optional[str] = None) -> List[dict]:
        """List files under a prefix.

        If category is provided, scopes the prefix to {tenant}/{category}/.
        Otherwise uses the provided path as prefix.
        """
        if category:
            prefix = f"{self.tenant}/{category}/"
        else:
            prefix = path if path.endswith('/') else path + '/'
        try:
            response = self._client.list_objects_v2(
                Bucket=self.bucket, Prefix=prefix
            )
            return [
                {
                    'key': obj['Key'],
                    'name': os.path.basename(obj['Key']),
                    'size': obj.get('Size'),
                    'modified': obj.get('LastModified'),
                }
                for obj in response.get('Contents', [])
            ]
        except ClientError as e:
            logger.error("Failed to list s3://%s/%s: %s", self.bucket, prefix, e)
            return []
