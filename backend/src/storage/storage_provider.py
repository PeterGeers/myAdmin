"""
StorageProvider: Abstract interface and factory for multi-backend file storage.

Supports Google Drive, S3 shared bucket, and S3 tenant bucket providers.
The factory resolves the provider from ParameterService (storage.invoice_provider).

Requirements: 6.1, 6.2
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class StorageProvider(ABC):
    """Abstract base class for file storage backends."""

    @abstractmethod
    def upload(self, file_data: bytes, path: str, metadata: dict = None) -> str:
        """Upload file, return reference string."""

    @abstractmethod
    def download(self, reference: str) -> bytes:
        """Download file by reference, return bytes."""

    @abstractmethod
    def delete(self, reference: str) -> bool:
        """Delete file by reference, return success."""

    @abstractmethod
    def list_files(self, path: str) -> List[dict]:
        """List files at path, return list of metadata dicts."""


VALID_PROVIDERS = ('google_drive', 's3_shared', 's3_tenant')


def get_storage_provider(tenant: str, parameter_service) -> StorageProvider:
    """
    Factory: resolves tenant's configured storage provider from
    ParameterService (namespace=storage, key=invoice_provider).
    Defaults to s3_shared if no provider is configured.
    """
    provider_type = parameter_service.get_param(
        'storage', 'invoice_provider', tenant=tenant
    )
    if not provider_type:
        provider_type = 's3_shared'

    if provider_type == 'google_drive':
        from storage.google_drive_storage import GoogleDriveStorage
        return GoogleDriveStorage(tenant, parameter_service)

    elif provider_type == 's3_shared':
        from storage.s3_shared_storage import S3SharedStorage
        return S3SharedStorage(tenant, parameter_service)

    elif provider_type == 's3_tenant':
        from storage.s3_tenant_storage import S3TenantStorage
        return S3TenantStorage(tenant, parameter_service)

    else:
        raise ValueError(
            f"Unknown storage provider: {provider_type}. "
            f"Valid options: {', '.join(VALID_PROVIDERS)}"
        )
