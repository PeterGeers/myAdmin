from database import DatabaseManager
from google_drive_service import GoogleDriveService
import re

class PDFValidator:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.drive_service = None
        try:
            self.drive_service = GoogleDriveService()
        except Exception as e:
            print(f"Warning: Could not initialize Google Drive service: {e}")
            self.drive_service = None
    
    def validate_pdf_urls(self):
        """Validate all Google Drive URLs in mutaties table"""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Get distinct records with Google Drive URLs
            query = """
                SELECT DISTINCT ReferenceNumber, Ref3, Ref4, 
                       MAX(ID) as ID, MAX(TransactionNumber) as TransactionNumber, 
                       MAX(TransactionDate) as TransactionDate, MAX(TransactionDescription) as TransactionDescription,
                       MAX(TransactionAmount) as TransactionAmount, MAX(Administration) as Administration
                FROM mutaties 
                WHERE Ref3 REGEXP 'google'
                GROUP BY ReferenceNumber, Ref3, Ref4
            """
            cursor.execute(query)
            records = cursor.fetchall()
            
            total_records = len(records)
            validation_results = []
            ok_count = 0
            failed_count = 0
            
            for i, record in enumerate(records):
                result = self._validate_single_record(record)
                
                if result['status'] == 'ok':
                    ok_count += 1
                else:
                    failed_count += 1
                    validation_results.append(result)
            
            return {
                'validation_results': validation_results,
                'total_records': total_records,
                'ok_count': ok_count,
                'failed_count': failed_count
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def validate_pdf_urls_with_progress(self, year=None, administration=None):
        """Generator that yields progress updates during validation"""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Build WHERE clause with filters
            where_clause = "WHERE Ref3 REGEXP 'google'"
            params = []
            
            if year and year != 'all':
                where_clause += " AND YEAR(TransactionDate) = %s"
                params.append(year)
            
            if administration and administration != 'all':
                where_clause += " AND Administration = %s"
                params.append(administration)
            
            print(f"Validating year: {year}, administration: {administration}")
            
            query = f"""
                SELECT DISTINCT ReferenceNumber, Ref3, Ref4, 
                       MAX(ID) as ID, MAX(TransactionNumber) as TransactionNumber, 
                       MAX(TransactionDate) as TransactionDate, MAX(TransactionDescription) as TransactionDescription,
                       MAX(TransactionAmount) as TransactionAmount, MAX(Administration) as Administration
                FROM mutaties 
                {where_clause}
                GROUP BY ReferenceNumber, Ref3, Ref4
                ORDER BY MAX(ID)
            """
            cursor.execute(query, params)
            records = cursor.fetchall()
            print(f"Found {len(records)} records for year {year}, administration {administration}")
            
            total_records = len(records)
            validation_results = []
            ok_count = 0
            failed_count = 0
            
            if total_records == 0:
                yield {
                    'current': 0,
                    'total': 0,
                    'ok_count': 0,
                    'failed_count': 0,
                    'validation_results': []
                }
                return
            
            for i, record in enumerate(records):
                
                result = self._validate_single_record(record)
                
                if result['status'] == 'ok':
                    ok_count += 1
                else:
                    failed_count += 1
                    validation_results.append(result)
                
                # Yield progress every 10 records or at the end
                if (i + 1) % 10 == 0 or i == total_records - 1:
                    yield {
                        'current': i + 1,
                        'total': total_records,
                        'ok_count': ok_count,
                        'failed_count': failed_count,
                        'validation_results': validation_results if i == total_records - 1 else None
                    }
            
        finally:
            cursor.close()
            conn.close()
    
    def get_administrations_for_year(self, year=None):
        """Get distinct administrations for a specific year"""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            where_clause = "WHERE Ref3 REGEXP 'google'"
            params = []
            
            if year and year != 'all':
                where_clause += " AND YEAR(TransactionDate) = %s"
                params.append(year)
            
            query = f"""
                SELECT DISTINCT Administration
                FROM mutaties 
                {where_clause}
                ORDER BY Administration
            """
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            return [row['Administration'] for row in results if row['Administration']]
            
        finally:
            cursor.close()
            conn.close()
    
    def _validate_single_record(self, record):
        """Validate a single record's Google Drive URL"""
        ref3_url = record['Ref3']
        ref4_name = record['Ref4']
        
        try:
            # Check if URL is Gmail - mark as needs manual verification
            if 'mail.google.com' in ref3_url:
                return {'status': 'gmail_manual_check', 'record': record}
            
            # Check if URL is a file
            if '/file/d/' in ref3_url or '/open?id=' in ref3_url:
                file_id = self._extract_file_id(ref3_url)
                if file_id and self._file_exists(file_id):
                    return {'status': 'ok', 'record': record}
                else:
                    return {'status': 'file_not_found', 'record': record}
            
            # Check if URL is a folder
            elif '/folders/' in ref3_url:
                folder_id = self._extract_folder_id(ref3_url)
                file_url = self._find_file_in_folder(folder_id, ref4_name)
                if file_url:
                    # Update Ref3 with correct file URL
                    self._update_ref3(record['ID'], file_url)
                    return {'status': 'updated', 'record': record, 'new_url': file_url}
                else:
                    return {'status': 'file_not_in_folder', 'record': record}
            
            # Try to find folder by reference number
            else:
                folder_url = self._find_folder_by_reference(record['ReferenceNumber'])
                if folder_url:
                    folder_id = self._extract_folder_id(folder_url)
                    file_url = self._find_file_in_folder(folder_id, ref4_name)
                    if file_url:
                        self._update_ref3(record['ID'], file_url)
                        return {'status': 'updated', 'record': record, 'new_url': file_url}
                
                return {'status': 'missing', 'record': record}
                
        except Exception as e:
            return {'status': 'error', 'record': record, 'error': str(e)}
    
    def _extract_file_id(self, url):
        """Extract file ID from Google Drive file URL"""
        import html
        print(f"Extracting file ID from URL: {url}")
        
        # Decode HTML entities
        decoded_url = html.unescape(url)
        print(f"Decoded URL: {decoded_url}")
        
        # Try /file/d/ format first
        match = re.search(r'/file/d/([a-zA-Z0-9-_]+)', decoded_url)
        if match:
            file_id = match.group(1)
            print(f"Extracted file ID (file/d format): {file_id}")
            return file_id
        
        # Try /open?id= format
        match = re.search(r'/open\?id=([a-zA-Z0-9-_]+)', decoded_url)
        if match:
            file_id = match.group(1)
            print(f"Extracted file ID (open?id format): {file_id}")
            return file_id
        
        # Try id= parameter anywhere in URL
        match = re.search(r'[?&]id=([a-zA-Z0-9-_]+)', decoded_url)
        if match:
            file_id = match.group(1)
            print(f"Extracted file ID (id parameter): {file_id}")
            return file_id
        
        print(f"Could not extract file ID from URL")
        return None
    
    def _extract_folder_id(self, url):
        """Extract folder ID from Google Drive folder URL"""
        match = re.search(r'/folders/([a-zA-Z0-9-_]+)', url)
        return match.group(1) if match else None
    
    def _file_exists(self, file_id):
        """Check if file exists in Google Drive"""
        if not self.drive_service:
            print(f"Google Drive service not available, cannot check file ID: {file_id}")
            return False
        try:
            print(f"Checking file existence for ID: {file_id}")
            result = self.drive_service.service.files().get(fileId=file_id).execute()
            print(f"File exists: {result.get('name', 'Unknown')}, ID: {file_id}")
            return True
        except Exception as e:
            print(f"File not found or error for ID {file_id}: {e}")
            return False
    
    def _find_file_in_folder(self, folder_id, filename):
        """Find specific file in Google Drive folder"""
        if not self.drive_service:
            print(f"Google Drive service not available, cannot search folder {folder_id}")
            return None
        try:
            results = self.drive_service.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            for file_item in files:
                if file_item['name'] == filename:
                    return f"https://drive.google.com/file/d/{file_item['id']}/view"
            
            return None
        except:
            return None
    
    def _find_folder_by_reference(self, reference_number):
        """Find folder by reference number (placeholder - implement based on your folder structure)"""
        # This would need to be implemented based on how folders are organized
        # For now, return None
        return None
    
    def _extract_gmail_message_id(self, url):
        """Extract message ID from Gmail URL"""
        import re
        print(f"Extracting Gmail message ID from: {url}")
        # Gmail URLs format: https://mail.google.com/mail/u/0/#inbox/message_id
        # Handle both old format (hex) and new format (alphanumeric)
        match = re.search(r'#[^/]+/([a-zA-Z0-9]+)', url)
        message_id = match.group(1) if match else None
        print(f"Extracted Gmail message ID: {message_id}")
        return message_id
    
    def _gmail_message_exists(self, message_id):
        """Check if Gmail message exists using Gmail API"""
        try:
            from googleapiclient.discovery import build
            print(f"Checking Gmail message existence for ID: {message_id}")
            
            # Build Gmail service with same credentials as Drive
            gmail_service = build('gmail', 'v1', credentials=self.drive_service.service._http.credentials)
            
            # Try to get the message
            message = gmail_service.users().messages().get(userId='me', id=message_id, format='minimal').execute()
            print(f"Gmail message exists: {message_id}")
            return True
        except Exception as e:
            print(f"Gmail message not found or error for ID {message_id}: {e}")
            print(f"Error type: {type(e).__name__}")
            return False
    
    def _update_ref3(self, record_id, new_url):
        """Update Ref3 field in database"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("UPDATE mutaties SET Ref3 = %s WHERE ID = %s", [new_url, record_id])
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    
    def update_record(self, old_ref3, reference_number=None, ref3=None, ref4=None):
        """Update all records with matching Ref3"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            updates = []
            params = []
            
            if reference_number is not None and reference_number.strip():
                updates.append("ReferenceNumber = %s")
                params.append(reference_number.strip())
            
            if ref3 is not None and ref3.strip():
                updates.append("Ref3 = %s")
                params.append(ref3.strip())
            
            if ref4 is not None and ref4.strip():
                updates.append("Ref4 = %s")
                params.append(ref4.strip())
            
            if updates:
                query = f"UPDATE mutaties SET {', '.join(updates)} WHERE Ref3 = %s"
                all_params = params + [old_ref3]
                print(f"Executing query: {query}")
                print(f"With params: {all_params}")
                cursor.execute(query, all_params)
                affected_rows = cursor.rowcount
                conn.commit()
                print(f"Updated {affected_rows} records with Ref3={old_ref3}")
                return affected_rows > 0
            
            print(f"No updates for Ref3={old_ref3}")
            return False
            
        except Exception as e:
            print(f"Error updating records with Ref3={old_ref3}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()