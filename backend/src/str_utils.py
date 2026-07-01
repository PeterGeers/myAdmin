"""
Common STR (Short-Term Rental) utility functions.

Shared helpers for tax calculations, date parsing, amount parsing,
and listing name normalization used across all STR platform parsers.
"""

import re
import pandas as pd
from datetime import datetime, date


def get_tax_rates(checkin_date: str, tax_rate_service=None, tenant: str = None) -> dict:
    """Get VAT and tourist tax rates based on check-in date from TaxRateService.

    Args:
        checkin_date: Check-in date in YYYY-MM-DD format
        tax_rate_service: Optional TaxRateService instance for dynamic rate lookup
        tenant: Optional tenant identifier for rate lookup

    Returns:
        dict with vat_rate, vat_base, tourist_tax_rate, tourist_tax_base, price_uplift
    """
    try:
        # Parse check-in date
        if isinstance(checkin_date, str):
            checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d").date()
        else:
            checkin_dt = checkin_date

        if tax_rate_service and tenant:
            # Look up btw_accommodation rate for this date
            btw_rate_info = tax_rate_service.get_tax_rate(
                tenant, "btw_accommodation", "low", checkin_dt
            )
            if not btw_rate_info:
                btw_rate_info = tax_rate_service.get_tax_rate(
                    tenant, "btw_accommodation", "high", checkin_dt
                )

            # Look up tourist_tax rate for this date
            tourist_info = tax_rate_service.get_tax_rate(
                tenant, "tourist_tax", "standard", checkin_dt
            )

            vat_rate = btw_rate_info["rate"] if btw_rate_info else 9.0
            tourist_rate = tourist_info["rate"] if tourist_info else 6.02
        else:
            # Fallback: hardcoded rates when no service available
            rate_change_date = date(2026, 1, 1)
            if checkin_dt >= rate_change_date:
                vat_rate = 21.0
                tourist_rate = 6.9
            else:
                vat_rate = 9.0
                tourist_rate = 6.02

        return {
            "vat_rate": vat_rate,
            "vat_base": 100 + vat_rate,
            "tourist_tax_rate": tourist_rate,
            "tourist_tax_base": 100 + tourist_rate,
            "price_uplift": 0.054409,
        }
    except Exception as e:
        print(f"Error getting tax rates for {checkin_date}: {e}")
        return {
            "vat_rate": 9.0,
            "vat_base": 109.0,
            "tourist_tax_rate": 6.02,
            "tourist_tax_base": 106.02,
            "price_uplift": 0.054409,
        }


def calculate_str_taxes(
    gross_amount: float,
    checkin_date: str,
    channel_fee: float = 0.0,
    tax_rate_service=None,
    tenant: str = None,
) -> dict:
    """
    Generic tax calculation function for all STR channels.

    Args:
        gross_amount: Total gross booking amount
        checkin_date: Check-in date in YYYY-MM-DD or DD-MM-YYYY format
        channel_fee: Channel commission fee (optional)
        tax_rate_service: Optional TaxRateService instance
        tenant: Optional tenant identifier

    Returns:
        dict with calculated amounts: amount_vat, amount_tourist_tax, amount_nett, tax_rates_used
    """
    try:
        # Normalize date format to YYYY-MM-DD for tax rate lookup
        if isinstance(checkin_date, str):
            checkin_date_iso = None
            date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"]

            for fmt in date_formats:
                try:
                    checkin_dt = datetime.strptime(checkin_date, fmt)
                    checkin_date_iso = checkin_dt.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

            if not checkin_date_iso:
                # Fallback to current date if parsing fails
                checkin_date_iso = datetime.now().strftime("%Y-%m-%d")
        else:
            checkin_date_iso = checkin_date.strftime("%Y-%m-%d")

        # Get tax rates based on check-in date
        tax_rates = get_tax_rates(checkin_date_iso, tax_rate_service, tenant)

        # Step 1: Calculate VAT on gross amount
        vat_base = 100 + tax_rates["vat_rate"]  # e.g., 121 for 21% VAT
        amount_vat = (float(gross_amount) / vat_base) * tax_rates["vat_rate"]

        # Step 2: Calculate Tourist Tax on VAT-exclusive amount
        vat_exclusive_amount = float(gross_amount) - amount_vat
        tourist_base = (
            100 + tax_rates["tourist_tax_rate"]
        )  # e.g., 106.9 for 6.9% tourist tax
        amount_tourist_tax = (vat_exclusive_amount / tourist_base) * tax_rates[
            "tourist_tax_rate"
        ]

        # Step 3: Net amount = gross - taxes - channel fee
        amount_nett = (
            float(gross_amount) - amount_tourist_tax - amount_vat - float(channel_fee)
        )

        return {
            "amount_vat": round(amount_vat, 2),
            "amount_tourist_tax": round(amount_tourist_tax, 2),
            "amount_nett": round(amount_nett, 2),
            "tax_rates_used": tax_rates,
            "vat_base": vat_base,
            "tourist_base": tourist_base,
            "vat_exclusive_amount": round(vat_exclusive_amount, 2),
        }

    except Exception as e:
        print(f"Error in tax calculation: {e}")
        # Return zero amounts if calculation fails
        return {
            "amount_vat": 0.0,
            "amount_tourist_tax": 0.0,
            "amount_nett": float(gross_amount) - float(channel_fee),
            "tax_rates_used": get_tax_rates(
                datetime.now().strftime("%Y-%m-%d"), tax_rate_service, tenant
            ),
            "total_tax_base": 115.0,  # Fallback
        }


