"""
Country Detection Utility for Guest Bookings

This module provides functions to detect guest country of origin from various data sources:
- Phone numbers (AirBNB)
- Booking.com addInfo field
- Other channels (fallback to None)
"""

import phonenumbers
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def extract_country_from_phone(phone: str) -> Optional[str]:
    """
    Extract ISO 3166-1 alpha-2 country code from international phone number.
    
    Args:
        phone: Phone number in international format (e.g., '+971 58 260 0953')
        
    Returns:
        Two-letter country code (e.g., 'AE' for UAE, 'ES' for Spain) or None if parsing fails
        
    Examples:
        >>> extract_country_from_phone('+971 58 260 0953')
        'AE'
        >>> extract_country_from_phone('+34 123 456 789')
        'ES'
        >>> extract_country_from_phone('+1 555 123 4567')
        'US'
    """
    if not phone or not isinstance(phone, str):
        return None
    
    try:
        # Clean up phone number - remove extra spaces
        phone_clean = phone.strip()
        
        # Parse phone number (None means no default region)
        parsed = phonenumbers.parse(phone_clean, None)
        
        # Get country code - don't validate if number is real, just extract the country
        # This is more lenient and works even with test/invalid numbers
        country_code = phonenumbers.region_code_for_number(parsed)
        
        # Validate it's a valid country code (2 letters)
        if country_code and len(country_code) == 2:
            return country_code
        
        # If region_code_for_number returns None, try to get it from country code
        # This handles cases where the number format is recognized but not fully valid
        if parsed and parsed.country_code:
            # Map numeric country code to ISO alpha-2
            region = phonenumbers.region_code_for_country_code(parsed.country_code)
            if region and len(region) == 2:
                return region
        
        return None
        
    except phonenumbers.NumberParseException as e:
        logger.debug(f"Could not parse phone number '{phone}': {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error parsing phone number '{phone}': {e}")
        return None


def extract_country_from_booking_addinfo(addinfo: str) -> Optional[str]:
    """
    Extract country code from Booking.com addInfo field.
    
    The addInfo field contains pipe-separated values. The country code position varies:
    - Older format: position 13
    - Newer format: position 19
    
    Args:
        addinfo: Pipe-separated string from Booking.com export
        
    Returns:
        Two-letter country code or None if not found/invalid
        
    Example:
        >>> addinfo = 'Booking.com|6438303279|Ruda, Luis|2025-06-26 11:19:30|NA|ok|91.3212 EUR|12|10.958544 EUR|Paid online|NA|NA|NA|es|Leisure|Mobile|Rode huis|1|NA'
        >>> extract_country_from_booking_addinfo(addinfo)
        'ES'
    """
    if not addinfo or not isinstance(addinfo, str):
        return None
    
    try:
        # Split by pipe separator
        fields = addinfo.split('|')
        
        # Try position 19 first (newer format)
        if len(fields) > 19:
            country = fields[19].strip().lower()
            # Validate: should be 2 characters and not 'NA' or empty or numeric
            if country and len(country) == 2 and country.lower() not in ['na', 'n/a', '--'] and not country.isdigit():
                return country.upper()
        
        # Fallback to position 13 (older format)
        if len(fields) > 13:
            country = fields[13].strip().lower()
            # Validate: should be 2 characters and not 'NA' or empty or numeric
            if country and len(country) == 2 and country.lower() not in ['na', 'n/a', '--'] and not country.isdigit():
                return country.upper()
        
        return None
        
    except Exception as e:
        logger.warning(f"Error parsing Booking.com addInfo: {e}")
        return None


def detect_country(channel: str, phone: str = None, addinfo: str = None) -> Optional[str]:
    """
    Detect guest country based on booking channel and available data.
    
    Detection strategy:
    - AirBNB: Use phone number
    - Booking.com: Use addInfo field
    - Other channels: Return None
    
    Args:
        channel: Booking channel (e.g., 'airbnb', 'booking.com', 'direct')
        phone: Phone number (optional, used for AirBNB)
        addinfo: Additional info field (optional, used for Booking.com)
        
    Returns:
        Two-letter ISO country code or None
        
    Examples:
        >>> detect_country('airbnb', phone='+971 58 260 0953')
        'AE'
        >>> detect_country('booking.com', addinfo='...|es|...')
        'ES'
        >>> detect_country('direct')
        None
    """
    if not channel:
        return None
    
    channel_lower = channel.lower().strip()
    
    # AirBNB: Extract from phone number
    if 'airbnb' in channel_lower:
        if phone:
            country = extract_country_from_phone(phone)
            if country:
                logger.debug(f"Detected country '{country}' from AirBNB phone: {phone}")
                return country
    
    # Booking.com: Extract from addInfo
    elif 'booking' in channel_lower:
        if addinfo:
            country = extract_country_from_booking_addinfo(addinfo)
            if country:
                logger.debug(f"Detected country '{country}' from Booking.com addInfo")
                return country
    
    # Other channels: No detection method available
    else:
        logger.debug(f"No country detection method for channel: {channel}")
    
    return None


