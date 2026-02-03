"""
Template Service for Railway Migration
Handles template metadata retrieval, template fetching from Google Drive,
field mapping application, and output generation.

This service provides template management for multi-tenant applications,
supporting XML templates with flexible field mappings stored in the database.
"""

import os
import json
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List
from datetime import datetime
from io import BytesIO

logger = logging.getLogger(__name__)


class TemplateService:
    """
    Service for managing templates and field mappings.
    
    Supports template metadata retrieval, template fetching from storage,
    field mapping application, and output generation in multiple formats.
    """
    
    def __init__(self, db_manager):
        """
        Initialize the template service.
        
        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager
        logger.info("TemplateService initialized successfully")
    
    def get_template_metadata(self, administration: str, template_type: str) -> Optional[Dict[str, Any]]:
        """
        Get template metadata including field mappings from database.
        
        Args:
            administration: The tenant/administration identifier
            template_type: Type of template (e.g., 'str_invoice', 'btw_aangifte')
            
        Returns:
            Dictionary containing template metadata:
            {
                'template_file_id': str,
                'field_mappings': dict,
                'is_active': bool,
                'created_at': str,
                'updated_at': str
            }
            Returns None if template not found or not active.
            
        Raises:
            Exception: If database query fails
        """
        try:
            query = """
                SELECT template_file_id, field_mappings, is_active, created_at, updated_at
                FROM tenant_template_config
                WHERE administration = %s AND template_type = %s AND is_active = TRUE
                LIMIT 1
            """
            
            results = self.db.execute_query(query, (administration, template_type))
            
            if not results or len(results) == 0:
                logger.warning(
                    f"No active template found for administration '{administration}', "
                    f"type '{template_type}'"
                )
                return None
            
            result = results[0]
            
            # Parse field_mappings JSON
            field_mappings = {}
            if result.get('field_mappings'):
                try:
                    if isinstance(result['field_mappings'], str):
                        field_mappings = json.loads(result['field_mappings'])
                    else:
                        field_mappings = result['field_mappings']
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse field_mappings JSON: {e}")
                    field_mappings = {}
            
            metadata = {
                'template_file_id': result['template_file_id'],
                'field_mappings': field_mappings,
                'is_active': result['is_active'],
                'created_at': result['created_at'].isoformat() if result.get('created_at') else None,
                'updated_at': result['updated_at'].isoformat() if result.get('updated_at') else None
            }
            
            logger.info(
                f"Retrieved template metadata for administration '{administration}', "
                f"type '{template_type}'"
            )
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get template metadata: {e}")
            raise Exception(f"Failed to retrieve template metadata: {str(e)}")
    
    def fetch_template_from_drive(self, file_id: str, administration: str) -> str:
        """
        Fetch XML template content from Google Drive.
        
        Args:
            file_id: Google Drive file ID
            administration: The tenant/administration identifier (for authentication)
            
        Returns:
            Template content as string (XML)
            
        Raises:
            Exception: If template fetch fails
        """
        try:
            # Import here to avoid circular dependencies
            from google_drive_service import GoogleDriveService
            
            # Initialize Google Drive service for this tenant
            drive_service = GoogleDriveService(administration)
            
            # Fetch file content from Google Drive
            logger.info(f"Fetching template file_id '{file_id}' for administration '{administration}'")
            
            request = drive_service.service.files().get_media(fileId=file_id)
            
            # Download file content
            file_content = BytesIO()
            from googleapiclient.http import MediaIoBaseDownload
            
            downloader = MediaIoBaseDownload(file_content, request)
            done = False
            
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")
            
            # Get content as string
            template_content = file_content.getvalue().decode('utf-8')
            
            logger.info(
                f"Successfully fetched template file_id '{file_id}' "
                f"for administration '{administration}'"
            )
            
            return template_content
            
        except Exception as e:
            logger.error(f"Failed to fetch template from Google Drive: {e}")
            raise Exception(f"Failed to fetch template: {str(e)}")
    
    def apply_field_mappings(
        self, 
        template_xml: str, 
        data: Dict[str, Any], 
        mappings: Dict[str, Any]
    ) -> str:
        """
        Apply field mappings to template XML.
        
        Replaces template placeholders with actual data values according to
        field mappings configuration. Supports formatting, transformations,
        and conditional logic.
        
        Args:
            template_xml: Template content as XML string
            data: Data dictionary containing values to map
            mappings: Field mappings configuration (from database)
            
        Returns:
            Template with field mappings applied as string
            
        Raises:
            Exception: If field mapping application fails
        """
        try:
            fields = mappings.get('fields', {})
            conditionals = mappings.get('conditionals', [])
            formatting = mappings.get('formatting', {})
            
            result_template = template_xml
            
            # Apply field mappings
            for field_name, field_config in fields.items():
                try:
                    # Get field value from data
                    value = self._get_field_value(data, field_config)
                    
                    # Format the value
                    formatted_value = self._format_value(value, field_config, formatting)
                    
                    # Replace placeholder in template
                    placeholder = f"{{{{ {field_name} }}}}"
                    result_template = result_template.replace(placeholder, str(formatted_value))
                    
                except Exception as e:
                    logger.warning(f"Failed to apply field mapping for '{field_name}': {e}")
                    # Use default value if specified
                    default_value = field_config.get('default', '')
                    placeholder = f"{{{{ {field_name} }}}}"
                    result_template = result_template.replace(placeholder, str(default_value))
            
            # Apply conditionals
            for conditional in conditionals:
                try:
                    result_template = self._apply_conditional(
                        result_template, 
                        data, 
                        conditional, 
                        fields
                    )
                except Exception as e:
                    logger.warning(f"Failed to apply conditional: {e}")
            
            logger.info("Successfully applied field mappings to template")
            
            return result_template
            
        except Exception as e:
            logger.error(f"Failed to apply field mappings: {e}")
            raise Exception(f"Failed to apply field mappings: {str(e)}")

    
    def generate_output(
        self, 
        template: str, 
        data: Dict[str, Any], 
        output_format: str
    ) -> Any:
        """
        Generate output in specified format from template and data.
        
        Supports multiple output formats: HTML, XML, Excel, PDF.
        
        Args:
            template: Template content (with field mappings already applied)
            data: Data dictionary (may be used for additional processing)
            output_format: Output format ('html', 'xml', 'excel', 'pdf')
            
        Returns:
            Generated output (format depends on output_format):
            - 'html': HTML string
            - 'xml': XML string
            - 'excel': BytesIO object containing Excel file
            - 'pdf': BytesIO object containing PDF file
            
        Raises:
            Exception: If output generation fails
        """
        try:
            output_format = output_format.lower()
            
            if output_format == 'html':
                return self._generate_html(template, data)
            elif output_format == 'xml':
                return self._generate_xml(template, data)
            elif output_format == 'excel':
                return self._generate_excel(template, data)
            elif output_format == 'pdf':
                return self._generate_pdf(template, data)
            else:
                raise ValueError(f"Unsupported output format: {output_format}")
            
        except Exception as e:
            logger.error(f"Failed to generate output: {e}")
            raise Exception(f"Failed to generate output: {str(e)}")
    
    # Helper methods
    
    def _get_field_value(self, data: Dict[str, Any], field_config: Dict[str, Any]) -> Any:
        """
        Get field value from data using path from field config.
        
        Args:
            data: Data dictionary
            field_config: Field configuration with 'path' and 'default'
            
        Returns:
            Field value or default if not found
        """
        path = field_config.get('path', '')
        default = field_config.get('default')
        
        # Navigate through nested dictionary using dot notation
        keys = path.split('.')
        value = data
        
        try:
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    value = None
                    break
                
                if value is None:
                    break
            
            # Return default if value is None
            if value is None:
                return default
            
            return value
            
        except Exception as e:
            logger.warning(f"Failed to get field value for path '{path}': {e}")
            return default
    
    def _format_value(
        self, 
        value: Any, 
        field_config: Dict[str, Any], 
        global_formatting: Dict[str, Any]
    ) -> str:
        """
        Format value according to field config and global formatting rules.
        
        Args:
            value: Value to format
            field_config: Field configuration with 'format' and 'transform'
            global_formatting: Global formatting rules
            
        Returns:
            Formatted value as string
        """
        if value is None:
            return ''
        
        # Apply transformation first
        transform = field_config.get('transform')
        if transform:
            value = self._apply_transform(value, transform)
        
        # Apply formatting
        format_type = field_config.get('format', 'text')
        
        if format_type == 'currency':
            return self._format_currency(value, global_formatting)
        elif format_type == 'date':
            return self._format_date(value, global_formatting)
        elif format_type == 'number':
            return self._format_number(value, global_formatting)
        elif format_type == 'text':
            return str(value)
        elif format_type == 'table':
            # Tables are handled separately in output generation
            return str(value)
        else:
            return str(value)
    
    def _apply_transform(self, value: Any, transform: str) -> Any:
        """
        Apply transformation function to value.
        
        Args:
            value: Value to transform
            transform: Transformation type ('abs', 'round', 'uppercase', 'lowercase')
            
        Returns:
            Transformed value
        """
        try:
            if transform == 'abs':
                return abs(float(value))
            elif transform == 'round':
                return round(float(value), 2)
            elif transform == 'uppercase':
                return str(value).upper()
            elif transform == 'lowercase':
                return str(value).lower()
            else:
                return value
        except Exception as e:
            logger.warning(f"Failed to apply transform '{transform}': {e}")
            return value
    
    def _format_currency(self, value: Any, formatting: Dict[str, Any]) -> str:
        """
        Format value as currency.
        
        Args:
            value: Numeric value
            formatting: Global formatting rules with 'currency' and 'locale'
            
        Returns:
            Formatted currency string
        """
        try:
            currency = formatting.get('currency', 'EUR')
            decimals = formatting.get('number_decimals', 2)
            
            # Convert to float
            numeric_value = float(value)
            
            # Format with decimals
            formatted = f"{numeric_value:,.{decimals}f}"
            
            # Add currency symbol
            if currency == 'EUR':
                return f"€ {formatted}"
            elif currency == 'USD':
                return f"$ {formatted}"
            elif currency == 'GBP':
                return f"£ {formatted}"
            else:
                return f"{currency} {formatted}"
                
        except Exception as e:
            logger.warning(f"Failed to format currency: {e}")
            return str(value)
    
    def _format_date(self, value: Any, formatting: Dict[str, Any]) -> str:
        """
        Format value as date.
        
        Args:
            value: Date value (string or datetime object)
            formatting: Global formatting rules with 'date_format'
            
        Returns:
            Formatted date string
        """
        try:
            date_format = formatting.get('date_format', 'DD-MM-YYYY')
            
            # Convert to datetime if string
            if isinstance(value, str):
                # Try common date formats
                for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%Y/%m/%d']:
                    try:
                        date_obj = datetime.strptime(value, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    # If no format matches, return as-is
                    return value
            elif isinstance(value, datetime):
                date_obj = value
            else:
                return str(value)
            
            # Format according to date_format
            if date_format == 'DD-MM-YYYY':
                return date_obj.strftime('%d-%m-%Y')
            elif date_format == 'YYYY-MM-DD':
                return date_obj.strftime('%Y-%m-%d')
            elif date_format == 'MM/DD/YYYY':
                return date_obj.strftime('%m/%d/%Y')
            else:
                return date_obj.strftime('%d-%m-%Y')
                
        except Exception as e:
            logger.warning(f"Failed to format date: {e}")
            return str(value)
    
    def _format_number(self, value: Any, formatting: Dict[str, Any]) -> str:
        """
        Format value as number.
        
        Args:
            value: Numeric value
            formatting: Global formatting rules with 'number_decimals'
            
        Returns:
            Formatted number string
        """
        try:
            numeric_value = float(value)
            
            # Check if it's a whole number (integer)
            if numeric_value == int(numeric_value):
                # Format as integer without decimals
                return str(int(numeric_value))
            else:
                # Format with decimals
                decimals = formatting.get('number_decimals', 2)
                return f"{numeric_value:,.{decimals}f}"
        except Exception as e:
            logger.warning(f"Failed to format number: {e}")
            return str(value)
    
    def _apply_conditional(
        self, 
        template: str, 
        data: Dict[str, Any], 
        conditional: Dict[str, Any],
        fields: Dict[str, Any]
    ) -> str:
        """
        Apply conditional logic to template.
        
        Args:
            template: Template content
            data: Data dictionary
            conditional: Conditional configuration
            fields: Field mappings
            
        Returns:
            Template with conditional applied
        """
        try:
            field_name = conditional.get('field')
            operator = conditional.get('operator')
            compare_value = conditional.get('value')
            action = conditional.get('action')
            
            # Get field config and value
            field_config = fields.get(field_name, {})
            field_value = self._get_field_value(data, field_config)
            
            # Evaluate condition
            condition_met = self._evaluate_condition(field_value, operator, compare_value)
            
            # Apply action based on condition
            if action == 'show' and not condition_met:
                # Hide the section (implementation depends on template structure)
                # For now, we'll just log it
                logger.debug(f"Conditional 'show' not met for field '{field_name}'")
            elif action == 'hide' and condition_met:
                # Hide the section
                logger.debug(f"Conditional 'hide' met for field '{field_name}'")
            
            return template
            
        except Exception as e:
            logger.warning(f"Failed to apply conditional: {e}")
            return template
    
    def _evaluate_condition(self, value: Any, operator: str, compare_value: Any) -> bool:
        """
        Evaluate conditional expression.
        
        Args:
            value: Field value
            operator: Comparison operator
            compare_value: Value to compare against
            
        Returns:
            True if condition is met, False otherwise
        """
        try:
            if operator == 'eq':
                return value == compare_value
            elif operator == 'ne':
                return value != compare_value
            elif operator == 'gt':
                return float(value) > float(compare_value)
            elif operator == 'lt':
                return float(value) < float(compare_value)
            elif operator == 'gte':
                return float(value) >= float(compare_value)
            elif operator == 'lte':
                return float(value) <= float(compare_value)
            elif operator == 'contains':
                return str(compare_value) in str(value)
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False
        except Exception as e:
            logger.warning(f"Failed to evaluate condition: {e}")
            return False
    
    # Output generation methods
    
    def _generate_html(self, template: str, data: Dict[str, Any]) -> str:
        """
        Generate HTML output from template.
        
        Args:
            template: Template content (already processed)
            data: Data dictionary
            
        Returns:
            HTML string
        """
        # Template is already processed with field mappings
        # Just return as HTML
        return template
    
    def _generate_xml(self, template: str, data: Dict[str, Any]) -> str:
        """
        Generate XML output from template.
        
        Args:
            template: Template content (already processed)
            data: Data dictionary
            
        Returns:
            XML string
        """
        # Template is already processed with field mappings
        # Validate and return as XML
        try:
            # Validate XML
            ET.fromstring(template)
            return template
        except ET.ParseError as e:
            logger.warning(f"XML validation failed: {e}")
            # Return anyway, might be partial XML
            return template
    
    def _generate_excel(self, template: str, data: Dict[str, Any]) -> BytesIO:
        """
        Generate Excel output from template.
        
        Args:
            template: Template content (already processed)
            data: Data dictionary
            
        Returns:
            BytesIO object containing Excel file
        """
        # This is a placeholder - actual implementation would use openpyxl or xlsxwriter
        # to generate Excel files from template data
        logger.warning("Excel generation not yet implemented")
        raise NotImplementedError("Excel generation not yet implemented")
    
    def _generate_pdf(self, template: str, data: Dict[str, Any]) -> BytesIO:
        """
        Generate PDF output from template.
        
        Args:
            template: Template content (already processed)
            data: Data dictionary
            
        Returns:
            BytesIO object containing PDF file
        """
        # This is a placeholder - actual implementation would use reportlab or weasyprint
        # to generate PDF files from HTML template
        logger.warning("PDF generation not yet implemented")
        raise NotImplementedError("PDF generation not yet implemented")
