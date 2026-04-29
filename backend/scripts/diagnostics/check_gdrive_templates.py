"""
Check and compare STR invoice templates on Google Drive
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager
from services.template_service import TemplateService

def check_templates():
    """Check what templates are stored on Google Drive"""
    
    # Initialize
    db = DatabaseManager(test_mode=False)
    template_service = TemplateService(db)
    
    administration = 'GoodwinSolutions'
    
    print("=" * 80)
    print("CHECKING STR INVOICE TEMPLATES ON GOOGLE DRIVE")
    print("=" * 80)
    
    for language in ['en', 'nl']:
        template_type = f'str_invoice_{language}'
        
        print(f"\n{'='*80}")
        print(f"Template Type: {template_type}")
        print(f"{'='*80}")
        
        try:
            # Get metadata from database
            metadata = template_service.get_template_metadata(administration, template_type)
            
            if metadata:
                print(f"\n✅ Metadata found in database:")
                print(f"   File ID: {metadata.get('template_file_id')}")
                print(f"   Active: {metadata.get('is_active')}")
                
                # Fetch template content from Google Drive
                file_id = metadata.get('template_file_id')
                if file_id:
                    try:
                        content = template_service.fetch_template_from_drive(file_id, administration)
                        
                        print(f"\n✅ Template fetched from Google Drive:")
                        print(f"   Content length: {len(content)} characters")
                        print(f"   First 500 characters:")
                        print("-" * 80)
                        print(content[:500])
                        print("-" * 80)
                        
                        # Check for key placeholders
                        placeholders = [
                            '{{ table_rows }}',
                            '{{ company_name }}',
                            '{{ reservationCode }}',
                            '{{ amountGross }}'
                        ]
                        
                        print(f"\n   Placeholder check:")
                        for placeholder in placeholders:
                            found = placeholder in content
                            status = "✅" if found else "❌"
                            print(f"   {status} {placeholder}: {'Found' if found else 'NOT FOUND'}")
                        
                        # Check for Jinja2 syntax (should NOT be present)
                        jinja_patterns = [
                            '{% if',
                            '{{ "%.2f"|format(',
                            '{% endif %}'
                        ]
                        
                        print(f"\n   Jinja2 syntax check (should be ABSENT):")
                        for pattern in jinja_patterns:
                            found = pattern in content
                            status = "❌" if found else "✅"
                            print(f"   {status} {pattern}: {'FOUND (BAD!)' if found else 'Not found (good)'}")
                        
                        # Save to file for inspection
                        output_file = f'gdrive_template_{language}.html'
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"\n   💾 Saved to: {output_file}")
                        
                    except Exception as e:
                        print(f"\n❌ Error fetching template from Google Drive: {e}")
                else:
                    print(f"\n❌ No file ID in metadata")
            else:
                print(f"\n❌ No metadata found in database")
                print(f"   Template not configured for {administration}")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}")
    print("DONE")
    print(f"{'='*80}")

if __name__ == '__main__':
    check_templates()
