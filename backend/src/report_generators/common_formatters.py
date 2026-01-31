"""
Common Formatting Utilities for Report Generators

This module provides shared formatting functions used across all report generators.
These utilities ensure consistent formatting of currency, dates, numbers, and other
data types throughout the application.

Usage:
    from report_generators.common_formatters import format_currency, format_date
    
    formatted_amount = format_currency(1234.56, currency='EUR')
    # Returns: "€ 1,234.56"
    
    formatted_date = format_date('2025-01-31', format_type='DD-MM-YYYY')
    # Returns: "31-01-2025"
"""

import logging
from datetime import datetime
from typing import Any, Optional, Union
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


def format_currency(
    value: Union[int, float, Decimal, str],
    currency: str = 'EUR',
    decimals: int = 2,
    show_symbol: bool = True,
    locale: str = 'nl_NL'
) -> str:
    """
    Format a numeric value as currency with locale-specific formatting.
    
    Args:
        value: Numeric value to format (int, float, Decimal, or string)
        currency: Currency code ('EUR', 'USD', 'GBP')
        decimals: Number of decimal places (default: 2)
        show_symbol: Whether to show currency symbol (default: True)
        locale: Locale for formatting ('nl_NL' for Dutch, 'en_US' for English)
    
    Returns:
        Formatted currency string (e.g., "€ 1.234,56" for nl_NL or "€ 1,234.56" for en_US)
    
    Examples:
        >>> format_currency(1234.56)
        '€ 1.234,56'
        >>> format_currency(1234.56, locale='en_US')
        '€ 1,234.56'
        >>> format_currency(1234.56, show_symbol=False)
        '1.234,56'
    """
    try:
        # Convert to float
        if isinstance(value, str):
            # Remove any existing currency symbols or separators
            value = value.replace('€', '').replace('$', '').replace('£', '')
            # Handle both Dutch and English formats
            if '.' in value and ',' in value:
                # Determine format by position (last separator is decimal)
                last_dot = value.rfind('.')
                last_comma = value.rfind(',')
                if last_comma > last_dot:
                    # Dutch format: 1.234,56
                    value = value.replace('.', '').replace(',', '.')
                else:
                    # English format: 1,234.56
                    value = value.replace(',', '')
            elif ',' in value:
                # Only comma - assume decimal separator
                value = value.replace(',', '.')
            value = value.strip()
        
        numeric_value = float(value)
        
        # Format with English separators first
        formatted_english = f"{numeric_value:,.{decimals}f}"
        
        # Apply locale-specific separators
        if locale.startswith('nl'):  # Dutch: . for thousands, , for decimal
            formatted = formatted_english.replace(',', 'TEMP').replace('.', ',').replace('TEMP', '.')
        else:  # English/default: , for thousands, . for decimal
            formatted = formatted_english
        
        # Add currency symbol if requested
        if show_symbol:
            currency_symbols = {
                'EUR': '€',
                'USD': '$',
                'GBP': '£'
            }
            symbol = currency_symbols.get(currency.upper(), currency)
            return f"{symbol} {formatted}"
        
        return formatted
        
    except (ValueError, TypeError, InvalidOperation) as e:
        logger.warning(f"Failed to format currency value '{value}': {e}")
        return str(value)


def format_amount(
    value: Union[int, float, Decimal, str],
    decimals: int = 2,
    locale: str = 'nl_NL'
) -> str:
    """
    Format a numeric amount without currency symbol with locale-specific formatting.
    
    Args:
        value: Numeric value to format
        decimals: Number of decimal places (default: 2)
        locale: Locale for formatting ('nl_NL' for Dutch, 'en_US' for English)
    
    Returns:
        Formatted number string with locale-specific separators
    
    Examples:
        >>> format_amount(1234.56)
        '1.234,56'
        >>> format_amount(1234.56, locale='en_US')
        '1,234.56'
        >>> format_amount(1234.567, decimals=3)
        '1.234,567'
    """
    return format_currency(value, show_symbol=False, decimals=decimals, locale=locale)


