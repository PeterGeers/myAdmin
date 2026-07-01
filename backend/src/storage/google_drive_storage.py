"""
GoogleDriveStorage: Wraps existing GoogleDriveService behind StorageProvider.

Default provider for current tenants.

Requirements: 6.3, 10.4
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
from typing import List

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

    def upload(self, file_data: bytes, path: str, metadata: dict = None) -> str:
        """Upload file to Google Drive. Returns the file ID as reference."""
        import tempfile
        import os
        metadata = metadata or {}
        folder_id = metadata.get('folder_id', '')
        filename = metadata.get('filename') or os.path.basename(path)
        mime_type = metadata.get('mime_type', 'application/octet-stream')

        svc = self._get_service()

        if isinstance(file_data, bytes) and mime_type.startswith('text/'):
            result = svc.upload_text_file(
                file_data.decode('utf-8'), filename, folder_id, mime_type
            )
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name
            try:
                result = svc.upload_file(tmp_path, filename, folder_id)
            finally:
                os.unlink(tmp_path)

        return result.get('id', '')

    def download(self, reference: str) -> bytes:
        """Download file from Google Drive by file ID."""
        svc = self._get_service()
        return svc.download_file_content(reference)

    def delete(self, reference: str) -> bool:
        """Delete file from Google Drive by file ID."""
        try:
            svc = self._get_service()
            svc.service.files().delete(fileId=reference).execute()
            return True
        except Exception as e:
            logger.error("Failed to delete Google Drive file %s: %s", reference, e)
            return False

    def list_files(self, path: str) -> List[dict]:
        """List files in a Google Drive folder (path = folder ID)."""
        try:
            svc = self._get_service()
            results = svc.service.files().list(
                q=f"'{path}' in parents and trashed=false",
                fields="files(id, name, mimeType, size, modifiedTime)"
            ).execute()
            return [
                {
                    'id': f['id'],
                    'name': f['name'],
                    'mime_type': f.get('mimeType'),
                    'size': f.get('size'),
                    'modified': f.get('modifiedTime'),
                }
                for f in results.get('files', [])
            ]
        except Exception as e:
            logger.error("Failed to list Google Drive folder %s: %s", path, e)
            return []
