"""
GoogleDriveStorage: Wraps existing GoogleDriveService behind StorageProvider.

Default provider for current tenants.

Requirements: 6.3, 10.4
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging

from storage.storage_provider import StorageProvider

logger = logging.getLogger(__name__)


class GoogleDriveStorage(StorageProvider):
    """Wraps existing GoogleDriveService behind the StorageProvider interface."""

    def __init__(self, tenant: str, parameter_service=None):
        self.tenant = tenant
        self.parameter_service = parameter_service
        self._service = None

    def _get_service(self):
        """Lazy-init the GoogleDriveService."""
        if self._service is None:
            from google_drive_service import GoogleDriveService

            self._service = GoogleDriveService(
                self.tenant, parameter_service=self.parameter_service
            )
        return self._service

    def _upload_raw(self, file_data: bytes, key: str, content_type: str) -> bool:
        """Raw upload for Google Drive. Not applicable — raises NotImplementedError.

        Google Drive doesn't use key-based addressing. Use MediaAssetService
        with an S3-based provider instead.
        """
        raise NotImplementedError(
            "GoogleDriveStorage does not support _upload_raw. "
            "Use MediaAssetService with S3 providers for managed assets."
        )

    def _delete_raw(self, key: str) -> bool:
        """Raw delete for Google Drive (uses key as file ID)."""
        try:
            svc = self._get_service()
            svc.service.files().delete(fileId=key).execute()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to delete Google Drive file %s: %s", key, e)
            return False

    def download(self, reference: str) -> bytes:
        """Download file from Google Drive by file ID."""
        svc = self._get_service()
        return svc.download_file_content(reference)

    def list_files(self, path: str) -> list[dict]:
        """List files in a Google Drive folder (path = folder ID)."""
        try:
            svc = self._get_service()
            results = (
                svc.service.files()
                .list(
                    q=f"'{path}' in parents and trashed=false",
                    fields="files(id, name, mimeType, size, modifiedTime)",
                )
                .execute()
            )
            return [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "mime_type": f.get("mimeType"),
                    "size": f.get("size"),
                    "modified": f.get("modifiedTime"),
                }
                for f in results.get("files", [])
            ]
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to list Google Drive folder %s: %s", path, e)
            return []
