#!/usr/bin/env python3
"""
Upload STR invoice templates to Google Drive
"""

import os
import sys
from src.google_drive_service import GoogleDriveService

def upload_templates():
    """Upload HTML templates to Google Drive templates folder"""
    try:
        # Initialize Google Drive service
        drive_service = GoogleDriveService()
        
        # Target folder ID from the requirement
        template_folder_id = "12FJAYbX5MI3wpGxwahcHykRQfUCRZob1"
        
        print(f"Target folder: https://drive.google.com/drive/folders/{template_folder_id}")
        
        # Templates to upload
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        templates = [
            'str_invoice_nl.html',
            'str_invoice_en.html'
        ]
        
        results = []
        
        for template_name in templates:
            template_path = os.path.join(templates_dir, template_name)
            
            if not os.path.exists(template_path):
                print(f"Template not found: {template_path}")
                results.append({'template': template_name, 'status': 'not_found'})
                continue
            
            try:
                # Check if file already exists
                existing_file = drive_service.check_file_exists(template_name, template_folder_id)
                
                if existing_file['exists']:
                    print(f"Template already exists: {template_name}")
                    print(f"   URL: {existing_file['file']['url']}")
                    results.append({
                        'template': template_name, 
                        'status': 'already_exists',
                        'url': existing_file['file']['url']
                    })
                else:
                    # Read template content and upload as text
                    print(f"Uploading template: {template_name}")
                    with open(template_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    upload_result = drive_service.upload_text_file(
                        content, template_name, template_folder_id, 'text/html'
                    )
                    print(f"   Uploaded successfully")
                    print(f"   URL: {upload_result['url']}")
                    results.append({
                        'template': template_name,
                        'status': 'uploaded',
                        'url': upload_result['url']
                    })
                
            except Exception as e:
                print(f"Error uploading {template_name}: {e}")
                import traceback
                traceback.print_exc()
                results.append({'template': template_name, 'status': 'error', 'error': str(e)})
        
        # Summary
        print(f"\nUpload Summary:")
        print(f"   Total templates: {len(templates)}")
        uploaded = len([r for r in results if r['status'] == 'uploaded'])
        existing = len([r for r in results if r['status'] == 'already_exists'])
        errors = len([r for r in results if r['status'] == 'error'])
        
        print(f"   Uploaded: {uploaded}")
        print(f"   Already exists: {existing}")
        print(f"   Errors: {errors}")
        
        if errors == 0:
            print(f"\nAll templates are now available in Google Drive!")
            print(f"   Folder: https://drive.google.com/drive/folders/{template_folder_id}")
            print(f"   View templates in browser to verify upload")
        
        return results
        
    except Exception as e:
        print(f"Failed to upload templates: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    print("Uploading STR Invoice Templates to Google Drive...")
    print("=" * 50)
    
    results = upload_templates()
    
    if not results:
        sys.exit(1)
    
    print("\nUpload process completed!")