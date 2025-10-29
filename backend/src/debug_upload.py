from google_drive_service import GoogleDriveService
from pdf_processor import PDFProcessor

def debug_upload():
    try:
        # Test folder creation
        drive = GoogleDriveService()
        print("=== Testing folder creation ===")
        
        # Check if Test folder exists
        parent_id = '1UlSJbRkvp3g-k66D5BNQAHqj1mYr1Xu3'  # zwembad folder
        results = drive.service.files().list(
            q=f"'{parent_id}' in parents and name='Test' and mimeType='application/vnd.google-apps.folder'",
            fields="files(id, name, webViewLink)"
        ).execute()
        
        if results['files']:
            test_folder = results['files'][0]
            print(f"Test folder found: {test_folder['name']} (ID: {test_folder['id']})")
            print(f"URL: {test_folder.get('webViewLink', 'No URL')}")
        else:
            print("Test folder not found")
        
        # Test PDF processing
        print("\n=== Testing PDF processor ===")
        pdf_processor = PDFProcessor()
        print("PDF processor initialized")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_upload()