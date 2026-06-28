"""
XLSX Download Helpers

File download helper methods used by the XLSX export system.
Handles downloading from Google Drive and S3, with logging and error handling.

Extracted from xlsx_report_generators.py to keep files under 500 lines.
"""

import os
import io
import logging

from google_drive_service import GoogleDriveService
from googleapiclient.http import MediaIoBaseDownload
from services.storage_resolver import resolve_storage_provider, get_s3_storage

logger = logging.getLogger(__name__)


class XLSXDownloadHelpersMixin:
    """Mixin providing file-download helpers for XLSX export.

    Must be used with a class that provides:
    - self.folder_search_log (list)
    """

    def _write_download_log(self, folder_path, administration, year, failed_downloads):
        """Write download log file with failed downloads and folder search results."""
        log_file = os.path.join(folder_path, 'download_log.txt')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"Download Log - {administration} {year}\n")
            f.write("=" * 50 + "\n\n")

            if failed_downloads:
                f.write("FAILED DOWNLOADS:\n")
                f.write("-" * 20 + "\n")
                for item in failed_downloads:
                    f.write(f"Reference Number: {item['ReferenceNumber']}\n")
                    f.write(f"Document: {item['Document']}\n")
                    f.write(f"URL: {item['DocUrl']}\n")
                    f.write("-" * 30 + "\n")

            if hasattr(self, 'folder_search_log') and self.folder_search_log:
                f.write("\nFOLDER SEARCH RESULTS:\n")
                f.write("-" * 25 + "\n")
                for item in self.folder_search_log:
                    f.write(f"Searched for: {item['document_searched']}\n")
                    f.write(f"Folder ID: {item['folder_id']}\n")
                    f.write(f"Files found: {', '.join(item['files_found'])}\n")
                    f.write("-" * 30 + "\n")

        print(f"Created log file: {log_file}")

    def _find_document_in_folder(self, service, folder_id, dest_folder, document_name):
        """Find and download specific document in folder."""
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)"
            ).execute()

            files = results.get('files', [])

            for file_item in files:
                if file_item['mimeType'] != 'application/vnd.google-apps.folder':
                    if file_item['name'] == document_name:
                        print(f"Found exact match: {file_item['name']}")
                        return self._download_single_file(
                            service, file_item['id'], file_item['name'], dest_folder
                        )

            if not hasattr(self, 'folder_search_log'):
                self.folder_search_log = []

            self.folder_search_log.append({
                'document_searched': document_name,
                'folder_id': folder_id,
                'files_found': [f['name'] for f in files if f['mimeType'] != 'application/vnd.google-apps.folder']
            })

            print(f"Document '{document_name}' not found in folder")
            return False

        except Exception as e:
            print(f"Error searching folder: {e}")
            return False

    def _download_single_file(self, service, file_id, filename, dest_folder):
        """Download a single file by ID."""
        try:
            request = service.files().get_media(fileId=file_id)
            file_path = os.path.join(dest_folder, filename)

            with io.FileIO(file_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()

            print(f"Successfully downloaded: {filename}")
            return True

        except Exception as e:
            print(f"Error downloading file {filename}: {e}")
            return False

    def _get_drive_service(self, administration):
        """Get Google Drive service.

        Args:
            administration: Tenant/administration identifier

        Returns:
            Google Drive service object, or None if provider is S3 or initialization fails
        """
        try:
            provider = resolve_storage_provider(administration)
            if provider == 's3_shared':
                return None
            drive_service = GoogleDriveService(administration)
            return drive_service.service
        except Exception as e:
            print(f"Could not initialize Google Drive service: {e}")
        return None

    def _download_s3_file(self, key, destination_folder, administration):
        """Download file from S3 by key and save to destination folder.

        Args:
            key: S3 object key (e.g. 'AcmeBV/invoices/Supplier1/uuid_file.pdf')
            destination_folder: Local folder path to save the file
            administration: Tenant/administration identifier

        Returns:
            True if download succeeded, False otherwise
        """
        try:
            storage = get_s3_storage(administration)
            file_data = storage.download(key)
            filename = os.path.basename(key)
            file_path = os.path.join(destination_folder, filename)
            with open(file_path, 'wb') as f:
                f.write(file_data)
            print(f"Successfully downloaded S3 file: {filename}")
            return True
        except Exception as e:
            print(f"Error downloading S3 file {key}: {e}")
            return False

    def _is_s3_key(self, doc_url):
        """Check if a DocUrl value is an S3 key rather than a Google Drive URL.

        Args:
            doc_url: The document URL or S3 key string

        Returns:
            True if the value looks like an S3 key, False otherwise
        """
        if not doc_url or not isinstance(doc_url, str):
            return False
        return '/' in doc_url and 'drive.google' not in doc_url

    def _download_drive_file(self, service, doc_url, dest_folder, document_name=''):
        """Download file from Google Drive."""
        try:
            print(f"Downloading from URL: {doc_url}")
            file_id = doc_url.split('&')[0]
            if '/d/' in file_id:
                file_id = file_id.split('/d/')[1].split('/')[0]
            elif '/folders/' in file_id:
                file_id = file_id.split('/folders/')[1].split('/')[0]
            elif 'id=' in file_id:
                file_id = file_id.split('id=')[1]
            else:
                file_id = file_id.split('/')[-1]

            print(f"Extracted file ID: {file_id}")

            file_metadata = service.files().get(fileId=file_id).execute()
            filename = file_metadata.get('name', f'file_{file_id}')
            mime_type = file_metadata.get('mimeType', '')
            print(f"File name: {filename}, MIME type: {mime_type}")

            if mime_type == 'application/vnd.google-apps.folder':
                print(f"Found folder: {filename}, searching for document: {document_name}")
                return self._find_document_in_folder(service, file_id, dest_folder, document_name)

            request = service.files().get_media(fileId=file_id)
            file_path = os.path.join(dest_folder, filename)
            print(f"Saving to: {file_path}")

            with io.FileIO(file_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()

            print(f"Successfully downloaded: {filename}")
            return True

        except Exception as e:
            print(f"Error downloading file {doc_url}: {e}")
            return False
