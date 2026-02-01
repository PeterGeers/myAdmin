"""
Unit tests for common_formatters module

Tests formatting utilities for currency, dates, numbers, and other data types.

This is a unit test suite - all functions are pure and have no external dependencies.
No database connections, no file system operations, no external API calls.
"""

import pytest
import os
import sys
from datetime import datetime
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from report_generators.common_formatters import (
    format_currency,
    format_amount,
    format_date,
    format_datetime,
    format_percentage,
    format_number,
    safe_float,
    safe_int,
    truncate_text,
    get_css_class_for_amount,
    escape_html
)


@pytest.mark.unit
class TestFormatCurrency:
    """Test suite for format_currency function"""
    
    def test_format_currency_default_eur(self):
        """Test currency formatting with default EUR"""
        result = format_currency(1234.56)
        assert result == "€ 1.234,56"
    
    def test_format_currency_usd(self):
        """Test currency formatting with USD"""
        result = format_currency(1234.56, currency='USD')
        assert result == "$ 1.234,56"
    
    def test_format_currency_gbp(self):
        """Test currency formatting with GBP"""
        result = format_currency(1234.56, currency='GBP')
        assert result == "£ 1.234,56"
    
    def test_format_currency_without_symbol(self):
        """Test currency formatting without symbol"""
        result = format_currency(1234.56, show_symbol=False)
        assert result == "1.234,56"
    
    def test_format_currency_custom_decimals(self):
        """Test currency formatting with custom decimal places"""
        result = format_currency(1234.567, decimals=3)
        assert result == "€ 1.234,567"
    
    def test_format_currency_zero_decimals(self):
        """Test currency formatting with zero decimals"""
        result = format_currency(1234.56, decimals=0)
        assert result == "€ 1.235"
    
    def test_format_currency_negative_value(self):
        """Test currency formatting with negative value"""
        result = format_currency(-1234.56)
        assert result == "€ -1.234,56"
    
    def test_format_currency_from_string(self):
        """Test currency formatting from string input"""
        result = format_currency("1234.56")
        assert result == "€ 1.234,56"
    
    def test_format_currency_from_string_with_symbols(self):
        """Test currency formatting from string with existing symbols"""
        result = format_currency("€ 1,234.56")
        assert result == "€ 1.234,56"
    
    def test_format_currency_from_decimal(self):
        """Test currency formatting from Decimal type"""
        result = format_currency(Decimal("1234.56"))
        assert result == "€ 1.234,56"
    
    def test_format_currency_invalid_input(self):
        """Test currency formatting with invalid input returns original"""
        result = format_currency("invalid")
        assert result == "invalid"
    
    def test_format_currency_large_number(self):
        """Test currency formatting with large numbers"""
        result = format_currency(1234567.89)
        assert result == "€ 1.234.567,89"


@pytest.mark.unit
class TestFormatAmount:
    """Test suite for format_amount function"""
    
    def test_format_amount_basic(self):
        """Test basic amount formatting"""
        result = format_amount(1234.56)
        assert result == "1.234,56"
    
    def test_format_amount_custom_decimals(self):
        """Test amount formatting with custom decimals"""
        result = format_amount(1234.567, decimals=3)
        assert result == "1.234,567"
    
    def test_format_amount_negative(self):
        """Test amount formatting with negative value"""
        result = format_amount(-1234.56)
        assert result == "-1.234,56"


@pytest.mark.unit
class TestFormatDate:
    """Test suite for format_date function"""
    
    def test_format_date_default_format(self):
        """Test date formatting with default DD-MM-YYYY format"""
        result = format_date('2025-01-31')
        assert result == "31-01-2025"
    
    def test_format_date_yyyy_mm_dd(self):
        """Test date formatting with YYYY-MM-DD format"""
        result = format_date('2025-01-31', format_type='YYYY-MM-DD')
        assert result == "2025-01-31"
    
    def test_format_date_mm_dd_yyyy(self):
        """Test date formatting with MM/DD/YYYY format"""
        result = format_date('2025-01-31', format_type='MM/DD/YYYY')
        assert result == "01/31/2025"
    
    def test_format_date_from_datetime_object(self):
        """Test date formatting from datetime object"""
        dt = datetime(2025, 1, 31)
        result = format_date(dt)
        assert result == "31-01-2025"
    
    def test_format_date_various_input_formats(self):
        """Test date formatting with various input formats"""
        # Test different input formats
        assert format_date('31-01-2025') == "31-01-2025"
        assert format_date('01/31/2025') == "31-01-2025"
        assert format_date('2025/01/31') == "31-01-2025"
    
    def test_format_date_invalid_input(self):
        """Test date formatting with invalid input returns original"""
        result = format_date('invalid-date')
        assert result == "invalid-date"


