"""
Guesty Direct (dfDirect) STR CSV parsing.

Handles processing of Guesty CSV reservation exports for dfDirect channel including:
- Header validation for 13 required columns
- Date parsing for "YYYY-MM-DD HH:MM AM/PM" and "YYYY-MM-DD" formats
- Status filtering (only "confirmed" rows processed)
- Financial calculations (4% channel fee, VAT, tourist tax)
- Field mapping to standard booking record format
- Duplicate detection support via reservationCode
"""

import calendar
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from country_detector import detect_country
from str_utils import calculate_str_taxes, normalize_listing_name

# All 13 required columns in the Guesty CSV export
REQUIRED_COLUMNS = [
    "CHECK-IN",
    "CHECK-OUT",
    "CONFIRMATION CODE",
    "LISTING",
    "GUEST",
    "CREATION DATE",
    "NUMBER OF NIGHTS",
    "NUMBER OF GUESTS",
    "STATUS",
    "BALANCE DUE",
    "TOTAL PAID",
    "TOTAL PAYOUT",
    "PLATFORM",
]


def _validate_headers(df_columns: list[str]) -> list[str]:
    """
    Validate that all 13 required columns are present.

    Comparison is case-insensitive and ignores leading/trailing whitespace
    in the actual column names.

    Args:
        df_columns: List of column names from the parsed DataFrame.

    Returns:
        List of missing column names (from REQUIRED_COLUMNS).
        Empty list means all required columns are present.
    """
    # Normalize actual columns: strip whitespace and lowercase
    normalized_actual = {col.strip().lower() for col in df_columns}

    missing = []
    for required_col in REQUIRED_COLUMNS:
        if required_col.strip().lower() not in normalized_actual:
            missing.append(required_col)

    return missing


def _parse_guesty_date(date_str: str) -> str | None:
    """
    Parse Guesty date format and extract the date portion.

    Supports two formats:
    - "YYYY-MM-DD HH:MM AM/PM" (e.g., "2026-06-12 02:00 PM") → "2026-06-12"
    - "YYYY-MM-DD" (e.g., "2026-06-12") → "2026-06-12"

    Validates the extracted date is a real calendar date (month ≤ 12,
    day ≤ days-in-month accounting for leap years).

    Args:
        date_str: The raw date string from the CSV.

    Returns:
        Date string in "YYYY-MM-DD" format, or None if the input is
        empty, invalid, or cannot be parsed.
    """
    if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)):
        return None

    # Convert to string and strip whitespace
    cleaned = str(date_str).strip()
    if not cleaned:
        return None

    # Pattern 1: "YYYY-MM-DD HH:MM AM/PM"
    match = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})\s+\d{1,2}:\d{2}\s*[AaPp][Mm]$", cleaned
    )
    if match:
        year_str, month_str, day_str = match.group(1), match.group(2), match.group(3)
        return _validate_date_parts(year_str, month_str, day_str)

    # Pattern 2: "YYYY-MM-DD" (plain date)
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", cleaned)
    if match:
        year_str, month_str, day_str = match.group(1), match.group(2), match.group(3)
        return _validate_date_parts(year_str, month_str, day_str)

    # No pattern matched
    return None


def _validate_date_parts(year_str: str, month_str: str, day_str: str) -> str | None:
    """
    Validate that year/month/day form a real calendar date.

    Args:
        year_str: 4-digit year string
        month_str: 2-digit month string
        day_str: 2-digit day string

    Returns:
        "YYYY-MM-DD" string if valid, None otherwise.
    """
    try:
        year = int(year_str)
        month = int(month_str)
        day = int(day_str)
    except ValueError:
        return None

    # Month must be 1-12
    if month < 1 or month > 12:
        return None

    # Day must be valid for the given month/year (handles leap years)
    max_day = calendar.monthrange(year, month)[1]
    if day < 1 or day > max_day:
        return None

    return f"{year_str}-{month_str}-{day_str}"


