"""
S3TenantStorage: Tenant's own S3 bucket using cross-account credentials.

Credentials are read from tenant_credentials via CredentialService.

Requirements: 6.5
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
import uuid
import os
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from storage.storage_provider import StorageProvider

logger = logging.getLogger(__name__)


class S3TenantStorage(StorageProvider):
    """Tenant's own S3 bucket using cross-account credentials."""

    def __init__(self, tenant: str, parameter_service=None):
        self.tenant = tenant
        self.parameter_service = parameter_service
        bucket = None
        if parameter_service:
            bucket = parameter_service.get_param(
                'storage', 's3_tenant_bucket', tenant=tenant
            )
        self.bucket = bucket or ''
        if not self.bucket:
            raise ValueError(f"S3 tenant bucket not configured for {tenant}")
        self._client = self._create_client(tenant, parameter_service)

    @staticmethod
    def _create_client(tenant, parameter_service):
        """Create S3 client with tenant's cross-account credentials."""
        if not parameter_service or not parameter_service.credential_service:
            raise RuntimeError(
                f"CredentialService required for S3 tenant storage ({tenant})"
            )
        cs = parameter_service.credential_service
        creds = cs.get_credential(tenant, 's3_credentials')
        if not creds or not isinstance(creds, dict):
            raise ValueError(
                f"S3 credentials not found for tenant {tenant}. "
                "Store them via tenant_credentials with type 's3_credentials'."
            )
        return boto3.client(
            's3',
            aws_access_key_id=creds.get('aws_access_key_id'),
            aws_secret_access_key=creds.get('aws_secret_access_key'),
            region_name=creds.get('region', 'eu-west-1'),
        )

    def upload(self, file_data: bytes, path: str, metadata: dict = None) -> str:
        """Upload file to tenant's S3 bucket. Returns the S3 key."""
        metadata = metadata or {}
        ref = metadata.get('reference_number', 'general')
        filename = os.path.basename(path)
        unique = uuid.uuid4().hex[:12]
        key = f"{ref}/{unique}_{filename}"
        content_type = metadata.get('mime_type', 'application/octet-stream')
        self._client.put_object(
            Bucket=self.bucket, Key=key, Body=file_data,
            ContentType=content_type
        )
        return key

    def download(self, reference: str) -> bytes:
        """Download file from tenant's S3 bucket by key."""
        response = self._client.get_object(Bucket=self.bucket, Key=reference)
        return response['Body'].read()

    def delete(self, reference: str) -> bool:
        """Delete file from tenant's S3 bucket by key."""
        try:
            self._client.delete_object(Bucket=self.bucket, Key=reference)
            return True
        except ClientError as e:
            logger.error("Failed to delete s3://%s/%s: %s", self.bucket, reference, e)
            return False

    def list_files(self, path: str) -> List[dict]:
        """List files under a prefix in tenant's bucket."""
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
