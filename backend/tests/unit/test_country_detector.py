"""
Unit tests for country_detector module.

Tests country detection from phone numbers, Booking.com addInfo fields,
and the integrated detect_country function.

Requirements: 1.7, 2.1, 8.1, 8.5
"""

import pytest
from unittest.mock import patch, MagicMock

from country_detector import (
    extract_country_from_phone,
    extract_country_from_booking_addinfo,
    detect_country,
    get_country_name,
)


# ---------------------------------------------------------------------------
# extract_country_from_phone
# ---------------------------------------------------------------------------

class TestExtractCountryFromPhone:
    """Tests for extract_country_from_phone function."""

    def test_extract_country_from_phone_uae_returns_ae(self):
        assert extract_country_from_phone('+971 58 260 0953') == 'AE'

    def test_extract_country_from_phone_spain_returns_es(self):
        assert extract_country_from_phone('+34 612 345 678') == 'ES'

    def test_extract_country_from_phone_us_returns_us(self):
        assert extract_country_from_phone('+1 555 123 4567') == 'US'

    def test_extract_country_from_phone_uk_returns_gb(self):
        assert extract_country_from_phone('+44 20 7946 0958') == 'GB'

    def test_extract_country_from_phone_netherlands_returns_nl(self):
        assert extract_country_from_phone('+31 20 123 4567') == 'NL'

    def test_extract_country_from_phone_germany_returns_de(self):
        assert extract_country_from_phone('+49 30 123456') == 'DE'

    def test_extract_country_from_phone_france_returns_fr(self):
        assert extract_country_from_phone('+33 1 23 45 67 89') == 'FR'

    def test_extract_country_from_phone_none_returns_none(self):
        assert extract_country_from_phone(None) is None

    def test_extract_country_from_phone_empty_string_returns_none(self):
        assert extract_country_from_phone('') is None

    def test_extract_country_from_phone_malformed_returns_none(self):
        assert extract_country_from_phone('not-a-phone') is None

    def test_extract_country_from_phone_digits_only_no_plus_returns_none(self):
        assert extract_country_from_phone('31201234567') is None

    def test_extract_country_from_phone_non_string_returns_none(self):
        assert extract_country_from_phone(12345) is None

    def test_extract_country_from_phone_whitespace_only_returns_none(self):
        assert extract_country_from_phone('   ') is None

    def test_extract_country_from_phone_with_leading_trailing_spaces_returns_country(self):
        result = extract_country_from_phone('  +31 20 123 4567  ')
        assert result == 'NL'


# ---------------------------------------------------------------------------
# extract_country_from_booking_addinfo
# ---------------------------------------------------------------------------

class TestExtractCountryFromBookingAddinfo:
    """Tests for extract_country_from_booking_addinfo function."""

    def test_extract_country_from_booking_addinfo_position13_es(self):
        addinfo = 'Booking.com|6438303279|Ruda, Luis|2025-06-26 11:19:30|NA|ok|91.3212 EUR|12|10.958544 EUR|Paid online|NA|NA|NA|es|Leisure|Mobile|Rode huis|1|NA'
        assert extract_country_from_booking_addinfo(addinfo) == 'ES'

    def test_extract_country_from_booking_addinfo_position13_de(self):
        addinfo = 'Booking.com|123|Test|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|de|Business|Desktop|Green|1|NA'
        assert extract_country_from_booking_addinfo(addinfo) == 'DE'

    def test_extract_country_from_booking_addinfo_position19_nl(self):
        # 20 fields (index 19 = 'nl'), position 13 = 'NA' (skipped)
        addinfo = 'Booking.com|123|Test|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|NA|Business|Desktop|Green|1|NA|nl'
        assert extract_country_from_booking_addinfo(addinfo) == 'NL'

    def test_extract_country_from_booking_addinfo_na_at_position13_returns_none(self):
        # Only 14 fields, position 13 = 'NA'
        addinfo = 'Booking.com|456|Short|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|NA'
        assert extract_country_from_booking_addinfo(addinfo) is None

    def test_extract_country_from_booking_addinfo_none_returns_none(self):
        assert extract_country_from_booking_addinfo(None) is None

    def test_extract_country_from_booking_addinfo_empty_returns_none(self):
        assert extract_country_from_booking_addinfo('') is None

    def test_extract_country_from_booking_addinfo_short_string_returns_none(self):
        assert extract_country_from_booking_addinfo('Invalid|format') is None

    def test_extract_country_from_booking_addinfo_non_string_returns_none(self):
        assert extract_country_from_booking_addinfo(12345) is None

    def test_extract_country_from_booking_addinfo_numeric_at_position13_returns_none(self):
        addinfo = 'Booking.com|123|Test|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|42|Business|Desktop|Green|1|NA'
        assert extract_country_from_booking_addinfo(addinfo) is None