@pytest.mark.unit
class TestFormatDatetime:
    """Test suite for format_datetime function"""
    
    def test_format_datetime_default(self):
        """Test datetime formatting with default format"""
        result = format_datetime('2025-01-31 14:30:00')
        assert result == "31-01-2025 14:30:00"
    
    def test_format_datetime_yyyy_mm_dd(self):
        """Test datetime formatting with YYYY-MM-DD format"""
        result = format_datetime('2025-01-31 14:30:00', format_type='YYYY-MM-DD HH:MM:SS')
        assert result == "2025-01-31 14:30:00"
    
    def test_format_datetime_from_datetime_object(self):
        """Test datetime formatting from datetime object"""
        dt = datetime(2025, 1, 31, 14, 30, 0)
        result = format_datetime(dt)
        assert result == "31-01-2025 14:30:00"


@pytest.mark.unit
class TestFormatPercentage:
    """Test suite for format_percentage function"""
    
    def test_format_percentage_basic(self):
        """Test basic percentage formatting"""
        result = format_percentage(0.21)
        assert result == "21.00%"
    
    def test_format_percentage_zero_decimals(self):
        """Test percentage formatting with zero decimals"""
        result = format_percentage(0.21, decimals=0)
        assert result == "21%"
    
    def test_format_percentage_without_symbol(self):
        """Test percentage formatting without symbol"""
        result = format_percentage(0.21, show_symbol=False)
        assert result == "21.00"
    
    def test_format_percentage_from_string(self):
        """Test percentage formatting from string"""
        result = format_percentage("0.21")
        assert result == "21.00%"


@pytest.mark.unit
class TestFormatNumber:
    """Test suite for format_number function"""
    
    def test_format_number_with_separator(self):
        """Test number formatting with thousand separator"""
        result = format_number(1234.567)
        assert result == "1.234,57"
    
    def test_format_number_without_separator(self):
        """Test number formatting without thousand separator"""
        result = format_number(1234.567, thousand_separator=False)
        assert result == "1234,57"
    
    def test_format_number_custom_decimals(self):
        """Test number formatting with custom decimals"""
        result = format_number(1234.567, decimals=3)
        assert result == "1.234,567"


@pytest.mark.unit
class TestSafeFloat:
    """Test suite for safe_float function"""
    
    def test_safe_float_valid_string(self):
        """Test safe float conversion from valid string"""
        result = safe_float('123.45')
        assert result == 123.45
    
    def test_safe_float_invalid_string(self):
        """Test safe float conversion from invalid string returns default"""
        result = safe_float('invalid', default=0.0)
        assert result == 0.0
    
    def test_safe_float_none(self):
        """Test safe float conversion from None returns default"""
        result = safe_float(None, default=0.0)
        assert result == 0.0
    
    def test_safe_float_with_currency_symbols(self):
        """Test safe float conversion removes currency symbols"""
        result = safe_float('€ 1.234,56')
        assert result == 1234.56
    
    def test_safe_float_from_int(self):
        """Test safe float conversion from int"""
        result = safe_float(123)
        assert result == 123.0
    
    def test_safe_float_from_float(self):
        """Test safe float conversion from float"""
        result = safe_float(123.45)
        assert result == 123.45


@pytest.mark.unit
class TestSafeInt:
    """Test suite for safe_int function"""
    
    def test_safe_int_valid_string(self):
        """Test safe int conversion from valid string"""
        result = safe_int('123')
        assert result == 123
    
    def test_safe_int_invalid_string(self):
        """Test safe int conversion from invalid string returns default"""
        result = safe_int('invalid', default=0)
        assert result == 0
    
    def test_safe_int_none(self):
        """Test safe int conversion from None returns default"""
        result = safe_int(None, default=0)
        assert result == 0
    
    def test_safe_int_from_float(self):
        """Test safe int conversion from float"""
        result = safe_int(123.45)
        assert result == 123
    
    def test_safe_int_from_float_string(self):
        """Test safe int conversion from float string"""
        result = safe_int('123.45')
        assert result == 123


@pytest.mark.unit
class TestTruncateText:
    """Test suite for truncate_text function"""
    
    def test_truncate_text_short_text(self):
        """Test truncate text with text shorter than max length"""
        result = truncate_text('Short text', max_length=50)
        assert result == 'Short text'
    
    def test_truncate_text_long_text(self):
        """Test truncate text with text longer than max length"""
        result = truncate_text('This is a very long text', max_length=10)
        assert result == 'This is...'
    
    def test_truncate_text_custom_suffix(self):
        """Test truncate text with custom suffix"""
        result = truncate_text('This is a very long text', max_length=10, suffix='---')
        assert result == 'This is---'
    
    def test_truncate_text_empty_string(self):
        """Test truncate text with empty string"""
        result = truncate_text('', max_length=10)
        assert result == ''
    
    def test_truncate_text_none(self):
        """Test truncate text with None"""
        result = truncate_text(None, max_length=10)
        assert result == ''


