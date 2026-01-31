import os
import shutil
from datetime import datetime
from database import DatabaseManager
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from google_drive_service import GoogleDriveService
import io
from googleapiclient.http import MediaIoBaseDownload
from services.template_service import TemplateService
import logging

logger = logging.getLogger(__name__)

class XLSXExportProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.template_service = TemplateService(self.db)
        # Default template path (fallback)
        self.default_template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'xlsx', 'template.xlsx')
        # Default output path (fallback)
        if os.getenv('DOCKER_ENV') or os.path.exists('/.dockerenv'):
            self.default_output_base_path = '/app/reports'
            os.makedirs(self.default_output_base_path, exist_ok=True)
        else:
            self.default_output_base_path = r'C:\Users\peter\OneDrive\Admin\reports'
        self.folder_search_log = []
        logger.info("XLSXExportProcessor initialized with TemplateService")
    
    def _get_template_path(self, administration):
        """Get template path for administration using TemplateService"""
        try:
            # Get template metadata from TemplateService
            metadata = self.template_service.get_template_metadata(
                administration, 
                'financial_report_xlsx'
            )
            
            if metadata and metadata.get('field_mappings'):
                field_mappings = metadata['field_mappings']
                template_path = field_mappings.get('template_path')
                
                if template_path and os.path.exists(template_path):
                    logger.info(
                        f"Using template path from TemplateService for {administration}: "
                        f"{template_path}"
                    )
                    return template_path
                else:
                    logger.warning(
                        f"Template path from database not found: {template_path}, "
                        f"using default"
                    )
        except Exception as e:
            logger.warning(f"Could not get template path from TemplateService: {e}")
        
        logger.info(f"Using default template path for {administration}")
        return self.default_template_path
    
    def _get_output_base_path(self, administration):
        """Get output base path for administration using TemplateService"""
        try:
            # Get template metadata from TemplateService
            metadata = self.template_service.get_template_metadata(
                administration,
                'financial_report_xlsx'
            )
            
            if metadata and metadata.get('field_mappings'):
                field_mappings = metadata['field_mappings']
                output_path = field_mappings.get('output_base_path')
                
                if output_path:
                    # Ensure directory exists
                    os.makedirs(output_path, exist_ok=True)
                    logger.info(
                        f"Using output path from TemplateService for {administration}: "
                        f"{output_path}"
                    )
                    return output_path
        except Exception as e:
            logger.warning(f"Could not get output path from TemplateService: {e}")
        
        logger.info(f"Using default output path for {administration}")
        return self.default_output_base_path
        
    def make_ledgers(self, year, administration):
        """Calculate starting balance and add all transactions for specific year and administration"""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Get balance accounts (VW = N) for years before target year
            balance_query = """
                SELECT Reknum, AccountName, Parent, Administration,
                       SUM(Amount) as Amount
                FROM vw_mutaties 
                WHERE VW = 'N' AND Administration LIKE %s AND jaar < %s
                GROUP BY Reknum, AccountName, Parent, Administration
                HAVING ABS(SUM(Amount)) > 0.01
            """
            cursor.execute(balance_query, [f"{administration}%", year])
            balance_data = cursor.fetchall()
            
            # Create beginning balance records
            beginning_balance = []
            for row in balance_data:
                balance_record = {
                    'TransactionNumber': f'Beginbalans {year}',
                    'TransactionDate': f'{year}-01-01',
                    'TransactionDescription': f'Beginbalans van het jaar {year} van Administratie {administration}',
                    'Amount': round(row['Amount'], 2),
                    'Reknum': row['Reknum'],
                    'AccountName': row['AccountName'],
                    'Parent': row['Parent'],
                    'Administration': row['Administration'],
                    'VW': 'N',
                    'jaar': year,
                    'kwartaal': 1,
                    'maand': 1,
                    'week': 1,
                    'ReferenceNumber': '',
                    'DocUrl': '',
                    'Document': ''
                }
                beginning_balance.append(balance_record)
            
            # Get all transactions for the specific year
            transactions_query = """
                SELECT TransactionNumber, TransactionDate, TransactionDescription, Amount, 
                       Reknum, AccountName, Parent, Administration, VW, jaar, kwartaal, 
                       maand, week, ReferenceNumber, Ref3 as DocUrl, Ref4 as Document
                FROM vw_mutaties 
                WHERE Administration LIKE %s AND jaar = %s
                ORDER BY TransactionDate, Reknum
            """
            cursor.execute(transactions_query, [f"{administration}%", year])
            transactions_data = cursor.fetchall()
            
            # Combine beginning balance and transactions
            all_data = beginning_balance + transactions_data
            
            return all_data
            
        finally:
            cursor.close()
            conn.close()
    
    def export_files(self, data, year, administration):
        """Export files and create folder structure"""
        # Get output base path for this administration
        output_base_path = self._get_output_base_path(administration)
        
        # Create output folder
        folder_path = os.path.join(output_base_path, f"{administration}{year}")
        try:
            os.makedirs(folder_path, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create directory {folder_path}: {e}")
            # Fallback to a temporary directory or current directory
            import tempfile
            folder_path = tempfile.mkdtemp(prefix=f"{administration}{year}_")
            print(f"Using temporary directory: {folder_path}")
        
        # Filter data for Google Drive files
        df = pd.DataFrame(data)
        print(f"Total records: {len(df)}")
        print(f"Columns available: {df.columns.tolist()}")
        
        # Check if DocUrl column exists and has Google Drive links
        if 'DocUrl' not in df.columns:
            print("DocUrl column not found in data")
            return 0
            
        df = df[df['DocUrl'].str.contains('drive.google', na=False)]
        print(f"Records with Google Drive URLs: {len(df)}")
        
        if len(df) == 0:
            print("No Google Drive files found")
            return 0
            
        df['ReferenceNumber'] = df['ReferenceNumber'].str.strip()
        df = df.drop_duplicates()
        
        # Create reference number folders
        reference_numbers = sorted(df['ReferenceNumber'].unique())
        reference_numbers = [ref for ref in reference_numbers if ref]
        
        for ref_num in reference_numbers:
            ref_folder = os.path.join(folder_path, ref_num)
            os.makedirs(ref_folder, exist_ok=True)
        
        # Download files from Google Drive
        downloaded_count = 0
        failed_downloads = []
        print(f"Found {len(df)} Google Drive files to download")
        try:
            service = self._get_drive_service()
            if service:
                for _, row in df.iterrows():
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
        
        # Write log file for failed downloads and folder contents
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
    
    def write_workbook(self, data, filename, sheet_name='data', administration=None):
        """Write data to Excel workbook using template"""
        # Ensure output directory exists - create full path if needed
        output_dir = os.path.dirname(filename)
        if output_dir:  # Only create if there's actually a directory path
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                print(f"Warning: Could not create directory {output_dir}: {e}")
                # Fallback to current directory
                filename = os.path.basename(filename)
                print(f"Falling back to current directory: {filename}")
        
        # Get template path for this administration
        template_path = self._get_template_path(administration) if administration else self.default_template_path
        
        # Copy template if target file doesn't exist
        if not os.path.exists(filename):
            if os.path.exists(template_path):
                shutil.copy2(template_path, filename)
            else:
                # Create new workbook if template doesn't exist
                from openpyxl import Workbook
                wb = Workbook()
                wb.save(filename)
        
        # Load workbook
        wb = load_workbook(filename)
        
        # Remove existing data sheet if it exists
        if sheet_name in wb.sheetnames:
            wb.remove(wb[sheet_name])
        
        # Create new data sheet
        ws = wb.create_sheet(sheet_name)
        
        # Convert data to DataFrame and select only required columns
        df = pd.DataFrame(data)
        required_columns = ['TransactionNumber', 'TransactionDate', 'TransactionDescription', 'Amount', 'Reknum', 'AccountName', 'SubParent', 'Parent', 'VW', 'jaar', 'kwartaal', 'maand', 'week', 'ReferenceNumber', 'Administration', 'DocUrl', 'Document']
        # Keep all available columns from required list
        available_columns = [col for col in required_columns if col in df.columns]
        df = df[available_columns]
        
        # Convert Amount column to numeric
        if 'Amount' in df.columns:
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        
        # Clean string columns (but not Amount)
        for col in df.select_dtypes(include=['object']).columns:
            if col != 'Amount':
                df[col] = df[col].astype(str).str.strip()
        
        # Write data to worksheet
        for r in dataframe_to_rows(df, index=False, header=True):
            ws.append(r)
        
        # Style the header row and format Amount column
        header_font = Font(bold=True)
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        for cell in ws[1]:
            cell.font = header_font
            cell.border = thin_border
        
        # Format Amount column as number
        amount_col = None
        for idx, cell in enumerate(ws[1], 1):
            if cell.value == 'Amount':
                amount_col = idx
                break
        
        if amount_col:
            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row=row, column=amount_col)
                if cell.value is not None:
                    cell.number_format = '0.00'
        
        # Add autofilter
        ws.auto_filter.ref = ws.dimensions
        
        # Save workbook
        wb.save(filename)
        return filename
    
    def generate_xlsx_export(self, administrations, years):
        """Generate XLSX exports for specified administrations and years"""
        results = []
        
        for administration in administrations:
            for year in years:
                try:
                    print(f"Processing {administration} {year}")
                    
                    # Get ledger data
                    ledger_data = self.make_ledgers(year, administration)
                    print(f"Found {len(ledger_data)} records")
                    
                    if not ledger_data:
                        results.append({
                            'administration': administration,
                            'year': year,
                            'error': 'No data found for this administration/year combination',
                            'success': False
                        })
                        continue
                    
                    # Get output base path for this administration
                    output_base_path = self._get_output_base_path(administration)
                    
                    # Create output folder and filename
                    folder_path = os.path.join(output_base_path, f"{administration}{year}")
                    filename = os.path.join(folder_path, f"{administration}{year}.xlsx")
                    
                    # Ensure base output directory exists
                    try:
                        os.makedirs(output_base_path, exist_ok=True)
                    except OSError as e:
                        print(f"Warning: Could not create base output directory {output_base_path}: {e}")
                        # Use current directory as fallback
                        filename = f"{administration}{year}.xlsx"
                        print(f"Using current directory for output: {filename}")
                    
                    # Write workbook (pass administration for template lookup)
                    output_file = self.write_workbook(ledger_data, filename, 'data', administration)
                    print(f"Created file: {output_file}")
                    
                    # Export files (create folder structure)
                    file_count = self.export_files(ledger_data, year, administration)
                    
                    results.append({
                        'administration': administration,
                        'year': year,
                        'filename': output_file,
                        'records': len(ledger_data),
                        'files_processed': file_count,
                        'success': True
                    })
                    
                except Exception as e:
                    print(f"Error processing {administration} {year}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    results.append({
                        'administration': administration,
                        'year': year,
                        'error': str(e),
                        'success': False
                    })
        
        return results
    
    def generate_xlsx_export_with_progress(self, administrations, years):
        """Generate XLSX exports with progress reporting"""
        total_combinations = len(administrations) * len(years)
        current_combination = 0
        results = []
        
        for administration in administrations:
            for year in years:
                current_combination += 1
                
                # Yield progress update
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
                    
                    # Get ledger data
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
                        
                        # Yield progress with error
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
                    
                    # Get output base path for this administration
                    output_base_path = self._get_output_base_path(administration)
                    
                    # Create output folder and filename
                    folder_path = os.path.join(output_base_path, f"{administration}{year}")
                    filename = os.path.join(folder_path, f"{administration}{year}.xlsx")
                    
                    # Ensure base output directory exists
                    try:
                        os.makedirs(output_base_path, exist_ok=True)
                    except OSError as e:
                        print(f"Warning: Could not create base output directory {output_base_path}: {e}")
                        # Use current directory as fallback
                        filename = f"{administration}{year}.xlsx"
                        print(f"Using current directory for output: {filename}")
                    
                    # Write workbook
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
                    
                    # Export files (create folder structure) with progress
                    yield {
                        'type': 'progress',
                        'current_combination': current_combination,
                        'total_combinations': total_combinations,
                        'current_administration': administration,
                        'current_year': year,
                        'status': f'Downloading Google Drive files for {administration} {year}...'
                    }
                    
                    # Use generator for file-level progress
                    file_count = 0
                    for file_progress in self.export_files_with_progress_generator(ledger_data, year, administration):
                        if file_progress.get('type') == 'file_progress':
                            # Yield file-level progress
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
                    
                    # Yield completion for this combination
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
                    
                    # Yield error for this combination
                    yield {
                        'type': 'progress',
                        'current_combination': current_combination,
                        'total_combinations': total_combinations,
                        'current_administration': administration,
                        'current_year': year,
                        'status': f'Error processing {administration} {year}: {str(e)}',
                        'result': result
                    }
        
        # Yield final results
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
        """Export files with progress reporting as a generator"""
        # Get output base path for this administration
        output_base_path = self._get_output_base_path(administration)
        
        # Create output folder
        folder_path = os.path.join(output_base_path, f"{administration}{year}")
        try:
            os.makedirs(folder_path, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create directory {folder_path}: {e}")
            # Fallback to a temporary directory or current directory
            import tempfile
            folder_path = tempfile.mkdtemp(prefix=f"{administration}{year}_")
            print(f"Using temporary directory: {folder_path}")
        
        # Filter data for Google Drive files
        df = pd.DataFrame(data)
        print(f"Total records: {len(df)}")
        
        # Check if DocUrl column exists and has Google Drive links
        if 'DocUrl' not in df.columns:
            print("DocUrl column not found in data")
            yield {'type': 'complete', 'downloaded_count': 0}
            return
            
        df = df[df['DocUrl'].str.contains('drive.google', na=False)]
        print(f"Records with Google Drive URLs: {len(df)}")
        
        if len(df) == 0:
            print("No Google Drive files found")
            yield {'type': 'complete', 'downloaded_count': 0}
            return
            
        df['ReferenceNumber'] = df['ReferenceNumber'].str.strip()
        df = df.drop_duplicates()
        
        # Create reference number folders
        reference_numbers = sorted(df['ReferenceNumber'].unique())
        reference_numbers = [ref for ref in reference_numbers if ref]
        
        for ref_num in reference_numbers:
            ref_folder = os.path.join(folder_path, ref_num)
            os.makedirs(ref_folder, exist_ok=True)
        
        # Download files from Google Drive with progress reporting
        downloaded_count = 0
        failed_downloads = []
        total_files = len(df)
        
        print(f"Found {total_files} Google Drive files to download")
        
        try:
            service = self._get_drive_service()
            if service:
                for index, (_, row) in enumerate(df.iterrows()):
                    # Yield progress for each file
                    yield {
                        'type': 'file_progress',
                        'current_file': index + 1,
                        'total_files': total_files,
                        'file_status': f'Downloading file {index + 1}/{total_files}: {row.get("Document", "Unknown")}',
                        'reference_number': row['ReferenceNumber']
                    }
                    
                    print(f"Processing file {index + 1}/{total_files}: {row['DocUrl']} -> {row['ReferenceNumber']}")
                    
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
        
        # Write log file for failed downloads and folder contents
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
        """Export files with progress reporting for individual file downloads"""
        # Get output base path for this administration
        output_base_path = self._get_output_base_path(administration)
        
        # Create output folder
        folder_path = os.path.join(output_base_path, f"{administration}{year}")
        try:
            os.makedirs(folder_path, exist_ok=True)
        except OSError as e:
            print(f"Warning: Could not create directory {folder_path}: {e}")
            # Fallback to a temporary directory or current directory
            import tempfile
            folder_path = tempfile.mkdtemp(prefix=f"{administration}{year}_")
            print(f"Using temporary directory: {folder_path}")
        
        # Filter data for Google Drive files
        df = pd.DataFrame(data)
        print(f"Total records: {len(df)}")
        
        # Check if DocUrl column exists and has Google Drive links
        if 'DocUrl' not in df.columns:
            print("DocUrl column not found in data")
            return 0
            
        df = df[df['DocUrl'].str.contains('drive.google', na=False)]
        print(f"Records with Google Drive URLs: {len(df)}")
        
        if len(df) == 0:
            print("No Google Drive files found")
            return 0
            
        df['ReferenceNumber'] = df['ReferenceNumber'].str.strip()
        df = df.drop_duplicates()
        
        # Create reference number folders
        reference_numbers = sorted(df['ReferenceNumber'].unique())
        reference_numbers = [ref for ref in reference_numbers if ref]
        
        for ref_num in reference_numbers:
            ref_folder = os.path.join(folder_path, ref_num)
            os.makedirs(ref_folder, exist_ok=True)
        
        # Download files from Google Drive with progress reporting
        downloaded_count = 0
        failed_downloads = []
        total_files = len(df)
        
        print(f"Found {total_files} Google Drive files to download")
        
        try:
            service = self._get_drive_service()
            if service:
                for index, (_, row) in enumerate(df.iterrows()):
                    # Report progress for each file
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
        
        # Write log file for failed downloads and folder contents
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
    
    def _find_document_in_folder(self, service, folder_id, dest_folder, document_name):
        """Find and download specific document in folder"""
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)"
            ).execute()
            
            files = results.get('files', [])
            
            # Look for exact match first
            for file_item in files:
                if file_item['mimeType'] != 'application/vnd.google-apps.folder':
                    if file_item['name'] == document_name:
                        print(f"Found exact match: {file_item['name']}")
                        return self._download_single_file(service, file_item['id'], file_item['name'], dest_folder)
            
            # If no exact match, log what was found
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
        """Download a single file by ID"""
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
    
    def _get_drive_service(self):
        """Get Google Drive service"""
        try:
            drive_service = GoogleDriveService()
            return drive_service.service
        except Exception as e:
            print(f"Could not initialize Google Drive service: {e}")
        return None
    
    def _download_drive_file(self, service, doc_url, dest_folder, document_name=''):
        """Download file from Google Drive"""
        try:
            print(f"Downloading from URL: {doc_url}")
            # Extract file ID from URL (same as R code: str_split(docUrl, "&")[[1]][1])
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
            
            # Get file metadata
            file_metadata = service.files().get(fileId=file_id).execute()
            filename = file_metadata.get('name', f'file_{file_id}')
            mime_type = file_metadata.get('mimeType', '')
            print(f"File name: {filename}, MIME type: {mime_type}")
            
            # Skip folders but find specific document inside
            if mime_type == 'application/vnd.google-apps.folder':
                print(f"Found folder: {filename}, searching for document: {document_name}")
                return self._find_document_in_folder(service, file_id, dest_folder, document_name)
            
            # Download file
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