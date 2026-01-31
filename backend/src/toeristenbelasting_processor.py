from database import DatabaseManager
from mutaties_cache import get_cache
from bnb_cache import get_bnb_cache
from report_generators import toeristenbelasting_generator
from services.template_service import TemplateService
import os
import logging

logger = logging.getLogger(__name__)

class ToeristenbelastingProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
    
    def generate_toeristenbelasting_report(self, year):
        """Generate Toeristenbelasting (Tourist Tax) declaration report using TemplateService"""
        try:
            # Get caches
            cache = get_cache()
            bnb_cache = get_bnb_cache()
            
            # Generate report data using the generator
            report_result = toeristenbelasting_generator.generate_toeristenbelasting_report(
                cache=cache,
                bnb_cache=bnb_cache,
                db=self.db,
                year=year
            )
            
            if not report_result.get('success'):
                return {
                    'success': False,
                    'error': report_result.get('error', 'Unknown error')
                }
            
            # Get template data
            template_data = report_result['template_data']
            raw_data = report_result['raw_data']
            
            # Initialize TemplateService
            template_service = TemplateService(self.db)
            
            # Try to get template metadata from database
            # Note: Toeristenbelasting is typically tenant-specific
            # For now, we'll use a default administration or get it from raw_data
            administration = raw_data.get('administration', 'GoodwinSolutions')
            template_type = 'toeristenbelasting_html'
            metadata = None
            
            try:
                metadata = template_service.get_template_metadata(administration, template_type)
            except Exception as e:
                logger.warning(f"Could not get template metadata from database: {e}")
            
            # Load template
            if metadata and metadata.get('template_file_id'):
                # Load from Google Drive
                try:
                    template_content = template_service.fetch_template_from_drive(
                        metadata['template_file_id'],
                        administration
                    )
                    field_mappings = metadata.get('field_mappings', {})
                except Exception as e:
                    logger.error(f"Failed to fetch template from Google Drive: {e}")
                    # Fallback to filesystem
                    metadata = None
            
            if not metadata:
                # Fallback: Load from filesystem
                template_path = os.path.join(
                    os.path.dirname(__file__),
                    '..',
                    'templates',
                    'html',
                    'toeristenbelasting_template.html'
                )
                
                if not os.path.exists(template_path):
                    logger.error(f"Template not found: {template_path}")
                    return {'success': False, 'error': 'Template not found'}
                
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_content = f.read()
                
                # Use default field mappings (simple placeholder replacement)
                field_mappings = {
                    'fields': {key: {'path': key, 'format': 'text'} for key in template_data.keys()},
                    'formatting': {
                        'locale': 'nl_NL',
                        'currency': 'EUR',
                        'date_format': 'DD-MM-YYYY',
                        'number_decimals': 2
                    }
                }
            
            # Apply field mappings using TemplateService
            html_report = template_service.apply_field_mappings(
                template_content,
                template_data,
                field_mappings
            )
            
            return {
                'success': True,
                'html_report': html_report,
                'data': raw_data
            }
            
        except Exception as e:
            print(f"Error generating toeristenbelasting report: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