# ---------------------------------------------------------------------------
# detect_country
# ---------------------------------------------------------------------------

class TestDetectCountry:
    """Tests for detect_country function."""

    def test_detect_country_airbnb_with_phone_returns_country(self):
        assert detect_country('airbnb', phone='+971 58 260 0953') == 'AE'

    def test_detect_country_airbnb_without_phone_returns_none(self):
        assert detect_country('airbnb') is None

    def test_detect_country_booking_with_addinfo_returns_country(self):
        addinfo = 'Booking.com|123|Test|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|es|Leisure|Mobile|Rode huis|1|NA'
        assert detect_country('booking.com', addinfo=addinfo) == 'ES'

    def test_detect_country_booking_without_addinfo_returns_none(self):
        assert detect_country('booking.com') is None

    def test_detect_country_direct_returns_none(self):
        assert detect_country('direct') is None

    def test_detect_country_empty_channel_returns_none(self):
        assert detect_country('') is None

    def test_detect_country_none_channel_returns_none(self):
        assert detect_country(None) is None

    def test_detect_country_airbnb_case_insensitive(self):
        assert detect_country('AirBnB', phone='+34 612 345 678') == 'ES'

    def test_detect_country_booking_case_insensitive(self):
        addinfo = 'Booking.com|123|Test|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|de|Business|Desktop|Green|1|NA'
        assert detect_country('Booking.com', addinfo=addinfo) == 'DE'

    def test_detect_country_unknown_channel_returns_none(self):
        assert detect_country('vrbo', phone='+1 555 123 4567') is None


# ---------------------------------------------------------------------------
# get_country_name
# ---------------------------------------------------------------------------

class TestGetCountryName:
    """Tests for get_country_name function."""

    def test_get_country_name_ae_returns_name(self):
        result = get_country_name('AE')
        assert result is not None
        assert 'United Arab Emirates' in result or 'UAE' in result

    def test_get_country_name_es_returns_spain(self):
        result = get_country_name('ES')
        assert result is not None
        assert 'Spain' in result

    def test_get_country_name_nl_returns_netherlands(self):
        result = get_country_name('NL')
        assert result is not None
        assert 'Netherlands' in result

    def test_get_country_name_none_returns_none(self):
        assert get_country_name(None) is None

    def test_get_country_name_empty_returns_none(self):
        assert get_country_name('') is None

    def test_get_country_name_single_char_returns_none(self):
        assert get_country_name('A') is None

    def test_get_country_name_three_chars_returns_none(self):
        assert get_country_name('ABC') is None

    def test_get_country_name_lowercase_returns_name(self):
        result = get_country_name('us')
        assert result is not None
        assert 'United States' in result

    def test_get_country_name_pycountry_unavailable_uses_fallback(self):
        """Test fallback dict is used when pycountry import fails."""
        # pycountry is not installed, so the bare except always triggers
        # and the fallback dict is used
        result = get_country_name('DE')
        assert result == 'Germany'

    def test_get_country_name_fallback_unknown_code_returns_none(self):
        """Test fallback dict returns None for unknown country code."""
        # pycountry not installed, fallback dict doesn't have 'XX'
        result = get_country_name('XX')
        assert result is None

    def test_get_country_name_pycountry_returns_none_uses_fallback(self):
        """Test fallback dict for various known codes."""
        # Since pycountry is not installed, all lookups use the fallback dict
        assert get_country_name('FR') == 'France'
        assert get_country_name('IT') == 'Italy'
        assert get_country_name('BE') == 'Belgium'

    def test_get_country_name_fallback_covers_all_common_countries(self):
        """Test that the fallback dict covers common country codes."""
        # These all hit the fallback dict (lines 243-281)
        assert get_country_name('CH') == 'Switzerland'
        assert get_country_name('AT') == 'Austria'
        assert get_country_name('PT') == 'Portugal'
        assert get_country_name('SE') == 'Sweden'
        assert get_country_name('NO') == 'Norway'
        assert get_country_name('DK') == 'Denmark'
        assert get_country_name('FI') == 'Finland'
        assert get_country_name('PL') == 'Poland'
        assert get_country_name('JP') == 'Japan'
        assert get_country_name('AU') == 'Australia'
        assert get_country_name('BR') == 'Brazil'
        assert get_country_name('SA') == 'Saudi Arabia'
        assert get_country_name('IL') == 'Israel'

    def test_get_country_name_pycountry_success_path(self):
        """Test the try block when pycountry is available (lines 193-194)."""
        import sys
        # Create a mock pycountry module
        mock_pycountry = MagicMock()
        mock_country = MagicMock()
        mock_country.name = 'Netherlands'
        mock_pycountry.countries.get.return_value = mock_country
        
        # Temporarily inject mock pycountry into sys.modules
        original = sys.modules.get('pycountry')
        sys.modules['pycountry'] = mock_pycountry
        try:
            result = get_country_name('NL')
            assert result == 'Netherlands'
        finally:
            if original is None:
                del sys.modules['pycountry']
            else:
                sys.modules['pycountry'] = original


