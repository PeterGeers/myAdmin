#!/usr/bin/env python3
"""
Force upload updated STR invoice templates to Google Drive
"""

import os
import sys
from src.google_drive_service import GoogleDriveService

def force_upload_templates():
    """Force upload HTML templates, replacing existing ones"""
    try:
        drive_service = GoogleDriveService()
        template_folder_id = "12FJAYbX5MI3wpGxwahcHykRQfUCRZob1"
        
        templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
        templates = ['str_invoice_nl.html', 'str_invoice_en.html']
        
        results = []
        
        for template_name in templates:
            template_path = os.path.join(templates_dir, template_name)
            
            if not os.path.exists(template_path):
                print(f"Template not found: {template_path}")
                continue
            
            try:
                # Check if file exists and delete it
                existing_file = drive_service.check_file_exists(template_name, template_folder_id)
                
                if existing_file['exists']:
                    print(f"Deleting existing template: {template_name}")
                    drive_service.service.files().delete(fileId=existing_file['file']['id']).execute()
                
                # Upload new version
                print(f"Uploading updated template: {template_name}")
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                upload_result = drive_service.upload_text_file(
                    content, template_name, template_folder_id, 'text/html'
                )
                
                print(f"   Uploaded successfully")
                print(f"   URL: {upload_result['url']}")
                results.append({
                    'template': template_name,
                    'status': 'replaced',
                    'url': upload_result['url']
                })
                
            except Exception as e:
                print(f"Error with {template_name}: {e}")
                results.append({'template': template_name, 'status': 'error', 'error': str(e)})
        
        print(f"\nForce upload completed!")
        print(f"Templates with fixed logo URLs are now in Google Drive")
        
        return results
        
    except Exception as e:
        print(f"Failed to force upload templates: {e}")
        return []

if __name__ == "__main__":
    print("Force Uploading Updated STR Invoice Templates...")
    print("=" * 50)
    
    results = force_upload_templates()
    
    if results:
        print("\nTemplates updated with working logo URLs!")
    else:
        sys.exit(1)