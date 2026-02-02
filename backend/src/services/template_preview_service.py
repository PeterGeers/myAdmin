"""
Template Preview Service for Railway Migration
Handles template preview generation, validation, and approval workflow.

This service provides template preview and validation capabilities for tenant administrators,
allowing them to safely upload, preview, and validate custom report templates before activation.
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class TemplatePreviewService:
    """
    Service for template preview and validation.
    
    Provides functionality for:
    - Generating template previews with sample data
    - Validating template syntax and structure
    - Fetching sample data for different template types
    - Approving and activating templates
    """
    
    def __init__(self, db_manager, administration: str):
        """
        Initialize the template preview service.
        
        Args:
            db_manager: DatabaseManager instance for database operations
            administration: The tenant/administration identifier
        """
        self.db = db_manager
        self.administration = administration
        
        # Import TemplateService for template operations
        from services.template_service import TemplateService
        self.template_service = TemplateService(db_manager)
        
        logger.info(f"TemplatePreviewService initialized for administration '{administration}'")
    
    def generate_preview(
        self,
        template_type: str,
        template_content: str,
        field_mappings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate preview with sample data.
        
        This method validates the template, fetches sample data, and generates
        a preview HTML by rendering the template with the sample data.
        
        Args:
            template_type: Type of template (e.g., 'str_invoice_nl', 'btw_aangifte')
            template_content: Template HTML content
            field_mappings: Field mappings configuration
            
        Returns:
            Dictionary containing:
            {
                'success': bool,
                'preview_html': str (if successful),
                'validation': dict,
                'sample_data_info': dict (if successful)
            }
        """
        try:
            logger.info(f"Generating preview for template type '{template_type}'")
            
            # 1. Validate template
            validation = self.validate_template(template_type, template_content)
            
            if not validation['is_valid']:
                logger.warning(f"Template validation failed for type '{template_type}'")
                return {
                    'success': False,
                    'validation': validation
                }
            
            # 2. Fetch sample data
            sample_data_result = self.fetch_sample_data(template_type)
            
            if not sample_data_result:
                logger.warning(f"No sample data available for template type '{template_type}'")
                return {
                    'success': False,
                    'validation': {
                        'is_valid': False,
                        'errors': [{
                            'type': 'no_sample_data',
                            'message': 'No sample data available for preview generation',
                            'severity': 'error'
                        }],
                        'warnings': []
                    }
                }
            
            sample_data = sample_data_result['data']
            sample_data_info = sample_data_result['metadata']
            
            # 3. Generate preview using report generator
            preview_html = self._render_template(
                template_content,
                sample_data,
                field_mappings
            )
            
            logger.info(f"Successfully generated preview for template type '{template_type}'")
            
            return {
                'success': True,
                'preview_html': preview_html,
                'validation': validation,
                'sample_data_info': sample_data_info
            }
            
        except Exception as e:
            logger.error(f"Failed to generate preview: {e}")
            return {
                'success': False,
                'validation': {
                    'is_valid': False,
                    'errors': [{
                        'type': 'preview_generation_error',
                        'message': f'Failed to generate preview: {str(e)}',
                        'severity': 'error'
                    }],
                    'warnings': []
                }
            }
    
    def validate_template(self, template_type: str, template_content: str) -> Dict[str, Any]:
        """
        Validate template syntax and structure.
        
        Performs multiple validation checks:
        - HTML syntax validation
        - Required placeholder validation
        - Security scan
        - File size check
        
        Args:
            template_type: Type of template
            template_content: Template HTML content
            
        Returns:
            Dictionary containing:
            {
                'is_valid': bool,
                'errors': list,
                'warnings': list,
                'checks_performed': list
            }
        """
        try:
            logger.info(f"Validating template type '{template_type}'")
            
            errors = []
            warnings = []
            
            # Check 1: HTML syntax
            syntax_errors = self._validate_html_syntax(template_content)
            errors.extend(syntax_errors)
            
            # Check 2: Required placeholders
            placeholder_errors = self._validate_placeholders(template_type, template_content)
            errors.extend(placeholder_errors)
            
            # Check 3: Security scan
            security_issues = self._validate_security(template_content)
            errors.extend([issue for issue in security_issues if issue.get('severity') == 'error'])
            warnings.extend([issue for issue in security_issues if issue.get('severity') == 'warning'])
            
            # Check 4: File size
            max_size = int(os.getenv('TEMPLATE_MAX_SIZE_MB', '5')) * 1024 * 1024
            if len(template_content.encode('utf-8')) > max_size:
                errors.append({
                    'type': 'file_size',
                    'message': f'Template exceeds {max_size // (1024 * 1024)}MB limit',
                    'severity': 'error'
                })
            
            is_valid = len(errors) == 0
            
            logger.info(
                f"Template validation completed: "
                f"valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}"
            )
            
            return {
                'is_valid': is_valid,
                'errors': errors,
                'warnings': warnings,
                'checks_performed': [
                    'html_syntax',
                    'required_placeholders',
                    'security_scan',
                    'file_size'
                ]
            }
            
        except Exception as e:
            logger.error(f"Template validation failed: {e}")
            return {
                'is_valid': False,
                'errors': [{
                    'type': 'validation_error',
                    'message': f'Validation failed: {str(e)}',
                    'severity': 'error'
                }],
                'warnings': [],
                'checks_performed': []
            }
    
    def fetch_sample_data(self, template_type: str) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent data for template type.
        
        Retrieves sample data from the database based on template type.
        Returns placeholder data if no real data is available.
        
        Args:
            template_type: Type of template
            
        Returns:
            Dictionary containing:
            {
                'data': dict (sample data),
                'metadata': dict (information about the sample data)
            }
            Returns None if fetch fails.
        """
        try:
            logger.info(f"Fetching sample data for template type '{template_type}'")
            
            if template_type in ['str_invoice_nl', 'str_invoice_en']:
                return self._fetch_str_invoice_sample()
            elif template_type == 'btw_aangifte':
                return self._fetch_btw_sample()
            elif template_type == 'aangifte_ib':
                return self._fetch_aangifte_ib_sample()
            elif template_type == 'toeristenbelasting':
                return self._fetch_toeristenbelasting_sample()
            else:
                return self._fetch_generic_sample()
                
        except Exception as e:
            logger.error(f"Failed to fetch sample data: {e}")
            return None
    
    def approve_template(
        self,
        template_type: str,
        template_content: str,
        field_mappings: Dict[str, Any],
        user_email: str,
        notes: str = ''
    ) -> Dict[str, Any]:
        """
        Approve and save template.
        
        This method:
        1. Validates the template
        2. Saves template to Google Drive
        3. Updates database metadata
        4. Archives previous version
        5. Logs approval
        
        Args:
            template_type: Type of template
            template_content: Template HTML content
            field_mappings: Field mappings configuration
            user_email: Email of user approving the template
            notes: Optional approval notes
            
        Returns:
            Dictionary containing:
            {
                'success': bool,
                'template_id': str (if successful),
                'file_id': str (if successful),
                'message': str,
                'previous_version': dict (if applicable)
            }
        """
        try:
            logger.info(f"Approving template type '{template_type}' by user '{user_email}'")
            
            # 1. Validate template one more time
            validation = self.validate_template(template_type, template_content)
            if not validation['is_valid']:
                return {
                    'success': False,
                    'message': 'Template validation failed',
                    'validation': validation
                }
            
            # 2. Get current template metadata (if exists)
            current_metadata = self.template_service.get_template_metadata(
                self.administration,
                template_type
            )
            
            previous_file_id = None
            version = 1
            
            if current_metadata:
                previous_file_id = current_metadata.get('template_file_id')
                # Increment version (would need to query for max version)
                version = 2  # Simplified - should query for actual max version
            
            # 3. Save template to Google Drive
            file_id = self._save_template_to_drive(
                template_type,
                template_content,
                version
            )
            
            # 4. Update database metadata
            self._update_template_metadata(
                template_type,
                file_id,
                field_mappings,
                user_email,
                notes,
                previous_file_id,
                version
            )
            
            # 5. Log approval
            self._log_template_approval(
                template_type,
                user_email,
                notes,
                validation
            )
            
            logger.info(
                f"Successfully approved template type '{template_type}', "
                f"file_id '{file_id}', version {version}"
            )
            
            result = {
                'success': True,
                'template_id': f"tmpl_{template_type}_{version}",
                'file_id': file_id,
                'message': 'Template approved and activated'
            }
            
            if previous_file_id:
                result['previous_version'] = {
                    'file_id': previous_file_id,
                    'archived_at': datetime.now().isoformat()
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to approve template: {e}")
            return {
                'success': False,
                'message': f'Failed to approve template: {str(e)}'
            }
    
    def _render_template(
        self,
        template_content: str,
        sample_data: Dict[str, Any],
        field_mappings: Dict[str, Any]
    ) -> str:
        """
        Render template with sample data.
        
        Replaces placeholders in template with actual values from sample data.
        
        Args:
            template_content: Template HTML content
            sample_data: Sample data dictionary
            field_mappings: Field mappings configuration
            
        Returns:
            Rendered HTML string
        """
        try:
            logger.debug("Rendering template with sample data")
            
            rendered = template_content
            
            # Simple placeholder replacement using {{ placeholder }} syntax
            # Find all placeholders
            placeholders = re.findall(r'\{\{\s*(\w+)\s*\}\}', template_content)
            
            for placeholder in placeholders:
                # Get value from sample data
                value = sample_data.get(placeholder, f'[{placeholder}]')
                
                # Format value if it's a number or date
                if isinstance(value, (int, float)):
                    value = f"{value:,.2f}"
                elif isinstance(value, datetime):
                    value = value.strftime('%d-%m-%Y')
                
                # Replace placeholder
                pattern = r'\{\{\s*' + placeholder + r'\s*\}\}'
                rendered = re.sub(pattern, str(value), rendered)
            
            logger.debug("Template rendering completed")
            
            return rendered
            
        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return template_content

    
    # Validation methods
    
    def _validate_html_syntax(self, template_content: str) -> List[Dict[str, Any]]:
        """
        Validate HTML is well-formed.
        
        Uses HTMLParser to check for:
        - Unclosed tags
        - Mismatched closing tags
        - Malformed HTML
        
        Args:
            template_content: Template HTML content
            
        Returns:
            List of error dictionaries
        """
        errors = []
        
        class ValidationParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.errors = []
                self.tag_stack = []
                self.line_number = 1
            
            def handle_starttag(self, tag, attrs):
                # Skip self-closing tags
                if tag not in ['br', 'hr', 'img', 'input', 'meta', 'link']:
                    self.tag_stack.append((tag, self.line_number))
            
            def handle_endtag(self, tag):
                if not self.tag_stack:
                    self.errors.append({
                        'type': 'syntax_error',
                        'message': f'Unexpected closing tag: </{tag}>',
                        'severity': 'error',
                        'line': self.line_number
                    })
                elif self.tag_stack[-1][0] != tag:
                    expected_tag = self.tag_stack[-1][0]
                    self.errors.append({
                        'type': 'syntax_error',
                        'message': f'Mismatched closing tag: expected </{expected_tag}>, got </{tag}>',
                        'severity': 'error',
                        'line': self.line_number
                    })
                else:
                    self.tag_stack.pop()
            
            def handle_data(self, data):
                # Count newlines to track line numbers
                self.line_number += data.count('\n')
        
        parser = ValidationParser()
        
        try:
            parser.feed(template_content)
            errors.extend(parser.errors)
            
            # Check for unclosed tags
            if parser.tag_stack:
                unclosed_tags = [tag for tag, line in parser.tag_stack]
                errors.append({
                    'type': 'syntax_error',
                    'message': f'Unclosed tags: {", ".join(unclosed_tags)}',
                    'severity': 'error'
                })
        
        except Exception as e:
            errors.append({
                'type': 'syntax_error',
                'message': f'HTML parsing error: {str(e)}',
                'severity': 'error'
            })
        
        return errors
    
    def _validate_placeholders(self, template_type: str, template_content: str) -> List[Dict[str, Any]]:
        """
        Check for required placeholders.
        
        Validates that all required placeholders for the template type
        are present in the template content. Supports both legacy placeholder
        names and database column names for backward compatibility.
        
        Args:
            template_type: Type of template
            template_content: Template HTML content
            
        Returns:
            List of error dictionaries
        """
        errors = []
        
        # Define required placeholders per template type
        # Each entry can have multiple acceptable names (legacy and new)
        REQUIRED_PLACEHOLDERS = {
            'str_invoice_nl': [
                ['invoice_number', 'reservationCode'],  # Either is acceptable
                ['guest_name', 'billing_name', 'guestName'],
                ['checkin_date', 'checkinDate'],
                ['checkout_date', 'checkoutDate'],
                ['amount_gross', 'amountGross', 'table_rows'],  # amount_gross or table with amounts
                ['company_name']
            ],
            'str_invoice_en': [
                ['invoice_number', 'reservationCode'],
                ['guest_name', 'billing_name', 'guestName'],
                ['checkin_date', 'checkinDate'],
                ['checkout_date', 'checkoutDate'],
                ['amount_gross', 'amountGross', 'table_rows'],
                ['company_name']
            ],
            'btw_aangifte': [
                ['year'],
                ['quarter'],
                ['administration'],
                ['balance_rows'],
                ['quarter_rows'],
                ['payment_instruction']
            ],
            'aangifte_ib': [
                ['year'],
                ['administration'],
                ['table_rows'],
                ['generated_date']
            ],
            'toeristenbelasting': [
                ['year'],
                ['contact_name'],
                ['contact_email'],
                ['nights_total'],
                ['revenue_total'],
                ['tourist_tax_total']
            ]
        }
        
        required = REQUIRED_PLACEHOLDERS.get(template_type, [])
        
        # Find all placeholders in template
        placeholders = re.findall(r'\{\{\s*(\w+)\s*\}\}', template_content)
        found_placeholders = set(placeholders)
        
        # Check for missing required placeholders
        for placeholder_options in required:
            # Ensure it's a list
            if isinstance(placeholder_options, str):
                placeholder_options = [placeholder_options]
            
            # Check if ANY of the acceptable names is present
            found = any(opt in found_placeholders for opt in placeholder_options)
            
            if not found:
                # Use the first option as the primary name in error message
                primary_name = placeholder_options[0]
                alternatives = placeholder_options[1:] if len(placeholder_options) > 1 else []
                
                message = f"Required placeholder '{{{{ {primary_name} }}}}' not found"
                if alternatives:
                    message += f" (alternatives: {', '.join(['{{ ' + alt + ' }}' for alt in alternatives])})"
                
                errors.append({
                    'type': 'missing_placeholder',
                    'message': message,
                    'severity': 'error',
                    'placeholder': primary_name
                })
        
        return errors
    
    def _validate_security(self, template_content: str) -> List[Dict[str, Any]]:
        """
        Check for security issues.
        
        Scans template for:
        - Script tags (not allowed)
        - Event handlers (not allowed)
        - External resources (warning)
        
        Args:
            template_content: Template HTML content
            
        Returns:
            List of error/warning dictionaries
        """
        issues = []
        
        # Check for script tags
        if re.search(r'<script[^>]*>', template_content, re.IGNORECASE):
            issues.append({
                'type': 'security_error',
                'message': 'Script tags are not allowed in templates',
                'severity': 'error'
            })
        
        # Check for event handlers (improved regex to avoid false positives)
        # Match event handlers like onclick=, onload=, etc. but not content="...on="
        # Use word boundary and ensure it's an actual HTML attribute
        event_handlers = re.findall(
            r'<[^>]*\s(on\w+)\s*=',
            template_content,
            re.IGNORECASE
        )
        if event_handlers:
            issues.append({
                'type': 'security_error',
                'message': f'Event handlers are not allowed: {", ".join(set(event_handlers))}',
                'severity': 'error'
            })
        
        # Check for external resources
        external_resources = re.findall(
            r'(src|href)\s*=\s*["\']https?://',
            template_content,
            re.IGNORECASE
        )
        if external_resources:
            issues.append({
                'type': 'security_warning',
                'message': 'External resources detected. Ensure they are from trusted sources.',
                'severity': 'warning'
            })
        
        return issues
    
    # Sample data fetching methods
    
    def _fetch_str_invoice_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent STR booking for invoice preview.
        
        Queries the vw_bnb_total view for the most recent realised booking
        for the current administration. Falls back to placeholder data if
        no bookings are found.
        
        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            query = """
                SELECT 
                    reservationCode,
                    guestName,
                    channel,
                    listing,
                    checkinDate,
                    checkoutDate,
                    nights,
                    guests,
                    amountGross,
                    amountNett,
                    amountChannelFee,
                    amountTouristTax,
                    amountVat,
                    status
                FROM vw_bnb_total
                WHERE administration = %s
                AND status = 'realised'
                ORDER BY checkinDate DESC
                LIMIT 1
            """
            
            results = self.db.execute_query(query, (self.administration,))
            
            if not results or len(results) == 0:
                logger.warning(f"No STR bookings found for administration '{self.administration}'")
                return self._get_placeholder_str_data()
            
            booking = results[0]
            
            # Prepare invoice data using the generator
            from report_generators.str_invoice_generator import prepare_invoice_data
            invoice_data = prepare_invoice_data(booking)
            
            # Generate invoice number (simplified - should use proper invoice numbering)
            invoice_data['invoice_number'] = f"INV-{booking.get('reservationCode', 'UNKNOWN')}"
            
            return {
                'data': invoice_data,
                'metadata': {
                    'source': 'database',
                    'record_date': str(booking.get('checkinDate', '')),
                    'record_id': booking.get('reservationCode', ''),
                    'message': 'Using most recent realised booking'
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch STR invoice sample: {e}")
            return self._get_placeholder_str_data()
    
    def _fetch_btw_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent BTW (VAT) data for preview.
        
        Retrieves balance and quarter data for the most recent quarter
        with available data. Uses the BTW aangifte generator to prepare
        the data in the correct format.
        
        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            # Get most recent year and quarter with data
            current_year = datetime.now().year
            current_quarter = (datetime.now().month - 1) // 3 + 1
            
            # Try to generate report using the actual generator
            try:
                from report_generators.btw_aangifte_generator import generate_btw_report, prepare_template_data
                from cache.mutaties_cache import MutatiesCache
                
                # Initialize cache
                cache = MutatiesCache()
                
                # Generate report
                report_data = generate_btw_report(
                    cache=cache,
                    db=self.db,
                    administration=self.administration,
                    year=current_year,
                    quarter=current_quarter
                )
                
                if report_data.get('success'):
                    # Prepare template data
                    template_data = prepare_template_data(report_data)
                    
                    return {
                        'data': template_data,
                        'metadata': {
                            'source': 'database',
                            'record_date': f'{current_year}-Q{current_quarter}',
                            'record_id': f'BTW-{current_year}-Q{current_quarter}',
                            'message': 'Using most recent quarter data'
                        }
                    }
                else:
                    logger.warning(f"BTW report generation failed: {report_data.get('error')}")
                    
            except ImportError as ie:
                logger.warning(f"Could not import BTW generator: {ie}")
            except Exception as ge:
                logger.warning(f"BTW report generation error: {ge}")
            
            # Fallback to placeholder data
            sample_data = {
                'year': str(current_year),
                'quarter': str(current_quarter),
                'administration': self.administration,
                'balance_rows': '<tr><td>2010</td><td>BTW te betalen</td><td class="amount">€1,000.00</td></tr>',
                'quarter_rows': '<tr><td>2020</td><td>BTW ontvangen</td><td class="amount">€500.00</td></tr>',
                'payment_instruction': '€500 te betalen',
                'generated_date': datetime.now().strftime('%d-%m-%Y')
            }
            
            return {
                'data': sample_data,
                'metadata': {
                    'source': 'placeholder',
                    'record_date': f'{current_year}-Q{current_quarter}',
                    'record_id': f'BTW-{current_year}-Q{current_quarter}',
                    'message': 'Using placeholder data - no real data available'
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch BTW sample: {e}")
            return None
    
    def _fetch_aangifte_ib_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent Aangifte IB (income tax) data for preview.
        
        Retrieves income tax data for the most recent year with available data.
        Uses the Aangifte IB generator to prepare the data in the correct format.
        
        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            # Use previous year as current year data may not be complete
            current_year = datetime.now().year - 1
            
            # Try to generate report using the actual generator
            try:
                from report_generators.aangifte_ib_generator import generate_table_rows
                from cache.mutaties_cache import MutatiesCache
                
                # Initialize cache
                cache = MutatiesCache()
                
                # Get report data from cache
                df = cache.get_data(self.db)
                
                # Filter by year and administration
                df_filtered = df[
                    (df['jaar'] == current_year) & 
                    (df['administration'].str.startswith(self.administration))
                ].copy()
                
                if len(df_filtered) > 0:
                    # Generate table rows
                    table_rows = generate_table_rows(
                        report_data=df_filtered.to_dict('records'),
                        cache=cache,
                        year=current_year,
                        administration=self.administration,
                        user_tenants=[self.administration]
                    )
                    
                    sample_data = {
                        'year': str(current_year),
                        'administration': self.administration,
                        'table_rows': table_rows,
                        'generated_date': datetime.now().strftime('%d-%m-%Y')
                    }
                    
                    return {
                        'data': sample_data,
                        'metadata': {
                            'source': 'database',
                            'record_date': str(current_year),
                            'record_id': f'IB-{current_year}',
                            'message': f'Using data from year {current_year}'
                        }
                    }
                else:
                    logger.warning(f"No Aangifte IB data found for {self.administration} in {current_year}")
                    
            except ImportError as ie:
                logger.warning(f"Could not import Aangifte IB generator: {ie}")
            except Exception as ge:
                logger.warning(f"Aangifte IB report generation error: {ge}")
            
            # Fallback to placeholder data
            sample_data = {
                'year': str(current_year),
                'administration': self.administration,
                'table_rows': '<tr><td>8001</td><td>Omzet</td><td class="amount">€50,000.00</td></tr>',
                'generated_date': datetime.now().strftime('%d-%m-%Y')
            }
            
            return {
                'data': sample_data,
                'metadata': {
                    'source': 'placeholder',
                    'record_date': str(current_year),
                    'record_id': f'IB-{current_year}',
                    'message': 'Using placeholder data - no real data available'
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch Aangifte IB sample: {e}")
            return None
    
    def _fetch_toeristenbelasting_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent tourist tax data for preview.
        
        Retrieves tourist tax declaration data for the most recent year
        with available data. Uses the Toeristenbelasting generator to
        prepare the data in the correct format.
        
        Returns:
            Dictionary with 'data' and 'metadata' keys, or None if no data found
        """
        try:
            current_year = datetime.now().year
            
            # Try to generate report using the actual generator
            try:
                from report_generators.toeristenbelasting_generator import generate_toeristenbelasting_report
                from cache.mutaties_cache import MutatiesCache
                from cache.bnb_cache import BNBCache
                
                # Initialize caches
                cache = MutatiesCache()
                bnb_cache = BNBCache()
                
                # Generate report
                report_data = generate_toeristenbelasting_report(
                    cache=cache,
                    bnb_cache=bnb_cache,
                    db=self.db,
                    year=current_year
                )
                
                if report_data.get('success'):
                    # Use template_data from the report
                    template_data = report_data.get('template_data', {})
                    
                    return {
                        'data': template_data,
                        'metadata': {
                            'source': 'database',
                            'record_date': str(current_year),
                            'record_id': f'TT-{current_year}',
                            'message': f'Using data from year {current_year}'
                        }
                    }
                else:
                    logger.warning(f"Toeristenbelasting report generation failed: {report_data.get('error')}")
                    
            except ImportError as ie:
                logger.warning(f"Could not import Toeristenbelasting generator: {ie}")
            except Exception as ge:
                logger.warning(f"Toeristenbelasting report generation error: {ge}")
            
            # Fallback to placeholder data
            sample_data = {
                'year': str(current_year),
                'contact_name': 'Sample Contact',
                'contact_email': 'contact@example.com',
                'nights_total': '100',
                'revenue_total': '€10,000.00',
                'tourist_tax_total': '€300.00',
                'generated_date': datetime.now().strftime('%d-%m-%Y')
            }
            
            return {
                'data': sample_data,
                'metadata': {
                    'source': 'placeholder',
                    'record_date': str(current_year),
                    'record_id': f'TT-{current_year}',
                    'message': 'Using placeholder data - no real data available'
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch tourist tax sample: {e}")
            return None
    
    def _fetch_generic_sample(self) -> Optional[Dict[str, Any]]:
        """
        Fetch generic placeholder data for unknown template types.
        
        This method provides fallback data when the template type is not
        recognized or when specific sample data fetching fails. It ensures
        that preview generation can always proceed with some data.
        
        Returns:
            Dictionary with 'data' and 'metadata' keys
        """
        logger.info(f"Using generic placeholder data for administration '{self.administration}'")
        
        sample_data = {
            'administration': self.administration,
            'generated_date': datetime.now().strftime('%d-%m-%Y'),
            'year': str(datetime.now().year),
            'sample_text': 'Sample Data',
            'sample_number': '1,234.56',
            'sample_currency': '€1,234.56',
            'company_name': 'Sample Company',
            'contact_email': 'contact@example.com'
        }
        
        return {
            'data': sample_data,
            'metadata': {
                'source': 'placeholder',
                'record_date': datetime.now().strftime('%Y-%m-%d'),
                'record_id': 'GENERIC-SAMPLE',
                'message': 'Using generic placeholder data - template type not recognized'
            }
        }
    
    def _get_placeholder_str_data(self) -> Dict[str, Any]:
        """
        Get placeholder STR invoice data when no real data is available.
        
        This method provides fallback invoice data with realistic sample values
        to ensure preview generation can proceed even when no bookings exist
        in the database.
        
        Returns:
            Dictionary with 'data' and 'metadata' keys
        """
        logger.info(f"Using placeholder STR invoice data for administration '{self.administration}'")
        
        placeholder_data = {
            'invoice_number': 'INV-2026-001',
            'reservationCode': 'RES-SAMPLE-001',
            'guestName': 'Sample Guest',
            'channel': 'Booking.com',
            'listing': 'Sample Property',
            'checkinDate': '01-01-2026',
            'checkoutDate': '05-01-2026',
            'nights': 4,
            'guests': 2,
            'amountGross': 500.00,
            'amountTouristTax': 15.00,
            'amountChannelFee': 50.00,
            'amountNett': 435.00,
            'amountVat': 0.00,
            'net_amount': 485.00,
            'tourist_tax': 15.00,
            'vat_amount': 0.00,
            'billing_name': 'Sample Guest',
            'billing_address': 'Via Booking.com',
            'billing_city': 'Reservering: RES-SAMPLE-001',
            'invoice_date': datetime.now().strftime('%d-%m-%Y'),
            'due_date': datetime.now().strftime('%d-%m-%Y'),
            'company_name': 'Jabaki a Goodwin Solutions Company',
            'company_address': 'Beemsterstraat 3',
            'company_postal_city': '2131 ZA Hoofddorp',
            'company_country': 'Nederland',
            'company_vat': 'NL812613764B02',
            'company_coc': '24352408',
            'contact_email': 'peter@jabaki.nl'
        }
        
        return {
            'data': placeholder_data,
            'metadata': {
                'source': 'placeholder',
                'message': 'No bookings found, using placeholder data',
                'record_date': datetime.now().strftime('%Y-%m-%d'),
                'record_id': 'PLACEHOLDER'
            }
        }
    
    # Template approval helper methods
    
    def _save_template_to_drive(
        self,
        template_type: str,
        template_content: str,
        version: int
    ) -> str:
        """
        Save template to Google Drive.
        
        Args:
            template_type: Type of template
            template_content: Template HTML content
            version: Version number
            
        Returns:
            Google Drive file ID
            
        Raises:
            Exception: If save fails
        """
        try:
            from google_drive_service import GoogleDriveService
            from io import BytesIO
            from googleapiclient.http import MediaIoBaseUpload
            
            # Initialize Google Drive service for this tenant
            drive_service = GoogleDriveService(self.administration)
            
            # Create file metadata
            file_name = f"{template_type}_v{version}.html"
            file_metadata = {
                'name': file_name,
                'mimeType': 'text/html'
            }
            
            # Create media upload
            file_content = BytesIO(template_content.encode('utf-8'))
            media = MediaIoBaseUpload(
                file_content,
                mimetype='text/html',
                resumable=True
            )
            
            # Upload file
            file = drive_service.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            
            logger.info(f"Saved template to Google Drive: file_id '{file_id}'")
            
            return file_id
            
        except Exception as e:
            logger.error(f"Failed to save template to Google Drive: {e}")
            raise Exception(f"Failed to save template to Google Drive: {str(e)}")
    
    def _update_template_metadata(
        self,
        template_type: str,
        file_id: str,
        field_mappings: Dict[str, Any],
        user_email: str,
        notes: str,
        previous_file_id: Optional[str],
        version: int
    ):
        """
        Update template metadata in database.
        
        Args:
            template_type: Type of template
            file_id: Google Drive file ID
            field_mappings: Field mappings configuration
            user_email: Email of approving user
            notes: Approval notes
            previous_file_id: Previous version file ID (if exists)
            version: Version number
        """
        try:
            # Convert field_mappings to JSON
            field_mappings_json = json.dumps(field_mappings) if field_mappings else None
            
            # Check if template config exists
            check_query = """
                SELECT id FROM tenant_template_config
                WHERE administration = %s AND template_type = %s
            """
            existing = self.db.execute_query(check_query, (self.administration, template_type))
            
            if existing:
                # Update existing
                update_query = """
                    UPDATE tenant_template_config
                    SET template_file_id = %s,
                        field_mappings = %s,
                        version = %s,
                        approved_by = %s,
                        approved_at = NOW(),
                        approval_notes = %s,
                        previous_file_id = %s,
                        status = 'active',
                        is_active = TRUE,
                        updated_at = NOW()
                    WHERE administration = %s AND template_type = %s
                """
                self.db.execute_query(
                    update_query,
                    (file_id, field_mappings_json, version, user_email, notes,
                     previous_file_id, self.administration, template_type),
                    fetch=False,
                    commit=True
                )
            else:
                # Insert new
                insert_query = """
                    INSERT INTO tenant_template_config
                    (administration, template_type, template_file_id, field_mappings,
                     version, approved_by, approved_at, approval_notes, previous_file_id,
                     status, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, 'active', TRUE)
                """
                self.db.execute_query(
                    insert_query,
                    (self.administration, template_type, file_id, field_mappings_json,
                     version, user_email, notes, previous_file_id),
                    fetch=False,
                    commit=True
                )
            
            logger.info(f"Updated template metadata for type '{template_type}'")
            
        except Exception as e:
            logger.error(f"Failed to update template metadata: {e}")
            raise Exception(f"Failed to update template metadata: {str(e)}")
    
    def _log_template_approval(
        self,
        template_type: str,
        user_email: str,
        notes: str,
        validation: Dict[str, Any]
    ):
        """
        Log template approval in validation log.
        
        Args:
            template_type: Type of template
            user_email: Email of approving user
            notes: Approval notes
            validation: Validation results
        """
        try:
            errors_json = json.dumps(validation.get('errors', []))
            warnings_json = json.dumps(validation.get('warnings', []))
            
            query = """
                INSERT INTO template_validation_log
                (administration, template_type, validation_result, errors, warnings,
                 validated_by, validated_at)
                VALUES (%s, %s, 'pass', %s, %s, %s, NOW())
            """
            
            self.db.execute_query(
                query,
                (self.administration, template_type, errors_json, warnings_json, user_email),
                fetch=False,
                commit=True
            )
            
            logger.info(f"Logged template approval for type '{template_type}'")
            
        except Exception as e:
            logger.error(f"Failed to log template approval: {e}")
            # Don't raise - logging failure shouldn't block approval
