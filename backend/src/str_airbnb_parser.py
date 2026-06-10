"""
Airbnb-specific STR file parsing.

Handles processing of Airbnb CSV reservation exports including:
- Multi-file import with deduplication by Bevestigingscode
- Dutch column name mapping
- European currency format parsing (€ 1.234,56)
- Financial calculations (gross, channel fee, VAT, tourist tax, net)
"""

import os
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional

from country_detector import detect_country
from str_utils import calculate_str_taxes, normalize_listing_name


def process_airbnb_multi(file_paths: List[str], tax_rate_service=None,
                         tenant: str = None) -> List[Dict]:
    """
    Process multiple Airbnb CSV files: read, concatenate, deduplicate, calculate.

    Args:
        file_paths: List of paths to Airbnb CSV files
        tax_rate_service: Optional TaxRateService for dynamic tax rates
        tenant: Optional tenant identifier

    Returns:
        List of booking dicts with financial calculations applied

    Raises:
        ValueError: If all files fail to parse
    """
    dfs = []
    failed_files = []

    for fp in file_paths:
        try:
            df = pd.read_csv(fp)
            dfs.append(df)
            print(f"Airbnb multi-import: loaded {len(df)} rows from {os.path.basename(fp)}")
        except Exception as e:
            failed_files.append(os.path.basename(fp))
            print(f"Airbnb multi-import: failed to parse {os.path.basename(fp)}: {e}")

    if not dfs:
        raise ValueError(f"All files failed to parse: {', '.join(failed_files)}")

    # Concatenate all DataFrames
    combined = pd.concat(dfs, ignore_index=True)
    print(f"Airbnb multi-import: {len(combined)} total rows from {len(dfs)} file(s)")

    # Deduplicate by Bevestigingscode, keeping the last occurrence
    if 'Bevestigingscode' in combined.columns:
        before_dedup = len(combined)
        combined = combined.drop_duplicates(subset='Bevestigingscode', keep='last')
        print(f"Airbnb multi-import: deduplicated {before_dedup} -> {len(combined)} rows (by Bevestigingscode)")

    # Determine sourceFile label
    today_str = datetime.now().strftime('%Y-%m-%d')
    if len(file_paths) > 1:
        source_file = f"{today_str} multi-import ({len(file_paths)} files)"
    else:
        source_file = f"{today_str} {os.path.basename(file_paths[0])}"

    # Process each row through the Airbnb algorithm
    transactions = []
    for _, row in combined.iterrows():
        booking = calculate_airbnb_row(row, combined.columns, source_file,
                                       tax_rate_service, tenant)
        if booking is not None:
            transactions.append(booking)

    if failed_files:
        print(f"Airbnb multi-import: WARNING - failed files: {', '.join(failed_files)}")

    print(f"Airbnb multi-import: {len(transactions)} transactions from {len(file_paths)} file(s)")
    return transactions