def _calculate_direct_row(
    row: "pd.Series",
    col_map: dict[str, str],
    source_file: str,
    row_number: int,
    tax_rate_service=None,
    tenant: str | None = None,
) -> dict | None:
    """
    Process a single Guesty CSV row into a booking dict.

    Returns None if the row should be skipped (with reason logged).
    Returns a dict with key "_skip_reason" if the row is skipped,
    allowing the caller to track skip reasons in the summary.

    Args:
        row: A pandas Series representing one CSV row.
        col_map: Mapping of normalized column names to actual DataFrame column names.
        source_file: The sourceFile label to attach.
        row_number: 1-based row number (excluding header) for error reporting.
        tax_rate_service: Optional TaxRateService for dynamic tax rates.
        tenant: Optional tenant identifier.

    Returns:
        Booking dict on success, or dict with "_skip_reason" key on skip.
    """
    # Helper to get a trimmed string value from the row
    def _get_str(col_key: str) -> str:
        actual_col = col_map.get(col_key, "")
        if not actual_col:
            return ""
        val = row.get(actual_col, "")
        if pd.isna(val):
            return ""
        return str(val).strip()

    # Get confirmation code early for logging
    confirmation_code = _get_str("confirmation code")

    # --- Status filtering ---
    status_val = _get_str("status")
    if not status_val or status_val.lower() != "confirmed":
        return {"_skip_reason": "non_confirmed_status"}

    # --- Validate TOTAL PAYOUT ---
    payout_str = _get_str("total payout")
    try:
        payout_decimal = Decimal(payout_str)
    except Exception:  # noqa: BLE001
        print(
            f"Warning: Row {row_number} ({confirmation_code}): "
            f"non-numeric TOTAL PAYOUT '{payout_str}', skipping.",
            flush=True,
        )
        return {"_skip_reason": "invalid_payout"}

    if payout_decimal <= 0:
        return {"_skip_reason": "zero_or_negative_payout"}

    # Round gross to 2dp using half-up
    amount_gross = float(
        payout_decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )

    # --- Validate NUMBER OF NIGHTS ---
    nights_str = _get_str("number of nights")
    try:
        nights = int(float(nights_str)) if nights_str else 0
    except (ValueError, TypeError):
        nights = 0

    if nights <= 0:
        print(
            f"Warning: Row {row_number} ({confirmation_code}): "
            f"zero or missing NUMBER OF NIGHTS, skipping.",
            flush=True,
        )
        return {"_skip_reason": "zero_nights"}

    # --- Parse dates ---
    checkin_str = _get_str("check-in")
    checkout_str = _get_str("check-out")
    creation_str = _get_str("creation date")

    checkin_date = _parse_guesty_date(checkin_str)
    checkout_date = _parse_guesty_date(checkout_str)
    reservation_date = _parse_guesty_date(creation_str)

    if not checkin_date:
        print(
            f"Warning: Row {row_number} ({confirmation_code}): "
            f"unparsable CHECK-IN date '{checkin_str}', skipping.",
            flush=True,
        )
        return {"_skip_reason": "unparsable_date"}

    if not checkout_date:
        print(
            f"Warning: Row {row_number} ({confirmation_code}): "
            f"unparsable CHECK-OUT date '{checkout_str}', skipping.",
            flush=True,
        )
        return {"_skip_reason": "unparsable_date"}

    if not reservation_date:
        print(
            f"Warning: Row {row_number} ({confirmation_code}): "
            f"unparsable CREATION DATE '{creation_str}', skipping.",
            flush=True,
        )
        return {"_skip_reason": "unparsable_date"}

    # --- Financial calculations ---
    # Channel fee: 4% of gross, half-up rounding to 2dp
    amount_channel_fee = float(
        (payout_decimal * Decimal("0.04"))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )

    # Tax calculation
    tax_calc = calculate_str_taxes(
        amount_gross, checkin_date, amount_channel_fee, tax_rate_service, tenant
    )
    amount_vat = tax_calc["amount_vat"]
    amount_tourist_tax = tax_calc["amount_tourist_tax"]
    amount_nett = tax_calc["amount_nett"]

    # Price per night
    price_per_night = round(amount_nett / nights, 2) if nights > 0 else 0

    # --- Derive date-based fields ---
    try:
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d").date()  # noqa: DTZ007
        reservation_dt = datetime.strptime(reservation_date, "%Y-%m-%d").date()  # noqa: DTZ007
        year = checkin_dt.year
        quarter = (checkin_dt.month - 1) // 3 + 1
        month = checkin_dt.month
        days_before_reservation = (checkin_dt - reservation_dt).days
    except Exception:  # noqa: BLE001
        year = datetime.now().year  # noqa: DTZ005
        quarter = 1
        month = 1
        days_before_reservation = 0
        checkin_dt = date.today()  # noqa: DTZ011

    # --- Booking status ---
    today = date.today()  # noqa: DTZ011
    if checkin_dt > today:
        booking_status = "planned"
    else:
        booking_status = "realised"

    # --- Field mapping ---
    listing_raw = _get_str("listing")
    listing = normalize_listing_name(listing_raw)
    guest_name = _get_str("guest")

    # Number of guests
    guests_str = _get_str("number of guests")
    try:
        guests = int(float(guests_str)) if guests_str else 0
    except (ValueError, TypeError):
        guests = 0

    # addInfo: "{confirmation_code} | {guest_name} | {listing}"
    add_info = f"{confirmation_code} | {guest_name} | {listing_raw}"

    # Country detection
    country = detect_country("dfDirect", phone="", addinfo=guest_name)

    return {
        "sourceFile": source_file,
        "channel": "dfDirect",
        "listing": listing,
        "checkinDate": checkin_date,
        "checkoutDate": checkout_date,
        "nights": nights,
        "guests": guests,
        "amountGross": amount_gross,
        "amountChannelFee": amount_channel_fee,
        "guestName": guest_name,
        "phone": "",
        "reservationCode": confirmation_code,
        "reservationDate": reservation_date,
        "status": booking_status,
        "addInfo": add_info,
        "amountVat": amount_vat,
        "amountTouristTax": amount_tourist_tax,
        "amountNett": amount_nett,
        "pricePerNight": price_per_night,
        "year": year,
        "q": quarter,
        "m": month,
        "daysBeforeReservation": days_before_reservation,
        "country": country,
    }


