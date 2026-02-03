"""
Debug which template is being loaded for Dutch invoice generation
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager
from services.template_service import TemplateService

def debug_template_loading():
    """Check which template would be loaded for Dutch invoice"""
    
    db = DatabaseManager(test_mode=False)
    template_service = TemplateService(db)
    
    administration = 'GoodwinSolutions'
    language = 'nl'
    template_type = f'str_invoice_{language}'
    
    print("=" * 80)
    print(f"DEBUGGING TEMPLATE LOADING FOR: {template_type}")
    print("=" * 80)
    
    # Step 1: Check database metadata
    print("\n1. Checking database metadata...")
    try:
        metadata = template_service.get_template_metadata(administration, template_type)
        if metadata:
            print(f"   ✅ Found metadata in database")
            print(f"   File ID: {metadata.get('template_file_id')}")
            print(f"   Active: {metadata.get('is_active')}")
            
            # Step 2: Try to fetch from Google Drive
            print("\n2. Fetching from Google Drive...")
            file_id = metadata.get('template_file_id')
            if file_id:
                try:
                    content = template_service.fetch_template_from_drive(file_id, administration)
                    print(f"   ✅ Successfully fetched from Google Drive")
                    print(f"   Content length: {len(content)} characters")
                    
                    # Check key placeholders
                    print("\n3. Checking placeholders in fetched template:")
                    placeholders = ['{{ table_rows }}', '{{ company_name }}', '{{ reservationCode }}']
                    for p in placeholders:
                        found = p in content
                        print(f"   {'✅' if found else '❌'} {p}: {'Found' if found else 'NOT FOUND'}")
                    
                    return content
                    
                except Exception as e:
                    print(f"   ❌ Error fetching from Google Drive: {e}")
                    print(f"   Will fall back to filesystem")
        else:
            print(f"   ❌ No metadata found in database")
            
    except Exception as e:
        print(f"   ❌ Error checking metadata: {e}")
    
    # Step 3: Fallback to filesystem
    print("\n4. Checking filesystem fallback...")
    template_file = f'str_invoice_{language}_template.html'
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'html', template_file)
    
    print(f"   Looking for: {template_path}")
    
    if os.path.exists(template_path):
        print(f"   ✅ File exists on filesystem")
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"   Content length: {len(content)} characters")
        
        # Check key placeholders
        print("\n5. Checking placeholders in filesystem template:")
        placeholders = ['{{ table_rows }}', '{{ company_name }}', '{{ reservationCode }}']
        for p in placeholders:
            found = p in content
            print(f"   {'✅' if found else '❌'} {p}: {'Found' if found else 'NOT FOUND'}")
        
        return content
    else:
        print(f"   ❌ File does NOT exist on filesystem")
        print(f"   This would cause an error!")
    
    return None

if __name__ == '__main__':
    content = debug_template_loading()
    
    if content:
        print("\n" + "=" * 80)
        print("TEMPLATE WOULD BE LOADED SUCCESSFULLY")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ NO TEMPLATE FOUND - THIS IS THE PROBLEM!")
        print("=" * 80)
