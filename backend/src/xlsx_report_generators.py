"""Report-specific XLSX export generators with progress reporting.

Contains the progress-aware export methods that build on the core
XLSXExportProcessor infrastructure. File-download helpers are in
xlsx_download_helpers.py.
"""

import os
import pandas as pd
from xlsx_download_helpers import XLSXDownloadHelpersMixin
import logging

logger = logging.getLogger(__name__)


class XLSXProgressExportMixin(XLSXDownloadHelpersMixin):
    """Mixin providing progress-reporting export methods and file-download helpers.
    
    Must be used with XLSXExportProcessor which provides:
    - self._get_output_base_path(administration)
    - self.make_ledgers(year, administration)
    - self.write_workbook(data, filename, sheet_name, administration)
    - self.folder_search_log
    """

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