def process_direct_csv(
    file_path: str,
    tax_rate_service=None,
    tenant: str | None = None,
) -> dict:
    """
    Parse a Guesty CSV export for dfDirect channel.

    Orchestrates: CSV read → header validation → row iteration →
    result collection (bookings, status_updates, summary).

    Args:
        file_path: Path to the uploaded CSV file.
        tax_rate_service: Optional TaxRateService for dynamic tax rates.
        tenant: Optional tenant identifier.

    Returns:
        dict with keys:
            - bookings: list[dict] — processed booking records
            - status_updates: list[dict] — non-confirmed rows with reservationCode
            - summary: dict — processing statistics
                - total_rows: int
                - processed_count: int
                - skipped_count: int
                - skipped_reasons: dict[str, int]
    """
    import os

    # --- Read CSV ---
    try:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Failed to parse CSV: {e}") from e

    # --- Build column map (normalized lowercase/stripped → actual column name) ---
    col_map = {col.strip().lower(): col for col in df.columns}

    # --- Validate headers ---
    missing = _validate_headers(df.columns.tolist())
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    # --- Build sourceFile label ---
    today_str = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    source_file = f"{today_str} {os.path.basename(file_path)}"

    # --- Iterate rows and collect results ---
    bookings: list[dict] = []
    status_updates: list[dict] = []
    skipped_reasons: dict[str, int] = {}
    total_rows = len(df)

    for idx, row in df.iterrows():
        row_number = int(idx) + 1  # 1-based row number (excluding header)

        result = _calculate_direct_row(
            row=row,
            col_map=col_map,
            source_file=source_file,
            row_number=row_number,
            tax_rate_service=tax_rate_service,
            tenant=tenant,
        )

        if result is None:
            # Shouldn't happen with current implementation, but handle defensively
            skipped_reasons["unknown"] = skipped_reasons.get("unknown", 0) + 1
            continue

        if "_skip_reason" in result:
            reason = result["_skip_reason"]
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

            # For non-confirmed rows with a reservation code, collect as status_update
            if reason == "non_confirmed_status":
                # Get reservation code from the row
                confirmation_col = col_map.get("confirmation code", "")
                reservation_code = ""
                if confirmation_col:
                    val = row.get(confirmation_col, "")
                    if val and str(val).strip():
                        reservation_code = str(val).strip()

                if reservation_code:
                    # Get the original status value from the row
                    status_col = col_map.get("status", "")
                    status_val = ""
                    if status_col:
                        val = row.get(status_col, "")
                        if val:
                            status_val = str(val).strip()

                    status_updates.append({
                        "reservationCode": reservation_code,
                        "status": status_val,
                    })
        else:
            # Normal booking dict
            bookings.append(result)

    skipped_count = sum(skipped_reasons.values())

    return {
        "bookings": bookings,
        "status_updates": status_updates,
        "summary": {
            "total_rows": total_rows,
            "processed_count": len(bookings),
            "skipped_count": skipped_count,
            "skipped_reasons": skipped_reasons,
        },
    }