def format_date(
    value: Union[str, datetime],
    format_type: str = 'DD-MM-YYYY'
) -> str:
    """
    Format a date value according to specified format.
    
    Args:
        value: Date value (string or datetime object)
        format_type: Output format ('DD-MM-YYYY', 'YYYY-MM-DD', 'MM/DD/YYYY')
    
    Returns:
        Formatted date string
    
    Examples:
        >>> format_date('2025-01-31')
        '31-01-2025'
        >>> format_date('2025-01-31', format_type='YYYY-MM-DD')
        '2025-01-31'
    """
    try:
        # Convert string to datetime if needed
        if isinstance(value, str):
            # Try common date formats
            date_formats = [
                '%Y-%m-%d',
                '%d-%m-%Y',
                '%m/%d/%Y',
                '%Y/%m/%d',
                '%Y-%m-%d %H:%M:%S',
                '%d-%m-%Y %H:%M:%S'
            ]
            
            date_obj = None
            for fmt in date_formats:
                try:
                    date_obj = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            
            if date_obj is None:
                # If no format matches, return as-is
                logger.warning(f"Could not parse date string: {value}")
                return value
        elif isinstance(value, datetime):
            date_obj = value
        else:
            logger.warning(f"Unsupported date type: {type(value)}")
            return str(value)
        
        # Format according to format_type
        format_map = {
            'DD-MM-YYYY': '%d-%m-%Y',
            'YYYY-MM-DD': '%Y-%m-%d',
            'MM/DD/YYYY': '%m/%d/%Y',
            'DD/MM/YYYY': '%d/%m/%Y',
            'YYYY/MM/DD': '%Y/%m/%d'
        }
        
        strftime_format = format_map.get(format_type, '%d-%m-%Y')
        return date_obj.strftime(strftime_format)
        
    except Exception as e:
        logger.warning(f"Failed to format date '{value}': {e}")
        return str(value)


def format_datetime(
    value: Union[str, datetime],
    format_type: str = 'DD-MM-YYYY HH:MM:SS'
) -> str:
    """
    Format a datetime value according to specified format.
    
    Args:
        value: Datetime value (string or datetime object)
        format_type: Output format (default: 'DD-MM-YYYY HH:MM:SS')
    
    Returns:
        Formatted datetime string
    
    Examples:
        >>> format_datetime('2025-01-31 14:30:00')
        '31-01-2025 14:30:00'
    """
    try:
        # Convert string to datetime if needed
        if isinstance(value, str):
            datetime_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%d-%m-%Y %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%d-%m-%Y %H:%M'
            ]
            
            datetime_obj = None
            for fmt in datetime_formats:
                try:
                    datetime_obj = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            
            if datetime_obj is None:
                logger.warning(f"Could not parse datetime string: {value}")
                return value
        elif isinstance(value, datetime):
            datetime_obj = value
        else:
            logger.warning(f"Unsupported datetime type: {type(value)}")
            return str(value)
        
        # Format according to format_type
        if format_type == 'DD-MM-YYYY HH:MM:SS':
            return datetime_obj.strftime('%d-%m-%Y %H:%M:%S')
        elif format_type == 'YYYY-MM-DD HH:MM:SS':
            return datetime_obj.strftime('%Y-%m-%d %H:%M:%S')
        elif format_type == 'DD-MM-YYYY HH:MM':
            return datetime_obj.strftime('%d-%m-%Y %H:%M')
        else:
            return datetime_obj.strftime('%d-%m-%Y %H:%M:%S')
        
    except Exception as e:
        logger.warning(f"Failed to format datetime '{value}': {e}")
        return str(value)


def format_percentage(
    value: Union[int, float, Decimal, str],
    decimals: int = 2,
    show_symbol: bool = True
) -> str:
    """
    Format a numeric value as percentage.
    
    Args:
        value: Numeric value to format (0.21 for 21%)
        decimals: Number of decimal places (default: 2)
        show_symbol: Whether to show % symbol (default: True)
    
    Returns:
        Formatted percentage string
    
    Examples:
        >>> format_percentage(0.21)
        '21.00%'
        >>> format_percentage(0.21, decimals=0)
        '21%'
    """
    try:
        numeric_value = float(value) * 100
        formatted = f"{numeric_value:.{decimals}f}"
        
        if show_symbol:
            return f"{formatted}%"
        return formatted
        
    except (ValueError, TypeError, InvalidOperation) as e:
        logger.warning(f"Failed to format percentage value '{value}': {e}")
        return str(value)