# ---------------------------------------------------------------------------
# Additional edge case tests for coverage
# ---------------------------------------------------------------------------

class TestExtractCountryFromPhoneEdgeCases:
    """Additional edge case tests for extract_country_from_phone."""

    def test_extract_country_from_phone_region_code_for_country_code_fallback(self):
        """Test fallback to region_code_for_country_code when region_code_for_number returns None."""
        with patch('country_detector.phonenumbers.parse') as mock_parse:
            with patch('country_detector.phonenumbers.region_code_for_number', return_value=None):
                with patch('country_detector.phonenumbers.region_code_for_country_code', return_value='NL'):
                    mock_parsed = MagicMock()
                    mock_parsed.country_code = 31
                    mock_parse.return_value = mock_parsed
                    result = extract_country_from_phone('+31 20 123 4567')
        assert result == 'NL'

    def test_extract_country_from_phone_both_region_lookups_fail_returns_none(self):
        """Test that when both region lookups fail, None is returned (line 61)."""
        with patch('country_detector.phonenumbers.parse') as mock_parse:
            with patch('country_detector.phonenumbers.region_code_for_number', return_value=None):
                with patch('country_detector.phonenumbers.region_code_for_country_code', return_value='001'):
                    # '001' is 3 chars, fails len(region) == 2 check
                    mock_parsed = MagicMock()
                    mock_parsed.country_code = 1
                    mock_parse.return_value = mock_parsed
                    result = extract_country_from_phone('+1 555 123 4567')
        assert result is None

    def test_extract_country_from_phone_number_parse_exception(self):
        """Test NumberParseException handler returns None."""
        with patch('country_detector.phonenumbers.parse') as mock_parse:
            from phonenumbers import NumberParseException
            mock_parse.side_effect = NumberParseException(0, "Invalid number")
            result = extract_country_from_phone('+999 invalid')
        assert result is None

    def test_extract_country_from_phone_generic_exception(self):
        """Test generic exception handler returns None."""
        with patch('country_detector.phonenumbers.parse') as mock_parse:
            mock_parse.side_effect = RuntimeError("Unexpected error")
            result = extract_country_from_phone('+31 20 123 4567')
        assert result is None


class TestExtractCountryFromBookingAddinfoEdgeCases:
    """Additional edge case tests for extract_country_from_booking_addinfo."""

    def test_extract_country_from_booking_addinfo_generic_exception(self):
        """Test generic exception handler returns None."""
        # The function has a broad except at lines 113-115
        # We trigger it by mocking the split method to raise inside the try block
        class FakeStr(str):
            def split(self, *args, **kwargs):
                raise RuntimeError("Forced error")

        # The isinstance check passes because FakeStr inherits from str
        fake_input = FakeStr('some|data|here')
        result = extract_country_from_booking_addinfo(fake_input)
        assert result is None


class TestDetectCountryEdgeCases:
    """Additional edge case tests for detect_country."""

    def test_detect_country_other_channel_logs_debug(self):
        """Test that 'other' channels trigger debug log and return None."""
        # This covers lines 193-194 (the else branch with logger.debug)
        result = detect_country('vrbo', phone='+1 555 123 4567')
        assert result is None

    def test_detect_country_expedia_returns_none(self):
        """Test that expedia channel (not airbnb/booking) returns None."""
        result = detect_country('expedia', phone='+44 20 7946 0958')
        assert result is None

    def test_detect_country_direct_with_addinfo_returns_none(self):
        """Test that direct channel ignores addinfo."""
        addinfo = 'Booking.com|123|Test|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|de|Business|Desktop|Green|1|NA'
        result = detect_country('direct', addinfo=addinfo)
        assert result is None