def calculate_airbnb_row(row, df_columns, source_file: str,
                         tax_rate_service=None, tenant: str = None) -> Optional[Dict]:
    """
    Process a single Airbnb row into a booking dict.

    Args:
        row: A pandas Series representing one booking row
        df_columns: The columns of the source DataFrame (for addInfo)
        source_file: The sourceFile label to attach
        tax_rate_service: Optional TaxRateService for dynamic tax rates
        tenant: Optional tenant identifier

    Returns:
        Booking dict or None if the row should be skipped
    """
    # Map Dutch AirBnB columns
    checkin_date = row.get('Begindatum', '')
    checkout_date = row.get('Einddatum', '')
    guest_name = row.get('Naam van de gast', '')
    listing = row.get('Advertentie', '')
    nights = row.get('# nachten', 0)
    earnings_str = row.get('Inkomsten', '€ 0,00')
    booking_id = row.get('Bevestigingscode', '')
    status = row.get('Status', 'Bevestigd')
    phone = row.get('Contact', '')
    adults = row.get('# volwassenen', 0) or 0
    children = row.get('# kinderen', 0) or 0
    babies = row.get("# baby's", 0) or 0
    reservation_date = row.get('Gereserveerd', '')

    # Parse earnings "€ 190,10" or "€ 1.841,18" format like R getAmount() function
    try:
        if pd.isna(earnings_str) or earnings_str == '':
            earnings = 0
        else:
            # Remove € symbol and spaces
            clean_amount = str(earnings_str).replace('€', '').replace(' ', '')
            # Handle European format: thousands separator (.) and decimal separator (,)
            if ',' in clean_amount:
                # Split on comma to separate decimal part
                parts = clean_amount.split(',')
                if len(parts) == 2:
                    # Remove dots from integer part (thousands separator)
                    integer_part = parts[0].replace('.', '')
                    decimal_part = parts[1]
                    clean_amount = f"{integer_part}.{decimal_part}"
                else:
                    clean_amount = clean_amount.replace(',', '.')
            earnings = float(clean_amount) if clean_amount else 0
    except (ValueError, TypeError):
        earnings = 0

    # Skip cancelled bookings with no earnings (like R code filter)
    if 'Geannuleerd' in status and earnings == 0:
        return None

    # Determine booking status
    today = date.today()
    try:
        checkin_dt = datetime.strptime(checkin_date, '%d-%m-%Y').date()
        if 'Geannuleerd' in status:
            booking_status = 'cancelled'
        elif checkin_dt > today:
            booking_status = 'planned'
        else:
            booking_status = 'realised'
    except:
        booking_status = 'realised'

    # Calculate financial amounts like R code
    # AirBnB "Inkomsten" is the paid out amount
    paid_out = earnings
    channel_fee_factor = 0.15  # 15% like R code
    amount_channel_fee = paid_out * channel_fee_factor
    gross_amount = paid_out + amount_channel_fee  # R: amountGross = paidOut + amountChannelFee

    # Use generic tax calculation function
    tax_calc = calculate_str_taxes(gross_amount, checkin_date, amount_channel_fee,
                                   tax_rate_service, tenant)
    amount_vat = tax_calc['amount_vat']
    amount_tourist_tax = tax_calc['amount_tourist_tax']
    amount_nett = tax_calc['amount_nett']

    # Calculate dates and periods
    try:
        checkin_dt = datetime.strptime(checkin_date, '%d-%m-%Y')
        checkout_dt = datetime.strptime(checkout_date, '%d-%m-%Y')
        reservation_dt = datetime.strptime(reservation_date, '%Y-%m-%d')

        year = checkin_dt.year
        quarter = (checkin_dt.month - 1) // 3 + 1
        month = checkin_dt.month
        days_before_reservation = (checkin_dt - reservation_dt).days
    except:
        year = datetime.now().year
        quarter = 1
        month = 1
        days_before_reservation = 0
        reservation_dt = datetime.now()

    # Price per night based on net amount
    price_per_night = amount_nett / nights if nights > 0 else 0

    # Total guests
    guests = adults + children + babies

    # Additional info - concatenate all CSV fields with |
    add_info = '|'.join(str(row.get(col, '')) for col in df_columns)

    # Detect country from phone number (AirBNB)
    country = detect_country('airbnb', phone=phone, addinfo=add_info)

    return {
        'sourceFile': source_file,
        'channel': 'airbnb',
        'listing': normalize_listing_name(str(listing)),
        'checkinDate': checkin_dt.strftime('%Y-%m-%d'),
        'checkoutDate': checkout_dt.strftime('%Y-%m-%d'),
        'nights': int(nights) if nights else 0,
        'guests': int(guests),
        'amountGross': round(float(gross_amount), 2),
        'amountChannelFee': round(float(amount_channel_fee), 2),
        'guestName': str(guest_name),
        'phone': str(phone),
        'reservationCode': str(booking_id),
        'reservationDate': reservation_dt.strftime('%Y-%m-%d'),
        'status': str(booking_status),
        'addInfo': add_info,
        'amountVat': amount_vat,  # Already rounded in calculate_str_taxes()
        'amountTouristTax': amount_tourist_tax,  # Already rounded in calculate_str_taxes()
        'amountNett': amount_nett,  # Already rounded in calculate_str_taxes()
        'pricePerNight': round(float(price_per_night), 2),
        'year': year,
        'q': quarter,
        'm': month,
        'daysBeforeReservation': days_before_reservation,
        'country': country,
    }