def get_country_name(country_code: str) -> Optional[str]:
    """
    Get full country name from ISO country code.
    
    Args:
        country_code: Two-letter ISO 3166-1 alpha-2 code
        
    Returns:
        Full country name or None
        
    Example:
        >>> get_country_name('AE')
        'United Arab Emirates'
        >>> get_country_name('ES')
        'Spain'
    """
    if not country_code or len(country_code) != 2:
        return None
    
    try:
        # Use phonenumbers library to get country name
        import pycountry
        country = pycountry.countries.get(alpha_2=country_code.upper())
        return country.name if country else None
    except:
        # Fallback: basic mapping for common countries
        country_names = {
            'AE': 'United Arab Emirates',
            'ES': 'Spain',
            'US': 'United States',
            'GB': 'United Kingdom',
            'DE': 'Germany',
            'FR': 'France',
            'IT': 'Italy',
            'NL': 'Netherlands',
            'BE': 'Belgium',
            'CH': 'Switzerland',
            'AT': 'Austria',
            'PT': 'Portugal',
            'SE': 'Sweden',
            'NO': 'Norway',
            'DK': 'Denmark',
            'FI': 'Finland',
            'PL': 'Poland',
            'CZ': 'Czech Republic',
            'HU': 'Hungary',
            'RO': 'Romania',
            'BG': 'Bulgaria',
            'GR': 'Greece',
            'TR': 'Turkey',
            'RU': 'Russia',
            'UA': 'Ukraine',
            'CN': 'China',
            'JP': 'Japan',
            'KR': 'South Korea',
            'IN': 'India',
            'AU': 'Australia',
            'NZ': 'New Zealand',
            'CA': 'Canada',
            'MX': 'Mexico',
            'BR': 'Brazil',
            'AR': 'Argentina',
            'ZA': 'South Africa',
            'EG': 'Egypt',
            'SA': 'Saudi Arabia',
            'IL': 'Israel'
        }
        return country_names.get(country_code.upper())


if __name__ == '__main__':
    # Test cases
    print("Testing country detection...")
    
    # Test phone number extraction
    print("\n1. Phone number tests:")
    test_phones = [
        '+971 58 260 0953',  # UAE
        '+34 123 456 789',   # Spain
        '+1 555 123 4567',   # USA
        '+44 20 1234 5678',  # UK
        '+31 20 123 4567',   # Netherlands
        'invalid',           # Invalid
        None                 # None
    ]
    
    for phone in test_phones:
        country = extract_country_from_phone(phone)
        print(f"  {phone} -> {country}")
    
    # Test Booking.com addInfo extraction
    print("\n2. Booking.com addInfo tests:")
    test_addinfo = [
        'Booking.com|6438303279|Ruda, Luis|2025-06-26 11:19:30|NA|ok|91.3212 EUR|12|10.958544 EUR|Paid online|NA|NA|NA|es|Leisure|Mobile|Rode huis|1|NA',
        'Booking.com|123|Test|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|de|Business|Desktop|Green|1|NA',
        'Booking.com|456|Short|2025-01-01|NA|ok|100 EUR|1|10 EUR|Paid|NA|NA|NA|NA|Business|Desktop|Green|1|NA',  # NA country
        'Invalid|format',
        None
    ]
    
    for addinfo in test_addinfo:
        country = extract_country_from_booking_addinfo(addinfo)
        print(f"  {addinfo[:50] if addinfo else None}... -> {country}")
    
    # Test integrated detection
    print("\n3. Integrated detection tests:")
    print(f"  AirBNB with phone: {detect_country('airbnb', phone='+971 58 260 0953')}")
    print(f"  Booking.com with addInfo: {detect_country('booking.com', addinfo=test_addinfo[0])}")
    print(f"  Direct booking: {detect_country('direct')}")
    
    print("\nAll tests completed!")