def format_number(
    value: Union[int, float, Decimal, str],
    decimals: int = 2,
    thousand_separator: bool = True,
    locale: str = 'nl_NL'
) -> str:
    """
    Format a numeric value with optional thousand separators and locale-specific formatting.
    
    Args:
        value: Numeric value to format
        decimals: Number of decimal places (default: 2)
        thousand_separator: Whether to use thousand separators (default: True)
        locale: Locale for formatting ('nl_NL' for Dutch, 'en_US' for English)
    
    Returns:
        Formatted number string with locale-specific separators
    
    Examples:
        >>> format_number(1234.567)
        '1.234,57'
        >>> format_number(1234.567, locale='en_US')
        '1,234.57'
        >>> format_number(1234.567, thousand_separator=False)
        '1234,57'
    """
    try:
        numeric_value = float(value)
        
        if thousand_separator:
            # Format with English separators first
            formatted_english = f"{numeric_value:,.{decimals}f}"
            # Apply locale-specific separators
            if locale.startswith('nl'):  # Dutch
                return formatted_english.replace(',', 'TEMP').replace('.', ',').replace('TEMP', '.')
            else:  # English/default
                return formatted_english
        else:
            # No thousand separator, just decimal
            formatted = f"{numeric_value:.{decimals}f}"
            if locale.startswith('nl'):  # Dutch: comma for decimal
                return formatted.replace('.', ',')
            else:  # English: period for decimal
                return formatted
        
    except (ValueError, TypeError, InvalidOperation) as e:
        logger.warning(f"Failed to format number value '{value}': {e}")
        return str(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default if conversion fails.
    Handles both English and Dutch number formats.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails (default: 0.0)
    
    Returns:
        Float value or default
    
    Examples:
        >>> safe_float('123.45')
        123.45
        >>> safe_float('123,45')
        123.45
        >>> safe_float('1.234,56')
        1234.56
        >>> safe_float('invalid', default=0.0)
        0.0
    """
    try:
        if value is None:
            return default
        
        if isinstance(value, str):
            # Remove common formatting characters
            value = value.replace('€', '').replace('$', '').replace('£', '').strip()
            
            # Detect format: if contains both . and ,, assume Dutch format (. = thousands, , = decimal)
            if '.' in value and ',' in value:
                # Dutch format: 1.234,56
                value = value.replace('.', '').replace(',', '.')
            elif ',' in value and '.' not in value:
                # Only comma, assume decimal separator: 123,45
                value = value.replace(',', '.')
            # else: English format or no separators, use as-is
        
        return float(value)
    except (ValueError, TypeError, InvalidOperation):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert a value to int, returning default if conversion fails.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails (default: 0)
    
    Returns:
        Integer value or default
    
    Examples:
        >>> safe_int('123')
        123
        >>> safe_int('invalid', default=0)
        0
    """
    try:
        if value is None:
            return default
        return int(float(value))
    except (ValueError, TypeError, InvalidOperation):
        return default


def truncate_text(text: str, max_length: int = 50, suffix: str = '...') -> str:
    """
    Truncate text to maximum length, adding suffix if truncated.
    
    Args:
        text: Text to truncate
        max_length: Maximum length (default: 50)
        suffix: Suffix to add if truncated (default: '...')
    
    Returns:
        Truncated text
    
    Examples:
        >>> truncate_text('This is a very long text', max_length=10)
        'This is...'
    """
    if not text:
        return ''
    
    text = str(text)
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def get_css_class_for_amount(amount: Union[int, float, Decimal], threshold: float = 0.01) -> str:
    """
    Get CSS class name based on amount value (positive/negative/zero).
    
    Args:
        amount: Numeric amount
        threshold: Threshold for considering value as zero (default: 0.01)
    
    Returns:
        CSS class name ('positive', 'negative', or 'zero')
    
    Examples:
        >>> get_css_class_for_amount(100.50)
        'positive'
        >>> get_css_class_for_amount(-50.25)
        'negative'
        >>> get_css_class_for_amount(0.005)
        'zero'
    """
    try:
        numeric_value = float(amount)
        
        if abs(numeric_value) < threshold:
            return 'zero'
        elif numeric_value > 0:
            return 'positive'
        else:
            return 'negative'
    except (ValueError, TypeError, InvalidOperation):
        return 'zero'


def escape_html(text: str) -> str:
    """
    Escape HTML special characters in text.
    
    Args:
        text: Text to escape
    
    Returns:
        HTML-escaped text
    
    Examples:
        >>> escape_html('<script>alert("XSS")</script>')
        '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'
    """
    if not text:
        return ''
    
    text = str(text)
    html_escape_table = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&#x27;",
        ">": "&gt;",
        "<": "&lt;",
    }
    
    return "".join(html_escape_table.get(c, c) for c in text)
