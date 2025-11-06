from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaFileUpload
import os
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveService:
    def __init__(self):
        self.service = self._authenticate()
    
    def _authenticate(self):
        # Get backend directory path
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        credentials_path = os.path.join(backend_dir, 'credentials.json')
        token_path = os.path.join(backend_dir, 'token.json')
        
        print(f"Looking for credentials at: {credentials_path}")
        print(f"Credentials file exists: {os.path.exists(credentials_path)}")
        print(f"Token path: {token_path}")
        print(f"Token file exists: {os.path.exists(token_path)}")
        
        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        
        return build('drive', 'v3', credentials=creds)
    
    def list_subfolders(self):
        # Use test or production folder based on TEST_MODE
        use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
        facturen_folder_id = os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test else os.getenv('FACTUREN_FOLDER_ID', '0B9OBNkcEDqv1YWQzZDkyM2YtMTE4Yy00ODUzLWIzZmEtMTQ1NzEzMDQ1N2Ix')
        
        try:
            all_subfolders = []
            page_token = None
            
            while True:
                results = self.service.files().list(
                    q=f"'{facturen_folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
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