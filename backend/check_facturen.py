from google_drive_service import GoogleDriveService

def find_facturen_folder():
    drive = GoogleDriveService()
    
    # Search for "Facturen" folder
    results = drive.service.files().list(
        q="name='Facturen' and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name, webViewLink)"
    ).execute()
    
    print("=== Looking for Facturen folder ===")
    if results['files']:
        for folder in results['files']:
            print(f"Found: {folder['name']} (ID: {folder['id']})")
            print(f"URL: {folder.get('webViewLink', 'No URL')}")
    else:
        print("No 'Facturen' folder found")
        print("Current parent folder is 'zwembad' (ID: 1UlSJbRkvp3g-k66D5BNQAHqj1mYr1Xu3)")

if __name__ == "__main__":
    find_facturen_folder()