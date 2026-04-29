"""
Check field_mappings configuration for both English and Dutch templates
"""
import os
import sys
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager
from services.template_service import TemplateService

def check_field_mappings():
    """Check field_mappings for both languages"""
    
    db = DatabaseManager(test_mode=False)
    template_service = TemplateService(db)
    
    administration = 'GoodwinSolutions'
    
    for language in ['en', 'nl']:
        template_type = f'str_invoice_{language}'
        
        print(f"\n{'='*80}")
        print(f"FIELD MAPPINGS FOR: {template_type}")
        print(f"{'='*80}")
        
        try:
            metadata = template_service.get_template_metadata(administration, template_type)
            
            if metadata:
                field_mappings = metadata.get('field_mappings')
                
                if field_mappings:
                    print(f"\n✅ Field mappings found in database")
                    print(f"\nField mappings structure:")
                    print(json.dumps(field_mappings, indent=2))
                else:
                    print(f"\n❌ No field_mappings in metadata (will use defaults)")
            else:
                print(f"\n❌ No metadata found")
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    check_field_mappings()
