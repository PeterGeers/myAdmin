"""
Booking.com-specific STR file parsing.

Handles processing of Booking.com exports including:
- Excel (.xls/.xlsx), CSV, and TSV file formats
- Multi-file import with deduplication by Book number
- Commission amount parsing (EUR format)
- Payout CSV processing for financial reconciliation
"""

import os
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional

from country_detector import detect_country
from str_utils import calculate_str_taxes, get_tax_rates, normalize_listing_name


def process_booking(
    file_path: str, tax_rate_service=None, tenant: str = None
) -> List[Dict]:
    """Process Booking.com Excel/CSV export.

    Args:
        file_path: Path to Booking.com export file
        tax_rate_service: Optional TaxRateService for dynamic tax rates
        tenant: Optional tenant identifier

    Returns:
        List of booking dicts with financial calculations
    """
    print(f"Starting booking.com processing for: {file_path}")
    try:
        # Handle both .xls/.xlsx and .csv/.tsv files
        if file_path.endswith((".xls", ".xlsx")):
            print(f"Reading Excel file: {file_path}")
            df = pd.read_excel(file_path)
        elif file_path.endswith(".tsv"):
            print(f"Reading TSV file: {file_path}")
            df = pd.read_csv(file_path, sep="\t")
        else:
            print(f"Reading CSV file: {file_path}")
            df = pd.read_csv(file_path)

        print(f"Booking.com file loaded: {len(df)} rows")
        print(f"Columns: {list(df.columns)}")
        if len(df) > 0:
            print(f"First row sample: {dict(df.iloc[0])}")
        else:
            print("No data rows found in file")
            return []

        # Source file info for single-file import: "{date} {filename}"
        source_file = (
            f"{datetime.now().strftime('%Y-%m-%d')} {os.path.basename(file_path)}"
        )

        transactions = []

        for _, row in df.iterrows():
            booking = calculate_booking_row(
                row, df.columns, source_file, tax_rate_service, tenant
            )
            if booking is not None:
                transactions.append(booking)

        print(f"Booking.com processing completed: {len(transactions)} transactions")
        return transactions
    except Exception as e:
        print(f"Error processing booking.com file: {str(e)}")
        import traceback

        traceback.print_exc()
        return []