def normalize_listing_name(listing: str) -> str:
    """Normalize listing names to standard format.

    Args:
        listing: Raw listing name from platform export

    Returns:
        Normalized listing name (Green Studio, Child Friendly, Red Studio, or original)
    """
    if not listing:
        return listing

    # Green Studio: One|groen|Groen|green|Green
    if re.search(r"One|groen|Groen|green|Green", listing):
        return "Green Studio"

    # Child Friendly: ^Apartment$|Tuinhuis|[G|g]arden|[C|c]hild
    if re.search(r"^Apartment$|Tuinhuis|[Gg]arden|[Cc]hild", listing):
        return "Child Friendly"

    # Red Studio: Rode|rode|Red|Rood|rood|red
    if re.search(r"Rode|rode|Red|Rood|rood|red", listing):
        return "Red Studio"

    return listing


def parse_amount(amount_str: str) -> float:
    """
    Parse amount string, stripping currency symbols.
    Handles European (€ 559,36) and US ($559.36) formats.

    Args:
        amount_str: Amount string with optional currency symbol

    Returns:
        Parsed float value, or 0 if parsing fails
    """
    if not amount_str or pd.isna(amount_str):
        return 0
    clean = str(amount_str).replace("€", "").replace("$", "").replace("£", "").strip()
    # European format: 1.234,56 → remove dots, replace comma with dot
    if "," in clean:
        parts = clean.split(",")
        if len(parts) == 2:
            integer_part = parts[0].replace(".", "").replace(" ", "")
            decimal_part = parts[1]
            clean = f"{integer_part}.{decimal_part}"
        else:
            clean = clean.replace(",", ".")
    try:
        return float(clean)
    except (ValueError, TypeError):
        return 0


def parse_multilang_date(date_str: str) -> str:
    """
    Parse multi-language date strings like '8 mei 2026', 'May 8, 2026', '8. Mai 2026'.
    Falls back to parse_date for standard formats.

    Args:
        date_str: Date string in various language formats

    Returns:
        Date in YYYY-MM-DD format
    """
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")

    month_map = {
        # Dutch
        "jan": 1,
        "feb": 2,
        "mrt": 3,
        "apr": 4,
        "mei": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "okt": 10,
        "nov": 11,
        "dec": 12,
        # English
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
        # German
        "januar": 1,
        "februar": 2,
        "märz": 3,
        "mai": 5,
        "juni": 6,
        "juli": 7,
        "oktober": 10,
        "dezember": 12,
        # French
        "janvier": 1,
        "février": 2,
        "mars": 3,
        "avril": 4,
        "juin": 6,
        "juillet": 7,
        "août": 8,
        "septembre": 9,
        "octobre": 10,
        "novembre": 11,
        "décembre": 12,
    }

    # Clean up: remove dots, commas, extra spaces
    clean = str(date_str).strip().replace(".", "").replace(",", "").lower()
    parts = clean.split()

    if len(parts) >= 3:
        # Try "8 mei 2026" or "mei 8 2026" patterns
        for i, part in enumerate(parts):
            if part in month_map:
                month = month_map[part]
                remaining = [p for j, p in enumerate(parts) if j != i]
                try:
                    nums = [int(p) for p in remaining if p.isdigit()]
                    if len(nums) >= 2:
                        day = min(nums)
                        year = max(nums)
                        if year < 100:
                            year += 2000
                        return f"{year}-{month:02d}-{day:02d}"
                except ValueError:
                    pass

    # Fallback to standard date parsing
    return parse_date(date_str)


def parse_date(date_str: str) -> str:
    """Parse various date formats to YYYY-MM-DD.

    Args:
        date_str: Date string in various formats

    Returns:
        Date in YYYY-MM-DD format, or today's date if parsing fails
    """
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")

    # Try common date formats
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]

    for fmt in formats:
        try:
            return datetime.strptime(str(date_str), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return datetime.now().strftime("%Y-%m-%d")
