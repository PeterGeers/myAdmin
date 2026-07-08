"""
STR (Short-Term Rental) Processor - Dispatcher Module

Orchestrates STR file processing across platforms by delegating to:
- str_airbnb_parser (Airbnb), str_booking_parser (Booking.com), str_utils (shared)
- Direct/VRBO: handled inline (smaller codepaths)
"""

import os
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional

from country_detector import detect_country
from str_utils import (
    get_tax_rates,
    calculate_str_taxes,
    normalize_listing_name,
    parse_amount,
    parse_multilang_date,
    parse_date,
)
from str_airbnb_parser import process_airbnb_multi, calculate_airbnb_row
from str_booking_parser import (
    process_booking,
    process_booking_multi,
    calculate_booking_row,
    process_booking_payout,
)


class STRProcessor:
    """Dispatcher that delegates platform-specific parsing to dedicated modules."""

    def __init__(
        self, test_mode: bool = False, tax_rate_service=None, tenant: str = None
    ):
        self.test_mode = test_mode
        self.platforms = ["airbnb", "booking", "direct"]
        self.tax_rate_service = tax_rate_service
        self.tenant = tenant
        # Download folder from environment or working directory
        if os.getenv("DOCKER_ENV") or os.path.exists("/.dockerenv"):
            self.download_folder = "/app/downloads"
        else:
            self.download_folder = os.path.join(os.getcwd(), "downloads")

        # Property mappings from config
        self.property_mappings = {
            "green": "Green Apartment",
            "child": "Garden House",
            "red": "Red Apartment",
        }

    # Tax / utility delegations (preserve existing interface)

    def get_tax_rates(self, checkin_date: str) -> dict:
        """Get VAT and tourist tax rates based on check-in date."""
        return get_tax_rates(checkin_date, self.tax_rate_service, self.tenant)

    def calculate_str_taxes(
        self, gross_amount: float, checkin_date: str, channel_fee: float = 0.0
    ) -> dict:
        """Generic tax calculation for all STR channels."""
        return calculate_str_taxes(
            gross_amount, checkin_date, channel_fee, self.tax_rate_service, self.tenant
        )

    def _normalize_listing_name(self, listing: str) -> str:
        return normalize_listing_name(listing)

    def _parse_amount(self, amount_str: str) -> float:
        return parse_amount(amount_str)

    def _parse_multilang_date(self, date_str: str) -> str:
        return parse_multilang_date(date_str)

    def _parse_date(self, date_str: str) -> str:
        return parse_date(date_str)

    # File scanning

    def scan_str_files(self, folder_path: str = None) -> Dict[str, List[str]]:
        """Scan folder for STR files by platform."""
        if not folder_path:
            folder_path = self.download_folder

        files = {"airbnb": [], "booking": [], "booking_payout": [], "direct": []}

        try:
            for file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path):
                    if "payout_from" in file.lower() and file.endswith(".csv"):
                        files["booking_payout"].append(file_path)
                    elif "reservation" in file.lower() and file.endswith(".csv"):
                        files["airbnb"].append(file_path)
                    elif (
                        "check-in" in file.lower() or "booking" in file.lower()
                    ) and file.endswith((".xls", ".xlsx")):
                        files["booking"].append(file_path)
                    elif "jabakirechtstreeks" in file.lower() and file.endswith(
                        (".xlsx")
                    ):
                        files["direct"].append(file_path)
        except Exception as e:
            print(f"Error scanning folder: {e}")

        return files

    # Multi-file dispatching

    def process_str_files(self, file_paths: List[str], platform: str) -> List[Dict]:
        """Process multiple STR files for a platform."""
        if platform.lower() == "vrbo":
            return self._process_vrbo(file_paths)

        if platform.lower() in ["booking", "booking.com"]:
            return self._process_booking_multi(file_paths)

        if platform.lower() == "airbnb":
            return self._process_airbnb_multi(file_paths)

        all_bookings = []
        for file_path in file_paths:
            try:
                bookings = self._process_single_file(file_path, platform)
                all_bookings.extend(bookings)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

        return all_bookings

    def _process_single_file(self, file_path: str, platform: str) -> List[Dict]:
        """Process single STR file based on platform."""
        platform = platform.lower()
        print(f"Processing file: {file_path} as platform: {platform}")

        if platform in ["booking", "booking.com"]:
            return self._process_booking(file_path)
        elif platform in ["booking_payout", "payout"]:
            return []
        elif platform == "direct":
            return self._process_direct(file_path)
        elif platform == "vrbo":
            return self._process_vrbo_single(file_path)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    # Airbnb delegation

    def _process_airbnb_multi(self, file_paths: List[str]) -> List[Dict]:
        """Process multiple Airbnb CSV files (delegated)."""
        return process_airbnb_multi(file_paths, self.tax_rate_service, self.tenant)

    def _calculate_airbnb_row(
        self, row, df_columns, source_file: str
    ) -> Optional[Dict]:
        """Process a single Airbnb row (delegated)."""
        return calculate_airbnb_row(
            row, df_columns, source_file, self.tax_rate_service, self.tenant
        )

    # Booking.com delegation

    def _process_booking(self, file_path: str) -> List[Dict]:
        """Process Booking.com export (delegated)."""
        return process_booking(file_path, self.tax_rate_service, self.tenant)

    def _process_booking_multi(self, file_paths: List[str]) -> List[Dict]:
        """Process multiple Booking.com files (delegated)."""
        return process_booking_multi(file_paths, self.tax_rate_service, self.tenant)

    def _calculate_booking_row(
        self, row, df_columns, source_file: str
    ) -> Optional[Dict]:
        """Process a single Booking.com row (delegated)."""
        return calculate_booking_row(
            row, df_columns, source_file, self.tax_rate_service, self.tenant
        )

    def _process_booking_payout(self, file_path: str) -> Dict:
        """Process Booking.com Payout CSV (delegated)."""
        return process_booking_payout(file_path, self.tax_rate_service, self.tenant)

    # Direct bookings (inline — small codepath)

    def _process_direct(self, file_path: str) -> List[Dict]:
        """Process direct bookings Excel/CSV."""
        try:
            df = (
                pd.read_excel(file_path)
                if file_path.endswith((".xls", ".xlsx"))
                else pd.read_csv(file_path)
            )
            transactions = []
            source_file = (
                f"{datetime.now().strftime('%Y-%m-%d')} {os.path.basename(file_path)}"
            )

            for _, row in df.iterrows():
                if str(row.get("type", "")).strip().lower() != "reservation":
                    continue
                booking = self._calculate_direct_row(row, file_path, source_file)
                if booking:
                    transactions.append(booking)

            return transactions
        except Exception as e:
            print(f"ERROR in _process_direct: {e}", flush=True)
            return []

    def _calculate_direct_row(
        self, row, file_path: str, source_file: str
    ) -> Optional[Dict]:
        """Process a single direct booking row."""
        checkin_date = row.get("startDate", "")
        guest_name = row.get("guestName", "")
        listing = row.get("listing", "")
        nights = row.get("nights", 0)
        guests = row.get("guests", 0)
        gross_amount = row.get("amountGross", 0)
        paid_out = row.get("paidOut", 0)
        channel_fee = float(gross_amount) - float(paid_out)
        booking_id = row.get("reservationCode", "")
        trade_type = row.get("typeTrade", "")
        details = row.get("details", "")
        currency = row.get("currency", "")
        cleaning_fee = row.get("cleaningFee", 0)

        # Determine channel
        trade_lower = str(trade_type).lower()
        channel = (
            "dfDirect"
            if "goodwin" in trade_lower
            else ("VRBO" if "vrbo" in trade_lower else "dfZwart")
        )

        # Booking status
        today = date.today()
        try:
            checkin_str = str(checkin_date).strip()
            checkin_dt = None
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"]:
                try:
                    checkin_dt = datetime.strptime(checkin_str.split()[0], fmt).date()
                    break
                except ValueError:
                    continue
            if checkin_dt is None:
                checkin_dt = pd.to_datetime(checkin_str).date()
            booking_status = "planned" if checkin_dt > today else "realised"
        except Exception:
            booking_status = "realised"

        # Checkout date
        try:
            checkin_dt = datetime.strptime(str(checkin_date), "%Y-%m-%d")
            checkout_date = (checkin_dt + pd.Timedelta(days=int(nights))).strftime(
                "%Y-%m-%d"
            )
        except Exception:
            try:
                from datetime import timedelta

                checkout_date = (
                    pd.to_datetime(checkin_date) + timedelta(days=int(nights))
                ).strftime("%Y-%m-%d")
            except Exception:
                checkout_date = str(checkin_date)

        tax_calc = self.calculate_str_taxes(gross_amount, checkin_date, channel_fee)

        # Dates and periods
        try:
            checkin_dt = datetime.strptime(str(checkin_date), "%Y-%m-%d")
            reservation_dt = checkin_dt
            year, quarter, month = (
                checkin_dt.year,
                (checkin_dt.month - 1) // 3 + 1,
                checkin_dt.month,
            )
        except Exception:
            reservation_dt = datetime.now()
            year, quarter, month = (
                reservation_dt.year,
                (reservation_dt.month - 1) // 3 + 1,
                reservation_dt.month,
            )

        price_per_night = (
            tax_calc["amount_nett"] / int(nights) if int(nights) > 0 else 0
        )
        add_info = (
            f"{os.path.basename(file_path)} | {guest_name} | reservation | {trade_type} "
            f"| {details} | {booking_id} | {currency} | {gross_amount} "
            f"| {channel_fee} | {cleaning_fee}"
        )
        country = detect_country(channel, phone="", addinfo=add_info)

        try:
            checkin_date_clean = pd.to_datetime(checkin_date).strftime("%Y-%m-%d")
        except Exception:
            checkin_date_clean = (
                str(checkin_date).split()[0]
                if " " in str(checkin_date)
                else str(checkin_date)
            )

        return {
            "sourceFile": source_file,
            "channel": channel,
            "listing": normalize_listing_name(str(listing)),
            "checkinDate": checkin_date_clean,
            "checkoutDate": checkout_date,
            "nights": int(nights) if nights else 0,
            "guests": int(guests) if guests else 0,
            "amountGross": round(float(gross_amount), 2),
            "amountChannelFee": round(float(channel_fee), 2),
            "guestName": str(guest_name).replace("'", " "),
            "phone": "",
            "reservationCode": str(booking_id),
            "reservationDate": reservation_dt.strftime("%Y-%m-%d"),
            "status": str(booking_status),
            "addInfo": add_info,
            "amountVat": tax_calc["amount_vat"],
            "amountTouristTax": tax_calc["amount_tourist_tax"],
            "amountNett": tax_calc["amount_nett"],
            "pricePerNight": round(float(price_per_night), 2),
            "year": year,
            "q": quarter,
            "m": month,
            "daysBeforeReservation": 0,
            "country": country,
        }

    # VRBO Processing

    def _process_vrbo(self, file_paths: List[str]) -> List[Dict]:
        """Process VRBO CSV exports — merges Reservations + Payouts files."""
        reservation_files, payout_files = [], []

        for fp in file_paths:
            try:
                header = pd.read_csv(fp, nrows=0).columns.tolist()
                first_col = header[0].strip() if header else ""
                if first_col == "Reservation ID":
                    reservation_files.append(fp)
                elif first_col in (
                    "Naam gast",
                    "Guest name",
                    "Name des Gastes",
                    "Nom du client",
                ):
                    payout_files.append(fp)
                else:
                    print(
                        f"VRBO: Unknown file type (first column: '{first_col}'): {fp}"
                    )
            except Exception as e:
                print(f"VRBO: Error reading header of {fp}: {e}")

        reservations = {}
        for fp in reservation_files:
            for res in self._parse_vrbo_reservations(fp):
                reservations[res["reservationCode"]] = res

        payouts = {}
        for fp in payout_files:
            for code, amount in self._parse_vrbo_payouts(fp):
                payouts[code] = amount

        bookings = [
            self._build_vrbo_booking(res, payouts.get(code))
            for code, res in reservations.items()
        ]

        orphans = sum(1 for c in payouts if c not in reservations)
        print(
            f"VRBO: {len(bookings)} bookings from {len(reservation_files)} reservation file(s) "
            f"and {len(payout_files)} payout file(s). {orphans} orphan payouts."
        )
        return bookings

    def _process_vrbo_single(self, file_path: str) -> List[Dict]:
        """Process a single VRBO file."""
        return self._process_vrbo([file_path])

    def _parse_vrbo_reservations(self, file_path: str) -> List[Dict]:
        """Parse a VRBO Reservations CSV."""
        try:
            df = pd.read_csv(file_path)
            src = f"{datetime.now().strftime('%Y-%m-%d')} {os.path.basename(file_path)}"
            col_map = {
                "reservationCode": "Reservation ID",
                "listingNumber": "Listing Number",
                "propertyName": "Property Name",
                "reservationDate": "Created On",
                "email": "Email",
                "guestName": "Inquirer",
                "phone": "Phone",
                "checkinDate": "Check-in",
                "checkoutDate": "Check-out",
            }
            results = []
            for _, row in df.iterrows():
                rec = {k: str(row.get(v, "")).strip() for k, v in col_map.items()}
                rec.update(
                    {
                        "nights": int(row.get("Nights Stay", 0) or 0),
                        "adults": int(row.get("Adults", 0) or 0),
                        "children": int(row.get("Children", 0) or 0),
                        "csvStatus": str(row.get("Status", "")).strip(),
                        "source": str(row.get("Source", "VRBO")).strip(),
                        "sourceFile": src,
                    }
                )
                results.append(rec)
            return results
        except Exception as e:
            print(f"VRBO: Error parsing reservations {file_path}: {e}")
            return []

    def _parse_vrbo_payouts(self, file_path: str) -> List[tuple]:
        """Parse a VRBO Payouts CSV (multi-language headers)."""
        try:
            df = pd.read_csv(file_path)
            code_col, amount_col = None, None
            for col in df.columns:
                cl = col.strip().lower()
                if cl in (
                    "boekingsnummer",
                    "booking number",
                    "buchungsnummer",
                    "numéro de réservation",
                ):
                    code_col = col
                elif cl in ("bedrag", "amount", "betrag", "montant"):
                    amount_col = col

            if not code_col or not amount_col:
                print(f"VRBO: Could not identify columns. Headers: {list(df.columns)}")
                return []

            results = []
            for _, row in df.iterrows():
                code = str(row.get(code_col, "")).strip()
                if not code or code == "nan":
                    continue
                results.append((code, parse_amount(str(row.get(amount_col, "0")))))
            return results
        except Exception as e:
            print(f"VRBO: Error parsing payouts {file_path}: {e}")
            return []

    def _build_vrbo_booking(self, res: Dict, payout_amount: Optional[float]) -> Dict:
        """Build a standard booking dict from VRBO reservation + payout data."""
        today = date.today()
        checkin_date = parse_date(res["checkinDate"])
        checkout_date = parse_date(res["checkoutDate"])
        reservation_date = parse_date(res["reservationDate"])

        try:
            checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d").date()
            if "cancel" in res["csvStatus"].lower():
                booking_status = "cancelled"
            elif checkin_dt > today:
                booking_status = "planned"
            else:
                booking_status = "realised"
        except Exception:
            booking_status = "realised"

        if payout_amount and payout_amount > 0:
            amount_gross = payout_amount / (1 - 0.25)
            amount_channel_fee = amount_gross - payout_amount
        else:
            amount_gross, amount_channel_fee = 0, 0

        tax_calc = self.calculate_str_taxes(
            amount_gross, checkin_date, amount_channel_fee
        )

        try:
            checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
            reservation_dt = datetime.strptime(reservation_date, "%Y-%m-%d")
            year, quarter, month = (
                checkin_dt.year,
                (checkin_dt.month - 1) // 3 + 1,
                checkin_dt.month,
            )
            days_before = (checkin_dt - reservation_dt).days
        except Exception:
            year, quarter, month, days_before = datetime.now().year, 1, 1, 0

        nights = res["nights"] or 0
        guests = res["adults"] + res["children"]
        price_per_night = tax_calc["amount_nett"] / nights if nights > 0 else 0
        country = detect_country(
            "vrbo", phone=res["phone"], addinfo=res.get("email", "")
        )

        return {
            "sourceFile": res["sourceFile"],
            "channel": "vrbo",
            "listing": normalize_listing_name(res["propertyName"]),
            "checkinDate": checkin_date,
            "checkoutDate": checkout_date,
            "nights": nights,
            "guests": guests,
            "amountGross": round(amount_gross, 2),
            "amountChannelFee": round(amount_channel_fee, 2),
            "amountNett": tax_calc["amount_nett"],
            "amountVat": tax_calc["amount_vat"],
            "amountTouristTax": tax_calc["amount_tourist_tax"],
            "guestName": res["guestName"],
            "phone": res["phone"],
            "reservationCode": res["reservationCode"],
            "reservationDate": reservation_date,
            "status": booking_status,
            "pricePerNight": round(price_per_night, 2),
            "daysBeforeReservation": days_before,
            "addInfo": "|".join(str(v) for v in res.values()),
            "year": year,
            "q": quarter,
            "m": month,
            "country": country,
        }

    # Summary / status helpers

    def generate_summary(self, bookings: List[Dict]) -> Dict:
        """Generate STR performance summary."""
        if not bookings:
            return {}
        df = pd.DataFrame(bookings)
        return {
            "total_bookings": len(bookings),
            "total_nights": df["nights"].sum() if "nights" in df.columns else 0,
            "total_gross": df["amountGross"].sum()
            if "amountGross" in df.columns
            else 0,
            "total_net": df["amountNett"].sum() if "amountNett" in df.columns else 0,
            "avg_nightly_rate": df["pricePerNight"].mean()
            if "pricePerNight" in df.columns
            else 0,
            "channels": df["channel"].value_counts().to_dict()
            if "channel" in df.columns
            else {},
            "listings": df["listing"].value_counts().to_dict()
            if "listing" in df.columns
            else {},
            "date_range": {
                "start": df["checkinDate"].min() if "checkinDate" in df.columns else "",
                "end": df["checkinDate"].max() if "checkinDate" in df.columns else "",
            },
        }

    def separate_by_status(self, bookings: List[Dict]) -> Dict[str, List[Dict]]:
        """Separate bookings by status and check for duplicates."""
        try:
            from str_database import STRDatabase

            str_db = STRDatabase(test_mode=self.test_mode)
            channels = set(b.get("channel", "") for b in bookings)
            existing_codes_by_channel = {
                ch: str_db.get_existing_reservation_codes_for_channel(ch)
                for ch in channels
                if ch
            }
            realised, planned, already_loaded = [], [], []
            for booking in bookings:
                channel = booking.get("channel", "")
                code = str(booking.get("reservationCode", ""))
                status = booking.get("status", "")
                if (
                    channel in existing_codes_by_channel
                    and code in existing_codes_by_channel[channel]
                ):
                    already_loaded.append(booking)
                elif status == "planned":
                    planned.append(booking)
                else:
                    realised.append(booking)
            return {
                "realised": realised,
                "planned": planned,
                "already_loaded": already_loaded,
            }
        except Exception:
            return {
                "realised": [
                    b for b in bookings if b.get("status") in ["realised", "cancelled"]
                ],
                "planned": [b for b in bookings if b.get("status") == "planned"],
                "already_loaded": [],
            }

    def generate_future_summary(self, planned_bookings: List[Dict]) -> List[Dict]:
        """Generate future bookings summary by channel and listing."""
        if not planned_bookings:
            return []
        df = pd.DataFrame(planned_bookings)
        summary = (
            df.groupby(["channel", "listing"])
            .agg({"amountGross": "sum", "reservationCode": "count"})
            .reset_index()
        )
        summary.columns = ["channel", "listing", "amount", "items"]
        summary["date"] = date.today().strftime("%Y-%m-%d")
        return summary.to_dict("records")