def process_booking_multi(
    file_paths: List[str], tax_rate_service=None, tenant: str = None
) -> List[Dict]:
    """
    Process multiple Booking.com files: read, concatenate, deduplicate, calculate.

    Args:
        file_paths: List of paths to Booking.com CSV/Excel files
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
            if fp.endswith((".xls", ".xlsx")):
                df = pd.read_excel(fp)
            elif fp.endswith(".tsv"):
                df = pd.read_csv(fp, sep="\t")
            else:
                df = pd.read_csv(fp)
            dfs.append(df)
            print(
                f"Booking multi-import: loaded {len(df)} rows from {os.path.basename(fp)}"
            )
        except Exception as e:
            failed_files.append(os.path.basename(fp))
            print(f"Booking multi-import: failed to parse {os.path.basename(fp)}: {e}")

    if not dfs:
        raise ValueError(f"All files failed to parse: {', '.join(failed_files)}")

    # Concatenate all DataFrames
    combined = pd.concat(dfs, ignore_index=True)
    print(f"Booking multi-import: {len(combined)} total rows from {len(dfs)} file(s)")

    # Deduplicate by Book number, keeping the last occurrence
    book_col = None
    for col_name in ["Book number", "Booking number", "Reservation"]:
        if col_name in combined.columns:
            book_col = col_name
            break

    if book_col:
        before_dedup = len(combined)
        combined = combined.drop_duplicates(subset=book_col, keep="last")
        print(
            f"Booking multi-import: deduplicated {before_dedup} -> {len(combined)} rows (by {book_col})"
        )

    # Determine sourceFile label
    today_str = datetime.now().strftime("%Y-%m-%d")
    if len(file_paths) > 1:
        source_file = f"{today_str} multi-import ({len(file_paths)} files)"
    else:
        source_file = f"{today_str} {os.path.basename(file_paths[0])}"

    # Process each row through the existing Booking.com algorithm
    transactions = []
    for _, row in combined.iterrows():
        booking = calculate_booking_row(
            row, combined.columns, source_file, tax_rate_service, tenant
        )
        if booking is not None:
            transactions.append(booking)

    if failed_files:
        print(
            f"Booking multi-import: WARNING - failed files: {', '.join(failed_files)}"
        )

    print(
        f"Booking multi-import: {len(transactions)} transactions from {len(file_paths)} file(s)"
    )
    return transactions


def calculate_booking_row(
    row, df_columns, source_file: str, tax_rate_service=None, tenant: str = None
) -> Optional[Dict]:
    """
    Process a single Booking.com row into a booking dict.

    Shared helper used by both process_booking and process_booking_multi
    to ensure algorithm equivalence.

    Args:
        row: A pandas Series representing one booking row
        df_columns: The columns of the source DataFrame (for addInfo)
        source_file: The sourceFile label to attach
        tax_rate_service: Optional TaxRateService for dynamic tax rates
        tenant: Optional tenant identifier

    Returns:
        Booking dict or None if the row should be skipped
    """
    # Map Booking.com columns with flexible matching
    checkin_date = row.get("Check-in", row.get("Checkin", row.get("Check in", "")))
    checkout_date = row.get("Check-out", row.get("Checkout", row.get("Check out", "")))
    guest_name = row.get("Guest name(s)", row.get("Guest name", row.get("Guest", "")))
    unit_type = row.get("Unit type", row.get("Property", row.get("Accommodation", "")))
    nights = row.get("Duration (nights)", row.get("Nights", row.get("Duration", 0)))
    price_str = row.get("Price", row.get("Total price", row.get("Amount", "0")))
    booking_id = row.get(
        "Book number", row.get("Booking number", row.get("Reservation", ""))
    )
    status = row.get("Status", "ok")
    commission_amount_str = row.get("Commission amount", row.get("Commission", ""))

    # Skip cancelled bookings with no commission (no revenue)
    if status == "cancelled_by_guest" and (
        pd.isna(commission_amount_str)
        or commission_amount_str == ""
        or commission_amount_str is None
    ):
        return None

    # Extract numeric base price from "126.6314 EUR" format
    try:
        if isinstance(price_str, str) and "EUR" in price_str:
            base_price = float(price_str.replace(" EUR", "").replace(",", "."))
        else:
            base_price = float(price_str) if price_str else 0
    except (ValueError, TypeError):
        base_price = 0

    # Skip records with zero or missing base price
    if base_price == 0:
        return None

    # Extract numeric commission amount from "15.195768 EUR" format
    try:
        if (
            pd.isna(commission_amount_str)
            or commission_amount_str == ""
            or commission_amount_str is None
        ):
            commission_amount = 0
        elif isinstance(commission_amount_str, str) and "EUR" in commission_amount_str:
            commission_amount = float(
                commission_amount_str.replace(" EUR", "").replace(",", ".")
            )
        else:
            commission_amount = (
                float(commission_amount_str) if commission_amount_str else 0
            )
    except (ValueError, TypeError):
        commission_amount = 0

    # Get tax rates based on check-in date
    _tax_rates = get_tax_rates(checkin_date, tax_rate_service, tenant)

    # Calculate gross amount using Booking.com algorithm
    uplift_factor = 1.047826
    amount_gross = round((base_price + commission_amount) * uplift_factor, 2)

    # Calculate channel fee
    amount_channel_fee = round(amount_gross - base_price, 2)

    price = amount_gross

    # Determine status based on check-in date and booking status
    today = date.today()
    try:
        checkin_dt = datetime.strptime(str(checkin_date), "%Y-%m-%d").date()
        if status == "cancelled_by_guest":
            booking_status = "cancelled"
        elif checkin_dt > today:
            booking_status = "planned"
        else:
            booking_status = "realised"
    except Exception:
        booking_status = "realised"

    # Use generic tax calculation function
    tax_calc = calculate_str_taxes(
        price, checkin_date, amount_channel_fee, tax_rate_service, tenant
    )
    amount_vat = tax_calc["amount_vat"]
    amount_tourist_tax = tax_calc["amount_tourist_tax"]
    amount_nett = tax_calc["amount_nett"]

    # Extract persons from data
    persons = row.get("Persons", 0) or 0
    adults = row.get("Adults", 0) or 0
    children = row.get("Children", 0) or 0
    guests = persons if persons > 0 else (adults + children)

    # Calculate dates and periods
    try:
        checkin_dt = datetime.strptime(str(checkin_date), "%Y-%m-%d")
        _checkout_dt = datetime.strptime(str(checkout_date), "%Y-%m-%d")
        reservation_dt = datetime.strptime(
            str(row.get("Booked on", "")).split(" ")[0], "%Y-%m-%d"
        )

        year = checkin_dt.year
        quarter = (checkin_dt.month - 1) // 3 + 1
        month = checkin_dt.month
        days_before_reservation = (checkin_dt - reservation_dt).days
    except Exception:
        year = datetime.now().year
        quarter = 1
        month = 1
        days_before_reservation = 0
        reservation_dt = datetime.now()

    # Price per night based on net amount
    price_per_night = amount_nett / nights if nights > 0 else 0

    # Additional info - concatenate all columns with |
    add_info = "|".join(str(row.get(col, "")) for col in df_columns)

    # Detect country from addInfo (Booking.com)
    country = detect_country("booking.com", phone="", addinfo=add_info)

    return {
        "sourceFile": source_file,
        "channel": "booking.com",
        "listing": normalize_listing_name(str(unit_type)),
        "checkinDate": str(checkin_date),
        "checkoutDate": str(checkout_date),
        "nights": int(nights) if nights else 0,
        "guests": int(guests),
        "amountGross": round(float(price), 2),
        "amountChannelFee": round(float(amount_channel_fee), 2),
        "guestName": str(guest_name),
        "phone": "",
        "reservationCode": str(booking_id),
        "reservationDate": reservation_dt.strftime("%Y-%m-%d"),
        "status": str(booking_status),
        "addInfo": add_info,
        "amountVat": amount_vat,
        "amountTouristTax": amount_tourist_tax,
        "amountNett": amount_nett,
        "pricePerNight": round(float(price_per_night), 2),
        "year": year,
        "q": quarter,
        "m": month,
        "daysBeforeReservation": days_before_reservation,
        "country": country,
    }


def process_booking_payout(
    file_path: str, tax_rate_service=None, tenant: str = None
) -> Dict:
    """
    Process Booking.com Payout CSV file to update financial figures.

    This file is available monthly after month closure and contains the final,
    accurate financial figures from Booking.com's settlement.

    Args:
        file_path: Path to the Payout CSV file (format: Payout_from_*.csv)
        tax_rate_service: Optional TaxRateService for dynamic tax rates
        tenant: Optional tenant identifier

    Returns:
        dict with update results: {
            'updated': List of updated reservation codes,
            'not_found': List of reservation codes not found in database,
            'errors': List of error messages,
            'summary': Summary statistics
        }
    """
    print(f"Processing Booking.com Payout CSV: {file_path}")

    results = {
        "updated": [],
        "not_found": [],
        "errors": [],
        "summary": {
            "total_rows": 0,
            "reservation_rows": 0,
            "updated_count": 0,
            "not_found_count": 0,
            "error_count": 0,
        },
    }

    try:
        # Read CSV file and strip whitespace from column names
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()

        results["summary"]["total_rows"] = len(df)

        print(f"Payout CSV loaded: {len(df)} rows")
        print(f"Columns: {list(df.columns)}")

        # Filter only Reservation rows (not Payout summary rows)
        reservation_rows = df[df["Type/Transaction type"].str.strip() == "Reservation"]
        results["summary"]["reservation_rows"] = len(reservation_rows)

        print(f"Found {len(reservation_rows)} reservation rows to process")

        updates = []

        for _, row in reservation_rows.iterrows():
            try:
                # Extract reservation code (Reference number)
                reservation_code_raw = row.get("Reference number", "")
                if pd.isna(reservation_code_raw) or reservation_code_raw == "-":
                    continue

                # Convert to string and remove decimal point if it's a float
                reservation_code = str(reservation_code_raw).strip()
                if (
                    "." in reservation_code
                    and reservation_code.replace(".", "").replace("0", "", 1).isdigit()
                ):
                    reservation_code = reservation_code.split(".")[0]

                if not reservation_code or reservation_code == "-":
                    continue

                # Extract financial data from CSV
                checkin_date = str(row.get("Check-in date", "")).strip()
                checkout_date = str(row.get("Check-out date", "")).strip()
                nights = (
                    int(row.get("Room nights", 0))
                    if pd.notna(row.get("Room nights"))
                    else 0
                )

                # Gross amount (actual from BDC)
                gross_amount_str = str(row.get("Gross amount", "0")).strip()
                gross_amount = (
                    float(gross_amount_str)
                    if gross_amount_str and gross_amount_str != "-"
                    else 0.0
                )

                # Commission (negative value in CSV)
                commission_str = str(row.get("Commission", "0")).strip()
                commission = (
                    float(commission_str)
                    if commission_str and commission_str != "-"
                    else 0.0
                )

                # Payments Service Fee (negative value in CSV)
                service_fee_str = str(row.get("Payments Service Fee", "0")).strip()
                service_fee = (
                    float(service_fee_str)
                    if service_fee_str and service_fee_str != "-"
                    else 0.0
                )

                # Skip if no gross amount
                if gross_amount == 0:
                    continue

                # Calculate channel fee: abs(Commission) + abs(Payments Service Fee)
                amount_channel_fee = abs(commission) + abs(service_fee)

                # Get tax rates based on check-in date
                tax_rates = get_tax_rates(checkin_date, tax_rate_service, tenant)

                # Calculate VAT on gross amount
                vat_base = tax_rates["vat_base"]
                vat_rate = tax_rates["vat_rate"]
                amount_vat = round((gross_amount / vat_base) * vat_rate, 2)

                # Calculate tourist tax
                vat_exclusive_amount = gross_amount - amount_vat
                tourist_base = tax_rates["tourist_tax_base"]
                tourist_rate = tax_rates["tourist_tax_rate"]
                amount_tourist_tax = round(
                    (vat_exclusive_amount / tourist_base) * tourist_rate, 2
                )

                # Calculate net amount
                amount_nett = (
                    gross_amount - amount_vat - amount_tourist_tax - amount_channel_fee
                )

                # Calculate price per night
                price_per_night = round(amount_nett / nights, 2) if nights > 0 else 0.0

                # Create update record
                update_record = {
                    "reservationCode": reservation_code,
                    "amountGross": round(gross_amount, 2),
                    "amountChannelFee": round(amount_channel_fee, 2),
                    "amountVat": round(amount_vat, 2),
                    "amountTouristTax": round(amount_tourist_tax, 2),
                    "amountNett": round(amount_nett, 2),
                    "pricePerNight": round(price_per_night, 2),
                    "checkinDate": checkin_date,
                    "checkoutDate": checkout_date,
                    "nights": nights,
                    "sourceFile": f"PAYOUT_{datetime.now().strftime('%Y-%m-%d')}_{os.path.basename(file_path)}",
                }

                updates.append(update_record)
                results["updated"].append(reservation_code)

                print(
                    f"Prepared update for reservation {reservation_code}: "
                    f"Gross={gross_amount}, ChannelFee={amount_channel_fee}, "
                    f"VAT={amount_vat}, TouristTax={amount_tourist_tax}, Net={amount_nett}"
                )

            except Exception as e:
                error_msg = (
                    f"Error processing row for reservation {reservation_code}: {str(e)}"
                )
                print(error_msg)
                results["errors"].append(error_msg)
                results["summary"]["error_count"] += 1

        # Update summary
        results["summary"]["updated_count"] = len(updates)
        results["updates"] = updates

        print("\nPayout processing completed:")
        print(f"  Total rows: {results['summary']['total_rows']}")
        print(f"  Reservation rows: {results['summary']['reservation_rows']}")
        print(f"  Updates prepared: {results['summary']['updated_count']}")
        print(f"  Errors: {results['summary']['error_count']}")

        return results

    except Exception as e:
        error_msg = f"Error processing Payout CSV file: {str(e)}"
        print(error_msg)
        import traceback

        traceback.print_exc()
        results["errors"].append(error_msg)
        results["summary"]["error_count"] += 1
        return results
