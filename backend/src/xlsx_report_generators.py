"""Report-specific XLSX export generators with progress reporting.

Contains the progress-aware export methods that build on the core
XLSXExportProcessor infrastructure, plus file-download helpers used
by both standard and progress-reporting export paths.
"""

import os
import io
import pandas as pd
from google_drive_service import GoogleDriveService
from googleapiclient.http import MediaIoBaseDownload
from services.storage_resolver import resolve_storage_provider, get_s3_storage
import logging

logger = logging.getLogger(__name__)


class XLSXProgressExportMixin:
    """Mixin providing progress-reporting export methods and file-download helpers.
    
    Must be used with XLSXExportProcessor which provides:
    - self._get_output_base_path(administration)
    - self.make_ledgers(year, administration)
    - self.write_workbook(data, filename, sheet_name, administration)
    - self.folder_search_log
    """

    # --- File download helper methods ---

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

    def export_files(self, data, year, administration):
        """Export files and create folder structure."""
        output_base_path = self._get_output_base_path(administration)

        folder_path = os.path.join(output_base_path, f"{administration}{year}")
        try:
            os.makedirs(folder_path, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create directory {folder_path}: {e}")
            import tempfile
            folder_path = tempfile.mkdtemp(prefix=f"{administration}{year}_")
            print(f"Using temporary directory: {folder_path}")

        df = pd.DataFrame(data)
        print(f"Total records: {len(df)}")
        print(f"Columns available: {df.columns.tolist()}")

        if 'DocUrl' not in df.columns:
            print("DocUrl column not found in data")
            return 0

        # Separate S3 keys and Google Drive URLs
        df_with_url = df[df['DocUrl'].notna() & (df['DocUrl'] != '')]
        df_s3 = df_with_url[df_with_url['DocUrl'].apply(self._is_s3_key)]
        df_drive = df_with_url[df_with_url['DocUrl'].str.contains('drive.google', na=False)]

        print(f"Records with S3 keys: {len(df_s3)}")
        print(f"Records with Google Drive URLs: {len(df_drive)}")

        if len(df_s3) == 0 and len(df_drive) == 0:
            print("No downloadable files found")
            return 0

        downloaded_count = 0
        failed_downloads = []

        # Process S3 files
        if len(df_s3) > 0:
            df_s3 = df_s3.copy()
            df_s3['ReferenceNumber'] = df_s3['ReferenceNumber'].str.strip()
            df_s3 = df_s3.drop_duplicates()
            s3_refs = sorted(df_s3['ReferenceNumber'].unique())
            s3_refs = [ref for ref in s3_refs if ref]
            for ref_num in s3_refs:
                os.makedirs(os.path.join(folder_path, ref_num), exist_ok=True)

            print(f"Found {len(df_s3)} S3 files to download")
            for _, row in df_s3.iterrows():
                if row['ReferenceNumber']:
                    dest = os.path.join(folder_path, row['ReferenceNumber'])
                    success = self._download_s3_file(row['DocUrl'], dest, administration)
                    if success:
                        downloaded_count += 1
                    else:
                        failed_downloads.append({
                            'ReferenceNumber': row['ReferenceNumber'],
                            'Document': row.get('Document', ''),
                            'DocUrl': row['DocUrl']
                        })

        # Process Google Drive files
        if len(df_drive) > 0:
            df_drive = df_drive.copy()
            df_drive['ReferenceNumber'] = df_drive['ReferenceNumber'].str.strip()
            df_drive = df_drive.drop_duplicates()
            drive_refs = sorted(df_drive['ReferenceNumber'].unique())
            drive_refs = [ref for ref in drive_refs if ref]
            for ref_num in drive_refs:
                os.makedirs(os.path.join(folder_path, ref_num), exist_ok=True)

            print(f"Found {len(df_drive)} Google Drive files to download")
            try:
                service = self._get_drive_service(administration)
                if service:
                    for _, row in df_drive.iterrows():
                        print(f"Processing file: {row['DocUrl']} -> {row['ReferenceNumber']}")
                        if row['ReferenceNumber']:
                            success = self._download_drive_file(
                                service,
                                row['DocUrl'],
                                os.path.join(folder_path, row['ReferenceNumber']),
                                row.get('Document', '')
                            )
                            if success:
                                downloaded_count += 1
                                print(f"Successfully downloaded file {downloaded_count}")
                            else:
                                failed_downloads.append({
                                    'ReferenceNumber': row['ReferenceNumber'],
                                    'Document': row.get('Document', ''),
                                    'DocUrl': row['DocUrl']
                                })
                else:
                    print("Could not get Google Drive service")
            except Exception as e:
                print(f"Error downloading files: {e}")
                import traceback
                traceback.print_exc()

        # Write log file
        self._write_download_log(folder_path, administration, year, failed_downloads)

        return downloaded_count

    def generate_xlsx_export_with_progress(self, administrations, years):
        """Generate XLSX exports with progress reporting.
        
        Yields progress dictionaries and a final 'complete' result.
        
        Args:
            administrations: List of administration identifiers
            years: List of years to process
            
        Yields:
            dict with 'type' key: 'progress' or 'complete'
        """
        total_combinations = len(administrations) * len(years)
        current_combination = 0
        results = []

        for administration in administrations:
            for year in years:
                current_combination += 1

                yield {
                    'type': 'progress',
                    'current_combination': current_combination,
                    'total_combinations': total_combinations,
                    'current_administration': administration,
                    'current_year': year,
                    'status': f'Processing {administration} {year}...'
                }

                try:
                    print(f"Processing {administration} {year}")
                    ledger_data = self.make_ledgers(year, administration)
                    print(f"Found {len(ledger_data)} records")

                    if not ledger_data:
                        result = {
                            'administration': administration,
                            'year': year,
                            'error': 'No data found for this administration/year combination',
                            'success': False
                        }
                        results.append(result)
                        yield {
                            'type': 'progress',
                            'current_combination': current_combination,
                            'total_combinations': total_combinations,
                            'current_administration': administration,
                            'current_year': year,
                            'status': f'No data found for {administration} {year}',
                            'result': result
                        }
                        continue

                    output_base_path = self._get_output_base_path(administration)
                    folder_path = os.path.join(output_base_path, f"{administration}{year}")
                    filename = os.path.join(folder_path, f"{administration}{year}.xlsx")

                    try:
                        os.makedirs(output_base_path, exist_ok=True)
                    except OSError as e:
                        print(f"Warning: Could not create base output directory {output_base_path}: {e}")
                        filename = f"{administration}{year}.xlsx"
                        print(f"Using current directory for output: {filename}")

                    yield {
                        'type': 'progress',
                        'current_combination': current_combination,
                        'total_combinations': total_combinations,
                        'current_administration': administration,
                        'current_year': year,
                        'status': f'Creating Excel file for {administration} {year}...'
                    }

                    output_file = self.write_workbook(ledger_data, filename, 'data', administration)
                    print(f"Created file: {output_file}")

                    yield {
                        'type': 'progress',
                        'current_combination': current_combination,
                        'total_combinations': total_combinations,
                        'current_administration': administration,
                        'current_year': year,
                        'status': f'Downloading files for {administration} {year}...'
                    }

                    file_count = 0
                    for file_progress in self.export_files_with_progress_generator(ledger_data, year, administration):
                        if file_progress.get('type') == 'file_progress':
                            yield {
                                'type': 'progress',
                                'current_combination': current_combination,
                                'total_combinations': total_combinations,
                                'current_administration': administration,
                                'current_year': year,
                                'status': file_progress['file_status'],
                                'file_progress': {
                                    'current_file': file_progress['current_file'],
                                    'total_files': file_progress['total_files'],
                                    'reference_number': file_progress['reference_number']
                                }
                            }
                        elif file_progress.get('type') == 'complete':
                            file_count = file_progress['downloaded_count']

                    result = {
                        'administration': administration,
                        'year': year,
                        'filename': output_file,
                        'records': len(ledger_data),
                        'files_processed': file_count,
                        'success': True
                    }
                    results.append(result)

                    yield {
                        'type': 'progress',
                        'current_combination': current_combination,
                        'total_combinations': total_combinations,
                        'current_administration': administration,
                        'current_year': year,
                        'status': f'Completed {administration} {year} - {len(ledger_data)} records, {file_count} files',
                        'result': result
                    }

                except Exception as e:
                    print(f"Error processing {administration} {year}: {str(e)}")
                    import traceback
                    traceback.print_exc()

                    result = {
                        'administration': administration,
                        'year': year,
                        'error': str(e),
                        'success': False
                    }
                    results.append(result)

                    yield {
                        'type': 'progress',
                        'current_combination': current_combination,
                        'total_combinations': total_combinations,
                        'current_administration': administration,
                        'current_year': year,
                        'status': f'Error processing {administration} {year}: {str(e)}',
                        'result': result
                    }

        successful_results = [r for r in results if r['success']]
        yield {
            'type': 'complete',
            'results': results,
            'total_processed': len(results),
            'successful': len(successful_results),
            'failed': len(results) - len(successful_results),
            'message': f'Generated {len(successful_results)} XLSX files out of {len(results)} requested'
        }

    def export_files_with_progress_generator(self, data, year, administration):
        """Export files with progress reporting as a generator.
        
        Args:
            data: List of ledger data records
            year: Year being processed
            administration: Administration identifier
            
        Yields:
            dict with 'type': 'file_progress' or 'complete'
        """
        output_base_path = self._get_output_base_path(administration)

        folder_path = os.path.join(output_base_path, f"{administration}{year}")
        try:
            os.makedirs(folder_path, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create directory {folder_path}: {e}")
            import tempfile
            folder_path = tempfile.mkdtemp(prefix=f"{administration}{year}_")
            print(f"Using temporary directory: {folder_path}")

        df = pd.DataFrame(data)
        print(f"Total records: {len(df)}")

        if 'DocUrl' not in df.columns:
            print("DocUrl column not found in data")
            yield {'type': 'complete', 'downloaded_count': 0}
            return

        df_with_url = df[df['DocUrl'].notna() & (df['DocUrl'] != '')]
        df_s3 = df_with_url[df_with_url['DocUrl'].apply(self._is_s3_key)]
        df_drive = df_with_url[df_with_url['DocUrl'].str.contains('drive.google', na=False)]

        print(f"Records with S3 keys: {len(df_s3)}")
        print(f"Records with Google Drive URLs: {len(df_drive)}")

        if len(df_s3) == 0 and len(df_drive) == 0:
            print("No downloadable files found")
            yield {'type': 'complete', 'downloaded_count': 0}
            return

        all_files = []

        if len(df_s3) > 0:
            df_s3 = df_s3.copy()
            df_s3['ReferenceNumber'] = df_s3['ReferenceNumber'].str.strip()
            df_s3 = df_s3.drop_duplicates()
            df_s3 = df_s3.copy()
            df_s3['_source'] = 's3'
            all_files.append(df_s3)

        if len(df_drive) > 0:
            df_drive = df_drive.copy()
            df_drive['ReferenceNumber'] = df_drive['ReferenceNumber'].str.strip()
            df_drive = df_drive.drop_duplicates()
            df_drive = df_drive.copy()
            df_drive['_source'] = 'drive'
            all_files.append(df_drive)

        combined_df = pd.concat(all_files, ignore_index=True)

        reference_numbers = sorted(combined_df['ReferenceNumber'].unique())
        reference_numbers = [ref for ref in reference_numbers if ref]

        for ref_num in reference_numbers:
            ref_folder = os.path.join(folder_path, ref_num)
            os.makedirs(ref_folder, exist_ok=True)

        downloaded_count = 0
        failed_downloads = []
        total_files = len(combined_df)

        print(f"Found {total_files} files to download")

        service = None
        if len(df_drive) > 0:
            try:
                service = self._get_drive_service(administration)
            except Exception as e:
                print(f"Error initializing Drive service: {e}")

        for index, (_, row) in enumerate(combined_df.iterrows()):
            yield {
                'type': 'file_progress',
                'current_file': index + 1,
                'total_files': total_files,
                'file_status': f'Downloading file {index + 1}/{total_files}: {row.get("Document", "Unknown")}',
                'reference_number': row['ReferenceNumber']
            }

            print(f"Processing file {index + 1}/{total_files}: {row['DocUrl']} -> {row['ReferenceNumber']}")

            if row['ReferenceNumber']:
                if row['_source'] == 's3':
                    success = self._download_s3_file(
                        row['DocUrl'],
                        os.path.join(folder_path, row['ReferenceNumber']),
                        administration
                    )
                elif service:
                    success = self._download_drive_file(
                        service,
                        row['DocUrl'],
                        os.path.join(folder_path, row['ReferenceNumber']),
                        row.get('Document', '')
                    )
                else:
                    print("Could not get Google Drive service")
                    success = False

                if success:
                    downloaded_count += 1
                    print(f"Successfully downloaded file {downloaded_count}")
                else:
                    failed_downloads.append({
                        'ReferenceNumber': row['ReferenceNumber'],
                        'Document': row.get('Document', ''),
                        'DocUrl': row['DocUrl']
                    })

        # Write log file
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

        yield {'type': 'complete', 'downloaded_count': downloaded_count}

    def export_files_with_progress(self, data, year, administration, progress_callback=None):
        """Export files with progress reporting via callback.
        
        Args:
            data: List of ledger data records
            year: Year being processed
            administration: Administration identifier
            progress_callback: Optional callable receiving progress dicts
            
        Returns:
            int: Number of files successfully downloaded
        """
        output_base_path = self._get_output_base_path(administration)

        folder_path = os.path.join(output_base_path, f"{administration}{year}")
        try:
            os.makedirs(folder_path, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create directory {folder_path}: {e}")
            import tempfile
            folder_path = tempfile.mkdtemp(prefix=f"{administration}{year}_")
            print(f"Using temporary directory: {folder_path}")

        df = pd.DataFrame(data)
        print(f"Total records: {len(df)}")

        if 'DocUrl' not in df.columns:
            print("DocUrl column not found in data")
            return 0

        df_with_url = df[df['DocUrl'].notna() & (df['DocUrl'] != '')]
        df_s3 = df_with_url[df_with_url['DocUrl'].apply(self._is_s3_key)]
        df_drive = df_with_url[df_with_url['DocUrl'].str.contains('drive.google', na=False)]

        print(f"Records with S3 keys: {len(df_s3)}")
        print(f"Records with Google Drive URLs: {len(df_drive)}")

        if len(df_s3) == 0 and len(df_drive) == 0:
            print("No downloadable files found")
            return 0

        all_files = []

        if len(df_s3) > 0:
            df_s3 = df_s3.copy()
            df_s3['ReferenceNumber'] = df_s3['ReferenceNumber'].str.strip()
            df_s3 = df_s3.drop_duplicates()
            df_s3 = df_s3.copy()
            df_s3['_source'] = 's3'
            all_files.append(df_s3)

        if len(df_drive) > 0:
            df_drive = df_drive.copy()
            df_drive['ReferenceNumber'] = df_drive['ReferenceNumber'].str.strip()
            df_drive = df_drive.drop_duplicates()
            df_drive = df_drive.copy()
            df_drive['_source'] = 'drive'
            all_files.append(df_drive)

        combined_df = pd.concat(all_files, ignore_index=True)

        reference_numbers = sorted(combined_df['ReferenceNumber'].unique())
        reference_numbers = [ref for ref in reference_numbers if ref]

        for ref_num in reference_numbers:
            ref_folder = os.path.join(folder_path, ref_num)
            os.makedirs(ref_folder, exist_ok=True)

        downloaded_count = 0
        failed_downloads = []
        total_files = len(combined_df)

        print(f"Found {total_files} files to download")

        service = None
        if len(df_drive) > 0:
            try:
                service = self._get_drive_service(administration)
            except Exception as e:
                print(f"Error initializing Drive service: {e}")

        for index, (_, row) in enumerate(combined_df.iterrows()):
            if progress_callback:
                progress_callback({
                    'type': 'file_progress',
                    'current_file': index + 1,
                    'total_files': total_files,
                    'file_status': f'Downloading file {index + 1}/{total_files}: {row.get("Document", "Unknown")}',
                    'reference_number': row['ReferenceNumber']
                })

            print(f"Processing file {index + 1}/{total_files}: {row['DocUrl']} -> {row['ReferenceNumber']}")

            if row['ReferenceNumber']:
                if row['_source'] == 's3':
                    success = self._download_s3_file(
                        row['DocUrl'],
                        os.path.join(folder_path, row['ReferenceNumber']),
                        administration
                    )
                elif service:
                    success = self._download_drive_file(
                        service,
                        row['DocUrl'],
                        os.path.join(folder_path, row['ReferenceNumber']),
                        row.get('Document', '')
                    )
                else:
                    print("Could not get Google Drive service")
                    success = False

                if success:
                    downloaded_count += 1
                    print(f"Successfully downloaded file {downloaded_count}")
                else:
                    failed_downloads.append({
                        'ReferenceNumber': row['ReferenceNumber'],
                        'Document': row.get('Document', ''),
                        'DocUrl': row['DocUrl']
                    })

        # Write log file
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

        return downloaded_count
