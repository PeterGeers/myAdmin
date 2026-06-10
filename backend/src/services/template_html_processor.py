"""
Template HTML Processor

Handles HTML parsing, validation, sanitization, and template rendering
for the template preview system.

Extracted from template_preview_service.py for maintainability.
"""

import re
import logging
from typing import Dict, Any, List
from datetime import datetime
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class TemplateHtmlProcessor:
    """
    Processes and validates HTML templates.

    Provides functionality for:
    - HTML syntax validation
    - Required placeholder validation
    - Security scanning
    - Template rendering with placeholder replacement
    """

    def validate_html_syntax(self, template_content: str) -> List[Dict[str, Any]]:
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

    def validate_placeholders(self, template_type: str, template_content: str) -> List[Dict[str, Any]]:
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
                ['amount_gross', 'amountGross', 'table_rows']  # amount_gross or table with amounts
            ],
            'str_invoice_en': [
                ['invoice_number', 'reservationCode'],
                ['guest_name', 'billing_name', 'guestName'],
                ['checkin_date', 'checkinDate'],
                ['checkout_date', 'checkoutDate'],
                ['amount_gross', 'amountGross', 'table_rows']
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
        # Updated regex to handle Jinja2 filters like {{ "%.2f"|format(variable) }}
        # This matches both simple {{ variable }} and filtered {{ ... | filter(variable) }}
        simple_placeholders = re.findall(r'\{\{\s*(\w+)\s*\}\}', template_content)
        filtered_placeholders = re.findall(r'\{\{[^}]*\|\s*\w+\((\w+)\)', template_content)

        # Combine both types
        found_placeholders = set(simple_placeholders + filtered_placeholders)

        logger.debug(f"Found placeholders: {found_placeholders}")

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

    def validate_security(self, template_content: str) -> List[Dict[str, Any]]:
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

    def render_template(
        self,
        template_content: str,
        sample_data: Dict[str, Any],
        field_mappings: Dict[str, Any]
    ) -> str:
        """
        Render template with sample data using simple placeholder replacement.

        Replaces placeholders in template with actual values from sample data.
        Does NOT use Jinja2 - only simple {{ placeholder }} replacement.

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

            logger.debug(f"Found {len(placeholders)} placeholders to replace")

            for placeholder in placeholders:
                # Get value from sample data
                value = sample_data.get(placeholder, f'[{placeholder}]')

                # Format value if it's a number or date
                if isinstance(value, (int, float)):
                    # Format numbers with thousands separator and 2 decimals
                    value = f"{value:,.2f}"
                elif isinstance(value, datetime):
                    value = value.strftime('%d-%m-%Y')

                # Replace placeholder
                pattern = r'\{\{\s*' + placeholder + r'\s*\}\}'
                rendered = re.sub(pattern, str(value), rendered)
                logger.debug(f"Replaced {placeholder} with {value}")

            logger.debug("Template rendering completed")

            return rendered

        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return template_content
