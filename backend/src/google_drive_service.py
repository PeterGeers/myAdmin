from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/drive']

logger = logging.getLogger(__name__)


class GoogleDriveAuthenticationError(Exception):
    """Custom exception for Google Drive authentication errors"""
    def __init__(self, administration, error_type, message, admin_action=None):
        self.administration = administration
        self.error_type = error_type
        self.message = message
        self.admin_action = admin_action
        super().__init__(self.message)
    
    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            'error': 'google_drive_auth_error',
            'error_type': self.error_type,
            'administration': self.administration,
            'message': self.message,
            'user_action': 'Please reconnect your Google Drive account.',
            'admin_action': self.admin_action,
            'can_reconnect': True  # Flag to show reconnect button in UI
        }


class GoogleDriveService:
    def __init__(self, administration: str):
        """
        Initialize GoogleDriveService for a specific administration/tenant.
        
        Args:
            administration: The tenant/administration identifier (e.g., 'GoodwinSolutions', 'PeterPrive')
        """
        self.administration = administration
        self.service = self._authenticate()
    
    def _authenticate(self):
        """
        Authenticate with Google Drive using credentials from database.
        
        Retrieves tenant-specific credentials from the database and uses them
        to authenticate with Google Drive API.
        
        Returns:
            Google Drive API service instance
            
        Raises:
            Exception: If credentials are not found or authentication fails
        """
        try:
            # Import here to avoid circular dependencies
            from database import DatabaseManager
            from services.credential_service import CredentialService
            
            # Initialize database and credential service
            db = DatabaseManager()
            credential_service = CredentialService(db)
            
            # Retrieve credentials from database
            logger.info(f"Retrieving Google Drive credentials for administration: {self.administration}")
            
            # Get OAuth credentials (credentials.json content)
            oauth_creds = credential_service.get_credential(
                self.administration, 
                'google_drive_oauth'
            )
            
            if not oauth_creds:
                raise Exception(
                    f"Google Drive OAuth credentials not found for administration '{self.administration}'. "
                    "Please run the migration script to store credentials in the database."
                )
            
            # Get token (token.json content) if it exists
            token_data = credential_service.get_credential(
                self.administration,
                'google_drive_token'
            )
            
            creds = None
            
            # If we have a token, try to use it
            if token_data:
                try:
                    # Ensure token_data has client_id and client_secret from oauth_creds
                    if 'client_id' not in token_data and 'installed' in oauth_creds:
                        token_data['client_id'] = oauth_creds['installed']['client_id']
                        token_data['client_secret'] = oauth_creds['installed']['client_secret']
                    elif 'client_id' not in token_data and 'web' in oauth_creds:
                        token_data['client_id'] = oauth_creds['web']['client_id']
                        token_data['client_secret'] = oauth_creds['web']['client_secret']
                    
                    # Create Credentials object from token data
                    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                    logger.info(f"Loaded existing token for administration: {self.administration}")
                except Exception as e:
                    logger.warning(f"Failed to load token: {e}")
                    creds = None
            
            # Check if credentials are valid or need refresh
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    # Refresh the token
                    logger.info(f"Refreshing expired token for administration: {self.administration}")
                    try:
                        creds.refresh(Request())
                        
                        # Store the refreshed token back to database
                        token_info = json.loads(creds.to_json())
                        credential_service.store_credential(
                            self.administration,
                            'google_drive_token',
                            token_info
                        )
                        logger.info(f"✅ Refreshed token stored for administration: {self.administration}")
                    except Exception as refresh_error:
                        # Token refresh failed - likely the refresh token is invalid/expired
                        logger.error(f"❌ Token refresh failed for {self.administration}: {refresh_error}")
                        logger.error(f"⚠️  The refresh token may have expired or been revoked.")
                        
                        # Provide user-friendly error message
                        raise GoogleDriveAuthenticationError(
                            administration=self.administration,
                            error_type='refresh_token_expired',
                            message="Google Drive access has expired. Please contact your system administrator to renew access.",
                            admin_action="Run: python backend/refresh_google_token.py && python scripts/credentials/migrate_credentials_to_db.py --tenant {self.administration}"
                        )
                else:
                    # Need to do OAuth flow
                    logger.warning(f"⚠️  No valid token found for administration: {self.administration}")
                    
                    # Provide user-friendly error message
                    raise GoogleDriveAuthenticationError(
                        administration=self.administration,
                        error_type='no_token',
                        message="Google Drive is not configured. Please contact your system administrator to set up Google Drive access.",
                        admin_action=f"Run: python backend/refresh_google_token.py && python scripts/credentials/migrate_credentials_to_db.py --tenant {self.administration}"
                    )
            
            # Build and return the service
            service = build('drive', 'v3', credentials=creds)
            logger.info(f"Successfully authenticated Google Drive for administration: {self.administration}")
            return service
            
        except Exception as e:
            logger.error(f"Failed to authenticate Google Drive for administration '{self.administration}': {e}")
            raise
    
    def list_subfolders(self):
        # Use test or production folder based on TEST_MODE
        use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
        facturen_folder_id = os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test else os.getenv('FACTUREN_FOLDER_ID', '0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix')
        
        try:
            all_subfolders = []
            page_token = None
            
            while True:
                results = self.service.files().list(
                    q=f"'{facturen_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                    fields="nextPageToken, files(id, name, webViewLink)",
                    pageSize=1000,
                    pageToken=page_token
                ).execute()
                
                subfolders = results.get('files', [])
                
                for folder in subfolders:
                    all_subfolders.append({
                        'id': folder['id'],
                        'name': folder['name'],
                        'url': folder.get('webViewLink', '')
                    })
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            # Log if we found duplicate folder names (shouldn't happen but good to know)
            folder_names = [f['name'] for f in all_subfolders]
            if len(folder_names) != len(set(folder_names)):
                from collections import Counter
                duplicates = [name for name, count in Counter(folder_names).items() if count > 1]
                print(f"WARNING: Found duplicate folder names in Facturen folder: {duplicates}")
                print(f"Folder details: {[f for f in all_subfolders if f['name'] in duplicates]}")
            
            return sorted(all_subfolders, key=lambda x: x['name'].lower())
        except Exception as e:
            print(f"Could not access Facturen folder: {e}")
            return []
    
    def upload_file(self, file_path, filename, folder_id):
        media = MediaFileUpload(file_path, resumable=True)
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink'
        ).execute()
        
        return {
            'id': file['id'],
            'url': file['webViewLink']
        }
    
    def upload_text_file(self, content, filename, folder_id, mime_type='text/html'):
        """Upload text content directly to Google Drive"""
        from googleapiclient.http import MediaIoBaseUpload
        import io
        
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode('utf-8')),
            mimetype=mime_type,
            resumable=True
        )
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink'
        ).execute()
        
        return {
            'id': file['id'],
            'url': file['webViewLink']
        }
    
    def check_file_exists(self, filename, folder_id):
        """Check if file already exists in the folder"""
        try:
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and name='{filename}' and trashed=false",
                fields="files(id, name, webViewLink)"
            ).execute()
            
            files = results.get('files', [])
            if files:
                return {
                    'exists': True,
                    'file': {
                        'id': files[0]['id'],
                        'name': files[0]['name'],
                        'url': files[0].get('webViewLink', '')
                    }
                }
            return {'exists': False}
        except Exception as e:
            print(f"Error checking file existence: {e}")
            return {'exists': False}
    
    def download_file_content(self, file_id):
        """
        Download file content from Google Drive by file ID
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            str: File content as string
        """
        try:
            from googleapiclient.http import MediaIoBaseDownload
            import io
            
            request = self.service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            # Get content as string
            file_buffer.seek(0)
            content = file_buffer.read().decode('utf-8')
            
            return content
            
        except Exception as e:
            print(f"Error downloading file content: {e}", flush=True)
            raise Exception(f"Failed to download file from Google Drive: {str(e)}")
    
    def create_folder(self, folder_name, parent_id):
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        
        folder = self.service.files().create(
            body=file_metadata,
            fields='id,name,webViewLink'
        ).execute()
        
        return {
            'id': folder['id'],
            'name': folder['name'],
            'url': folder.get('webViewLink', '')
        }