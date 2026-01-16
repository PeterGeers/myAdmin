"""
Upload found invoices to Google Drive and generate result file with URLs
Uploads to Facturen folder, organized by ReferenceNumber subfolder
"""

import csv
import os
import sys
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))
from google_drive_service import GoogleDriveService

load_dotenv()

# Configuration
FOUND_INVOICES_CSV = 'found_invoices.csv'
OUTPUT_CSV = 'uploaded_invoices_with_urls.csv'
GDRIVE_FACTUREN_FOLDER_ID = os.getenv('FACTUREN_FOLDER_ID')

def find_or_create_folder(gdrive, folder_name, parent_id):
    """Find or create folder in Google Drive"""
    query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = gdrive.service.files().list(q=query, fields='files(id)').execute()
    folders = results.get('files', [])
    
    if folders:
        return folders[0]['id']
    
    result = gdrive.create_folder(folder_name, parent_id)
    return result['id']

def upload_to_gdrive(gdrive, file_path, folder_id, filename):
    """Upload file to Google Drive and return shareable URL"""
    result = gdrive.upload_file(file_path, filename, folder_id)
    
    # Make shareable
    gdrive.service.permissions().create(
        fileId=result['id'],
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return result['url']

def main():
    print("Starting upload process...")
    print(f"Google Drive Facturen Folder ID: {GDRIVE_FACTUREN_FOLDER_ID}")
    print()
    
    # Initialize Google Drive
    print("Connecting to Google Drive...")
    gdrive = GoogleDriveService()
    
    # Load found invoices
    with open(FOUND_INVOICES_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        records = list(reader)
    
    print(f"Total records: {len(records)}")
    print()
    
    # Group by unique file
    files_to_process = defaultdict(list)
    for record in records:
        key = (record['Ref4'], record['OneDrivePath'], record['ReferenceNumber'])
        files_to_process[key].append(record)
    
    print(f"Unique files to upload: {len(files_to_process)}")
    print()
    
    # Process and collect results
    results = []
    success = 0
    errors = 0
    
    for idx, ((ref4, onedrive_path, reference_number), record_list) in enumerate(files_to_process.items(), 1):
        print(f"[{idx}/{len(files_to_process)}] {ref4}")
        print(f"  Reference: {reference_number}")
        
        try:
            if not os.path.exists(onedrive_path):
                print(f"  ERROR: File not found")
                errors += 1
                continue
            
            # Find/create folder
            folder_id = find_or_create_folder(gdrive, reference_number, GDRIVE_FACTUREN_FOLDER_ID)
            
            # Upload
            print(f"  Uploading...")
            new_url = upload_to_gdrive(gdrive, onedrive_path, folder_id, ref4)
            print(f"  DONE: {new_url}")
            
            # Add to results for all records with this file
            for record in record_list:
                results.append({
                    'ID': record['ID'],
                    'Date': record['Date'],
                    'ReferenceNumber': reference_number,
                    'Ref4': ref4,
                    'OneDrivePath': onedrive_path,
                    'GoogleDriveURL': new_url
                })
            
            success += 1
            print()
            
        except Exception as e:
            print(f"  ERROR: {str(e)}")
            errors += 1
            print()
    
    # Write results
    print("Writing results...")
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['ID', 'Date', 'ReferenceNumber', 'Ref4', 'OneDrivePath', 'GoogleDriveURL'])
        writer.writeheader()
        writer.writerows(results)
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Successfully uploaded: {success} files")
    print(f"Errors: {errors} files")
    print(f"Total records with URLs: {len(results)}")
    print(f"Output saved to: {OUTPUT_CSV}")
    print("=" * 60)

if __name__ == '__main__':
    main()
