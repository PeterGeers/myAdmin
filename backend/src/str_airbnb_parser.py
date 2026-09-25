"""
Airbnb-specific STR file parsing.

Handles processing of Airbnb CSV reservation exports including:
- Multi-file import with deduplication by Bevestigingscode
- Dutch column name mapping
- European currency format parsing (€ 1.234,56)
- Financial calculations (gross, channel fee, VAT, tourist tax, net)
"""

import os
from datetime import datetime

import pandas as pd

from country_detector import detect_country
from str_utils import calculate_str_taxes, normalize_listing_name


def parse_airbnb_amount(value) -> float:
    """
    Parse an Airbnb amount cell into a float, accepting both US and European notation.

    Airbnb exports mix notations within one file: ``Bruto-inkomsten`` uses US notation
    (``274.80``) while ``Servicekosten`` uses quoted European notation (``"42,59"``,
    ``"1.234,56"``) or ``0.00``. Cells are also quoted and space-padded.

    Decision rule (see design "The amount-parsing algorithm"):
      - NaN or blank-after-strip -> 0.0
      - strip quotes, spaces, and the euro symbol
      - if a comma is present (European):
          - two comma-parts: drop "." thousands separators from the integer part,
            join integer + "." + decimal
          - otherwise: replace "," with "."
      - no comma: parse as US-style period-decimal
      - any float() failure -> 0.0

    Args:
        value: The raw cell value (str, number, or NaN).

    Returns:
        The parsed numeric value, or 0.0 for blank/NaN/non-numeric input.
    """
    # NaN check (pandas NaN, numpy nan, etc.)
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass

    # Strip quotes, spaces, and the euro symbol
    s = str(value).replace('"', "").replace("'", "").replace("€", "").replace(" ", "")

    if s == "":
        return 0.0

    if "," in s:
        # European notation
        parts = s.split(",")
        if len(parts) == 2:
            integer_part = parts[0].replace(".", "")  # drop thousands separator
            s = f"{integer_part}.{parts[1]}"
        else:
            s = s.replace(",", ".")
    # else: already US-style period-decimal

    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def parse_airbnb_date(value) -> datetime | None:
    """
    Parse an Airbnb export date in ``MM/DD/YYYY`` form.

    Airbnb's new export format writes dates as ``MM/DD/YYYY`` (for example
    ``09/23/2026``) and cell values may be space-padded. This strips surrounding
    whitespace before parsing and returns ``None`` on any failure so the caller
    can apply its today/current-year fallback.

    Args:
        value: The raw cell value (string, or NaN/None for blanks).

    Returns:
        A ``datetime`` for a valid ``MM/DD/YYYY`` date, otherwise ``None``.
    """
    if value is None:
        return None
    # pandas NaN and other non-string blanks
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%m/%d/%Y")
    except (ValueError, TypeError):
        return None