@pytest.mark.unit
class TestGetCssClassForAmount:
    """Test suite for get_css_class_for_amount function"""
    
    def test_css_class_positive_amount(self):
        """Test CSS class for positive amount"""
        result = get_css_class_for_amount(100.50)
        assert result == 'positive'
    
    def test_css_class_negative_amount(self):
        """Test CSS class for negative amount"""
        result = get_css_class_for_amount(-50.25)
        assert result == 'negative'
    
    def test_css_class_zero_amount(self):
        """Test CSS class for zero amount"""
        result = get_css_class_for_amount(0.005)
        assert result == 'zero'
    
    def test_css_class_custom_threshold(self):
        """Test CSS class with custom threshold"""
        result = get_css_class_for_amount(0.5, threshold=1.0)
        assert result == 'zero'
    
    def test_css_class_from_string(self):
        """Test CSS class from string amount"""
        result = get_css_class_for_amount('100.50')
        assert result == 'positive'
    
    def test_css_class_invalid_input(self):
        """Test CSS class with invalid input returns zero"""
        result = get_css_class_for_amount('invalid')
        assert result == 'zero'


@pytest.mark.unit
class TestEscapeHtml:
    """Test suite for escape_html function"""
    
    def test_escape_html_script_tag(self):
        """Test HTML escaping of script tag"""
        result = escape_html('<script>alert("XSS")</script>')
        assert result == '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'
    
    def test_escape_html_ampersand(self):
        """Test HTML escaping of ampersand"""
        result = escape_html('Tom & Jerry')
        assert result == 'Tom &amp; Jerry'
    
    def test_escape_html_quotes(self):
        """Test HTML escaping of quotes"""
        result = escape_html('He said "Hello"')
        assert result == 'He said &quot;Hello&quot;'
    
    def test_escape_html_single_quotes(self):
        """Test HTML escaping of single quotes"""
        result = escape_html("It's a test")
        assert result == "It&#x27;s a test"
    
    def test_escape_html_angle_brackets(self):
        """Test HTML escaping of angle brackets"""
        result = escape_html('1 < 2 > 0')
        assert result == '1 &lt; 2 &gt; 0'
    
    def test_escape_html_empty_string(self):
        """Test HTML escaping of empty string"""
        result = escape_html('')
        assert result == ''
    
    def test_escape_html_none(self):
        """Test HTML escaping of None"""
        result = escape_html(None)
        assert result == ''
    
    def test_escape_html_normal_text(self):
        """Test HTML escaping of normal text without special characters"""
        result = escape_html('Normal text')
        assert result == 'Normal text'


@pytest.mark.unit
class TestEdgeCases:
    """Test suite for edge cases and boundary conditions"""
    
    def test_format_currency_very_large_number(self):
        """Test currency formatting with very large number"""
        result = format_currency(999999999999.99)
        assert result == "€ 999.999.999.999,99"
    
    def test_format_currency_very_small_number(self):
        """Test currency formatting with very small number"""
        result = format_currency(0.01)
        assert result == "€ 0,01"
    
    def test_safe_float_with_multiple_commas(self):
        """Test safe float with multiple thousand separators"""
        result = safe_float('1.234.567,89')
        assert result == 1234567.89
    
    def test_format_date_with_time_component(self):
        """Test date formatting ignores time component"""
        result = format_date('2025-01-31 14:30:00')
        assert result == "31-01-2025"
    
    @pytest.mark.parametrize("value,expected", [
        (0, "€ 0,00"),
        (0.0, "€ 0,00"),
        (1, "€ 1,00"),
        (-1, "€ -1,00"),
    ])
    def test_format_currency_special_values(self, value, expected):
        """Test currency formatting with special numeric values"""
        result = format_currency(value)
        assert result == expected
    
    @pytest.mark.parametrize("text,max_len,expected", [
        ("", 10, ""),
        ("a", 10, "a"),
        ("1234567890", 10, "1234567890"),
        ("12345678901", 10, "1234567..."),
    ])
    def test_truncate_text_boundary_conditions(self, text, max_len, expected):
        """Test truncate text with boundary conditions"""
        result = truncate_text(text, max_length=max_len)
        assert result == expected
