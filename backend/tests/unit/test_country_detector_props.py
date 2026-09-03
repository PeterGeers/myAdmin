"""
Property-based tests for country_detector module.

Uses Hypothesis to verify correctness properties from the design document.
Feature: missing-py-tests, Property 2: Phone Number Country Extraction

Requirements: 3.2
Reference: .kiro/specs/missing-py-tests/design.md
"""

import phonenumbers
import pytest
from hypothesis import given, strategies as st, settings

from country_detector import extract_country_from_phone


# Known country calling codes mapped to ISO 3166-1 alpha-2 codes
COUNTRY_CODES = {
    '1': 'US',      # US/Canada
    '7': 'RU',      # Russia
    '31': 'NL',     # Netherlands
    '32': 'BE',     # Belgium
    '33': 'FR',     # France
    '34': 'ES',     # Spain
    '39': 'IT',     # Italy
    '44': 'GB',     # United Kingdom
    '49': 'DE',     # Germany
    '61': 'AU',     # Australia
    '81': 'JP',     # Japan
    '86': 'CN',     # China
    '91': 'IN',     # India
    '971': 'AE',    # UAE
    '972': 'IL',    # Israel
    '46': 'SE',     # Sweden
    '47': 'NO',     # Norway
    '48': 'PL',     # Poland
    '55': 'BR',     # Brazil
    '52': 'MX',     # Mexico
}

# All valid ISO 3166-1 alpha-2 region codes, sourced from the authoritative
# set the function itself uses (phonenumbers.SUPPORTED_REGIONS, ~245 codes).
# This includes region codes like IM, GG, JE that the phonenumbers library
# returns for certain calling codes.
VALID_ISO_CODES = set(phonenumbers.SUPPORTED_REGIONS)


# Strategy: generate valid E.164 phone numbers from known country codes
@st.composite
def valid_e164_phone(draw):
    """Generate a valid E.164 formatted phone number with a known country code."""
    calling_code = draw(st.sampled_from(list(COUNTRY_CODES.keys())))
    # Generate 6-10 digit subscriber number
    subscriber_digits = draw(st.integers(min_value=100000, max_value=9999999999))
    return f'+{calling_code}{subscriber_digits}'


# ---------------------------------------------------------------------------
# Property 2: Phone Number Country Extraction
# Feature: missing-py-tests, Property 2: Phone Number Country Extraction
# Validates: Requirements 3.2
# ---------------------------------------------------------------------------

class TestPhoneNumberCountryExtraction:
    """
    Property 2: Phone Number Country Extraction

    For any valid E.164 formatted phone number with a known country calling code,
    extract_country_from_phone SHALL return a valid 2-letter ISO 3166-1 alpha-2
    country code or None (never an invalid code, never an exception).

    Feature: missing-py-tests, Property 2: Phone Number Country Extraction
    **Validates: Requirements 3.2**
    """

    @settings(max_examples=100)
    @given(phone=valid_e164_phone())
    def test_valid_e164_returns_valid_iso_code_or_none(self, phone):
        """
        Feature: missing-py-tests, Property 2: Phone Number Country Extraction

        For any valid E.164 phone number, the result is always a valid
        2-letter ISO country code or None — never an exception.
        """
        result = extract_country_from_phone(phone)

        # Result must be None or a valid 2-letter ISO code
        if result is not None:
            assert isinstance(result, str), f"Expected str, got {type(result)}"
            assert len(result) == 2, f"Expected 2-char code, got '{result}'"
            assert result == result.upper(), f"Expected uppercase, got '{result}'"
            assert result in VALID_ISO_CODES, f"'{result}' is not a valid ISO code"

    @settings(max_examples=100)
    @given(text=st.text(max_size=50))
    def test_arbitrary_input_never_raises(self, text):
        """
        Feature: missing-py-tests, Property 2: Phone Number Country Extraction

        For any arbitrary string input, extract_country_from_phone never raises
        an exception — it returns a valid code or None.
        """
        result = extract_country_from_phone(text)

        if result is not None:
            assert isinstance(result, str)
            assert len(result) == 2
            assert result == result.upper()