def build_booking_from_group(
    code: str,
    rows,
    source_file: str,
    status: str,
    tax_rate_service=None,
    tenant: str | None = None,
) -> dict:
    """
    Assemble one Booking_Dict from a group of rows sharing one ``Bevestigingscode``.

    A booking appears in the export as two rows (a ``Boeking`` row and a
    ``Doorloop totaal`` row) that repeat the same dates, guest, and listing but each
    carry a portion of the gross income. Amounts are therefore summed across the whole
    group while shared attributes (dates, guest, listing, nights) are read from the
    first row (see design "The group-by algorithm").

    Args:
        code: The group's ``Bevestigingscode`` value (becomes ``reservationCode``).
        rows: A pandas DataFrame of the group's rows (column names already stripped).
        source_file: The ``sourceFile`` label to attach.
        status: The booking status ("planned" or "realised") from the file class.
        tax_rate_service: Optional TaxRateService for dynamic tax rates.
        tenant: Optional tenant identifier.

    Returns:
        A Booking_Dict with exactly the 24 contract fields (Requirement 8).
    """
    first = rows.iloc[0]

    # --- Amounts: summed across all rows in the group (Req 3.1, 3.2; no 15% factor) ---
    gross_amount = sum(parse_airbnb_amount(v) for v in rows.get("Bruto-inkomsten", []))
    amount_channel_fee = sum(
        parse_airbnb_amount(v) for v in rows.get("Servicekosten", [])
    )

    # --- Dates from the first row, with today / current-year fallback (Req 5.1, 5.2) ---
    checkin_dt = parse_airbnb_date(first.get("Begindatum", ""))
    checkout_dt = parse_airbnb_date(first.get("Einddatum", ""))
    reservation_dt = parse_airbnb_date(first.get("Boekingsdatum", ""))

    now = datetime.now()
    checkin_dt = checkin_dt or now
    checkout_dt = checkout_dt or now
    reservation_dt = reservation_dt or now

    # Derived periods from the check-in date (Req 5.3, 5.4, 9.3)
    year = checkin_dt.year
    quarter = (checkin_dt.month - 1) // 3 + 1
    month = checkin_dt.month
    days_before_reservation = (checkin_dt - reservation_dt).days

    checkin_str = checkin_dt.strftime("%Y-%m-%d")

    # --- Taxes / net via the shared calculator (Req 3.3) ---
    tax_calc = calculate_str_taxes(
        gross_amount, checkin_str, amount_channel_fee, tax_rate_service, tenant
    )
    amount_vat = tax_calc["amount_vat"]
    amount_tourist_tax = tax_calc["amount_tourist_tax"]
    amount_nett = tax_calc["amount_nett"]

    # --- Nights and price per night ---
    try:
        nights = int(float(first.get("Nachten", 0) or 0))
    except (ValueError, TypeError):
        nights = 0
    price_per_night = amount_nett / nights if nights > 0 else 0

    guest_name = str(first.get("Gast", "") or "")
    listing = normalize_listing_name(str(first.get("Advertentie", "") or ""))

    # Additional info from the informational column; feeds country detection (Req 7.3)
    add_info = str(first.get("Informatie", "") or "")
    country = detect_country("airbnb", addinfo=add_info)

    return {
        "sourceFile": source_file,
        "channel": "airbnb",  # Req 8.2
        "listing": listing,  # Req 8.3
        "checkinDate": checkin_str,
        "checkoutDate": checkout_dt.strftime("%Y-%m-%d"),
        "nights": nights,
        "guests": 2,  # Req 7.1 (no guest-count column)
        "amountGross": round(float(gross_amount), 2),
        "amountChannelFee": round(float(amount_channel_fee), 2),
        "guestName": guest_name,
        "phone": "",  # Req 7.2 (no contact column)
        "reservationCode": str(code),  # Req 8.4
        "reservationDate": reservation_dt.strftime("%Y-%m-%d"),
        "status": status,  # Req 6.1 / 6.3 (from file class, passed by caller)
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


def process_airbnb_multi(
    file_paths: list[str],
    tax_rate_service=None,
    tenant: str | None = None,
    status: str = "realised",
) -> list[dict]:
    """
    Process Airbnb CSV file(s) of a single classification into Booking_Dicts.

    Each file is read with pandas (quoted, space-padded amounts like ``"42,59"`` are
    handled via ``skipinitialspace``), its column names are stripped of the UTF-8 BOM and
    surrounding whitespace, ``Payout`` rows and blank-``Bevestigingscode`` rows are dropped,
    and the remaining rows are grouped by their stripped ``Bevestigingscode``. Exactly one
    ``build_booking_from_group`` call is made per group (see design "The group-by
    algorithm"). Every returned dict is tagged with the passed ``status``.

    Unreadable files are skipped (their basename recorded); a ``ValueError`` is raised only
    when every file fails, preserving the previous contract (design "Error handling").

    Args:
        file_paths: Paths to Airbnb CSV files of one classification.
        tax_rate_service: Optional TaxRateService for dynamic tax rates.
        tenant: Optional tenant identifier.
        status: Booking status for this batch ("planned" for a Pending_File batch,
            "realised" for a Realised_File batch). Req 6.1 / 6.3 / 6.5.

    Returns:
        A list of Booking_Dicts, one per confirmation code, all tagged with ``status``.

    Raises:
        ValueError: If all files fail to parse.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    if len(file_paths) > 1:
        source_file = f"{today_str} multi-import ({len(file_paths)} files)"
    else:
        base = os.path.basename(file_paths[0]) if file_paths else "unknown"
        source_file = f"{today_str} {base}"

    bookings: list[dict] = []
    failed_files: list[str] = []
    parsed_any = False

    for fp in file_paths:
        try:
            # skipinitialspace lets pandas honour the quotes around space-padded
            # European amounts (e.g. ` "42,59"`) so the C parser doesn't choke on the
            # embedded comma; on_bad_lines is a belt-and-suspenders fallback.
            df = pd.read_csv(fp, skipinitialspace=True, on_bad_lines="skip")
        except Exception as e:
            failed_files.append(os.path.basename(fp))
            print(f"Airbnb multi-import: failed to parse {os.path.basename(fp)}: {e}")
            continue

        parsed_any = True

        # Strip BOM + surrounding whitespace from every column name.
        df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

        # Req 2.3: drop Payout rows and blank-confirmation-code rows before grouping.
        if "Type" in df.columns:
            df = df[df["Type"].map(lambda v: str(v).strip()) != "Payout"]
        if "Bevestigingscode" not in df.columns:
            print(
                f"Airbnb multi-import: {os.path.basename(fp)} has no Bevestigingscode column; skipping"
            )
            continue
        code_series = df["Bevestigingscode"].map(lambda v: str(v).strip())
        df = df[code_series != ""]
        df = df[code_series.map(lambda v: v.lower()) != "nan"]

        print(
            f"Airbnb multi-import: {len(df)} booking rows from {os.path.basename(fp)}"
        )

        # Req 2.1 / 2.2: one Booking_Dict per non-blank confirmation code.
        grouping_key = df["Bevestigingscode"].map(lambda v: str(v).strip())
        for code, group in df.groupby(grouping_key):
            bookings.append(
                build_booking_from_group(
                    code, group, source_file, status, tax_rate_service, tenant
                )
            )

    if not parsed_any:
        raise ValueError(f"All files failed to parse: {', '.join(failed_files)}")

    if failed_files:
        print(f"Airbnb multi-import: WARNING - failed files: {', '.join(failed_files)}")

    print(
        f"Airbnb multi-import: {len(bookings)} bookings ({status}) from {len(file_paths)} file(s)"
    )
    return bookings
