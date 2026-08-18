from database import DatabaseManager
from db_exceptions import DatabaseError
from dialect_helpers import dialect


class STRDatabase(DatabaseManager):
    def __init__(self, test_mode: bool = False):
        super().__init__(test_mode)
        self.connection = self.get_connection()
        # Uses existing tables: bnb, bnbplanned, bnbfuture

    def insert_realised_bookings(self, bookings: list[dict]) -> int:
        """Insert realised bookings into bnb table"""
        if not bookings:
            return 0

        # Get existing reservation codes by channel to avoid duplicates
        new_bookings = []

        for booking in bookings:
            channel = booking.get("channel", "")
            code = booking.get("reservationCode", "")
            admin = booking.get("administration", "")
            existing_codes = self.get_existing_reservation_codes_for_channel(
                channel, admin if admin else None
            )
            if code not in existing_codes:
                new_bookings.append(booking)

        if not new_bookings:
            return 0

        insert_query = """
        INSERT INTO bnb 
        (sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
         amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat,
         guestName, phone, reservationCode, reservationDate, status, pricePerNight,
         daysBeforeReservation, addInfo, year, q, m, country, administration)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            cursor = self.connection.cursor()
            inserted = 0

            # Check table structure first
            _available_columns = self.check_bnb_table_structure()

            for booking in new_bookings:
                values = (
                    booking.get("sourceFile", ""),
                    booking.get("channel", ""),
                    booking.get("listing", ""),
                    booking.get("checkinDate", ""),
                    booking.get("checkoutDate", ""),
                    booking.get("nights", 0),
                    booking.get("guests", 0),
                    booking.get("amountGross", 0),
                    booking.get("amountNett", 0),
                    booking.get("amountChannelFee", 0),
                    booking.get("amountTouristTax", 0),
                    booking.get("amountVat", 0),
                    booking.get("guestName", ""),
                    booking.get("phone", ""),
                    booking.get("reservationCode", ""),
                    booking.get("reservationDate", ""),
                    booking.get("status", ""),
                    booking.get("pricePerNight", 0),
                    booking.get("daysBeforeReservation", 0),
                    booking.get("addInfo", ""),
                    booking.get("year", 0),
                    booking.get("q", 0),
                    booking.get("m", 0),
                    booking.get("country", None),
                    booking.get("administration", ""),
                )

                cursor.execute(insert_query, values)
                inserted += 1

            self.connection.commit()
            cursor.close()
            return inserted

        except DatabaseError:
            return 0

    def insert_planned_bookings(self, bookings: list[dict]) -> int:
        """Insert planned bookings into bnbplanned table (delete by channel/listing/admin first)"""
        try:
            cursor = self.connection.cursor()

            if not bookings:
                cursor.close()
                return 0

            # Get unique channel/listing/administration combinations from new bookings
            channel_listing_admins = {
                (
                    booking.get("channel", ""),
                    booking.get("listing", ""),
                    booking.get("administration", ""),
                )
                for booking in bookings
            }

            # Delete existing records for these channel/listing/administration combinations
            for channel, listing, admin in channel_listing_admins:
                cursor.execute(
                    "DELETE FROM bnbplanned WHERE channel = %s AND listing = %s AND administration = %s",
                    (channel, listing, admin),
                )

            insert_query = """
            INSERT INTO bnbplanned 
            (sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
             amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat,
             guestName, phone, reservationCode, reservationDate, status, pricePerNight,
             daysBeforeReservation, addInfo, year, q, m, country, administration)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            inserted = 0
            for booking in bookings:
                values = (
                    booking.get("sourceFile", ""),
                    booking.get("channel", ""),
                    booking.get("listing", ""),
                    booking.get("checkinDate", ""),
                    booking.get("checkoutDate", ""),
                    booking.get("nights", 0),
                    booking.get("guests", 0),
                    booking.get("amountGross", 0),
                    booking.get("amountNett", 0),
                    booking.get("amountChannelFee", 0),
                    booking.get("amountTouristTax", 0),
                    booking.get("amountVat", 0),
                    booking.get("guestName", ""),
                    booking.get("phone", ""),
                    booking.get("reservationCode", ""),
                    booking.get("reservationDate", ""),
                    booking.get("status", ""),
                    booking.get("pricePerNight", 0),
                    booking.get("daysBeforeReservation", 0),
                    booking.get("addInfo", ""),
                    booking.get("year", 0),
                    booking.get("q", 0),
                    booking.get("m", 0),
                    booking.get("country", None),
                    booking.get("administration", ""),
                )

                cursor.execute(insert_query, values)
                inserted += 1

            self.connection.commit()
            cursor.close()
            return inserted

        except DatabaseError:
            return 0

    def insert_future_summary(self, summary_data: list[dict]) -> int:
        """Insert future summary into bnbfuture table"""
        if not summary_data:
            return 0

        insert_query = """
        INSERT INTO bnbfuture (channel, listing, amount, items, date)
        VALUES (%s, %s, %s, %s, %s)
        """

        try:
            cursor = self.connection.cursor()
            inserted = 0

            for item in summary_data:
                values = (
                    item.get("channel", ""),
                    item.get("listing", ""),
                    item.get("amount", 0),
                    item.get("items", 0),
                    item.get("date", ""),
                )

                cursor.execute(insert_query, values)
                inserted += 1

            self.connection.commit()
            cursor.close()
            return inserted

        except DatabaseError:
            return 0

    def get_existing_reservation_codes_for_channel(
        self, channel: str, tenant: str | None = None
    ) -> set:
        """Get existing reservation codes for a specific channel from bnb table"""
        try:
            cursor = self.connection.cursor()
            if tenant:
                cursor.execute(
                    "SELECT DISTINCT reservationCode FROM bnb WHERE channel = %s AND administration = %s AND reservationCode IS NOT NULL",
                    (channel, tenant),
                )
            else:
                cursor.execute(
                    "SELECT DISTINCT reservationCode FROM bnb WHERE channel = %s AND reservationCode IS NOT NULL",
                    (channel,),
                )
            codes = {str(row[0]) for row in cursor.fetchall()}
            cursor.close()
            return codes
        except DatabaseError:
            return set()

    def check_bnb_table_structure(self):
        """Check the actual structure of the bnb table"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(dialect.describe_table("bnb"))
            columns = cursor.fetchall()
            cursor.close()

            return [col[0] for col in columns]
        except DatabaseError:
            return []

    def write_bnb_future_summary(self) -> dict:
        """Write current planned BNB data summary to bnbfuture table"""
        try:
            # First ensure the table structure is correct
            self._ensure_bnbfuture_structure()

            cursor = self.connection.cursor(dictionary=True)

            # Get current planned bookings summary by channel and listing
            query = """
            SELECT 
                channel,
                listing,
                SUM(amountGross) as amount,
                COUNT(*) as items
            FROM bnbplanned 
            GROUP BY channel, listing
            """

            cursor.execute(query)
            results = cursor.fetchall()

            if not results:
                cursor.close()
                return {"success": False, "message": "No planned bookings found"}

            # Get current date
            from datetime import date

            current_date = date.today().strftime("%Y-%m-%d")

            # Check for existing records with same date and delete them
            delete_query = "DELETE FROM bnbfuture WHERE date = %s"
            cursor.execute(delete_query, (current_date,))

            # Insert new records (exclude id field to use AUTO_INCREMENT)
            insert_query = """
            INSERT INTO bnbfuture (date, channel, listing, amount, items)
            VALUES (%s, %s, %s, %s, %s)
            """

            inserted = 0
            for row in results:
                values = (
                    current_date,
                    row["channel"],
                    row["listing"],
                    round(float(row["amount"]), 2),
                    row["items"],
                )
                cursor.execute(insert_query, values)
                inserted += 1

            self.connection.commit()
            cursor.close()

            return {
                "success": True,
                "inserted": inserted,
                "date": current_date,
                "summary": results,
            }

        except DatabaseError as e:
            return {"success": False, "error": str(e)}

    def _ensure_bnbfuture_structure(self):
        """Ensure bnbfuture table has proper AUTO_INCREMENT id field"""
        try:
            cursor = self.connection.cursor()

            # Check if table exists and get structure
            cursor.execute("SHOW TABLES LIKE 'bnbfuture'")
            if not cursor.fetchone():
                # Create table if it doesn't exist
                create_query = """
                CREATE TABLE bnbfuture (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE,
                    channel VARCHAR(50),
                    listing VARCHAR(100),
                    amount DECIMAL(10,2),
                    items INT
                )
                """
                cursor.execute(create_query)
            else:
                # Check if id field has AUTO_INCREMENT
                cursor.execute("SHOW CREATE TABLE bnbfuture")
                create_statement = cursor.fetchone()[1]

                if "AUTO_INCREMENT" not in create_statement:
                    # Add AUTO_INCREMENT to id field
                    cursor.execute(
                        "ALTER TABLE bnbfuture MODIFY id INT AUTO_INCREMENT PRIMARY KEY"
                    )

            self.connection.commit()
            cursor.close()

        except DatabaseError as e:
            print(f"Error ensuring bnbfuture structure: {e}")
            if cursor:
                cursor.close()

    def get_str_summary(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        """Get STR performance summary from bnb table"""
        where_clause = ""
        params = []

        if start_date and end_date:
            where_clause = "WHERE checkinDate BETWEEN %s AND %s"
            params = [start_date, end_date]

        query = f"""
        SELECT 
            COUNT(*) as total_bookings,
            SUM(nights) as total_nights,
            SUM(amountGross) as total_gross,
            SUM(amountNett) as total_net,
            channel,
            COUNT(*) as channel_count
        FROM bnb 
        {where_clause}
        GROUP BY channel
        """

        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()

            summary = {
                "total_bookings": sum(r["total_bookings"] for r in results),
                "total_nights": sum(r["total_nights"] or 0 for r in results),
                "total_gross": sum(r["total_gross"] or 0 for r in results),
                "total_net": sum(r["total_net"] or 0 for r in results),
                "channels": {r["channel"]: r["channel_count"] for r in results},
            }

            return summary

        except DatabaseError:
            return {}

    def upsert_direct_bookings(
        self,
        bookings: list[dict],
        status_updates: list[dict] | None = None,
        tenant: str | None = None,
    ) -> dict:
        """
        Insert or update dfDirect bookings using reservationCode as composite key.

        Args:
            bookings: List of booking dicts from the parser (confirmed rows)
            status_updates: Optional list of dicts with reservationCode + status
                            for non-confirmed re-imported rows
            tenant: Optional tenant/administration identifier for tenant isolation

        Returns:
            dict with 'inserted': int, 'updated': int
            On error: dict with 'inserted': 0, 'updated': 0, 'error': str
        """
        if not bookings and not status_updates:
            return {"inserted": 0, "updated": 0}

        try:
            with self.transaction() as (cursor, _conn):
                # Step 1: Query existing reservation codes for channel "dfDirect"
                if tenant:
                    cursor.execute(
                        "SELECT DISTINCT reservationCode FROM bnb WHERE channel = 'dfDirect' AND administration = %s AND reservationCode IS NOT NULL",
                        (tenant,),
                    )
                else:
                    cursor.execute(
                        "SELECT DISTINCT reservationCode FROM bnb WHERE channel = 'dfDirect' AND reservationCode IS NOT NULL"
                    )

                existing_codes = {row["reservationCode"] for row in cursor.fetchall()}

                # Step 2: Separate bookings into new and existing
                new_bookings = []
                existing_bookings = []
                for booking in bookings:
                    code = booking.get("reservationCode", "")
                    if code in existing_codes:
                        existing_bookings.append(booking)
                    else:
                        new_bookings.append(booking)

                # Step 3: INSERT new bookings
                insert_query = """
                INSERT INTO bnb 
                (sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
                 amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat,
                 guestName, phone, reservationCode, reservationDate, status, pricePerNight,
                 daysBeforeReservation, addInfo, year, q, m, country, administration)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                for booking in new_bookings:
                    values = (
                        booking.get("sourceFile", ""),
                        booking.get("channel", ""),
                        booking.get("listing", ""),
                        booking.get("checkinDate", ""),
                        booking.get("checkoutDate", ""),
                        booking.get("nights", 0),
                        booking.get("guests", 0),
                        booking.get("amountGross", 0),
                        booking.get("amountNett", 0),
                        booking.get("amountChannelFee", 0),
                        booking.get("amountTouristTax", 0),
                        booking.get("amountVat", 0),
                        booking.get("guestName", ""),
                        booking.get("phone", ""),
                        booking.get("reservationCode", ""),
                        booking.get("reservationDate", ""),
                        booking.get("status", ""),
                        booking.get("pricePerNight", 0),
                        booking.get("daysBeforeReservation", 0),
                        booking.get("addInfo", ""),
                        booking.get("year", 0),
                        booking.get("q", 0),
                        booking.get("m", 0),
                        booking.get("country", None),
                        booking.get("administration", tenant),
                    )
                    cursor.execute(insert_query, values)

                # Step 4: UPDATE existing bookings
                if tenant:
                    update_query = """
                    UPDATE bnb SET
                        checkinDate = %s, checkoutDate = %s, listing = %s, guestName = %s,
                        nights = %s, guests = %s, amountGross = %s, amountNett = %s,
                        amountChannelFee = %s, amountVat = %s, amountTouristTax = %s,
                        status = %s, pricePerNight = %s, sourceFile = %s
                    WHERE reservationCode = %s AND channel = 'dfDirect' AND administration = %s
                    """
                else:
                    update_query = """
                    UPDATE bnb SET
                        checkinDate = %s, checkoutDate = %s, listing = %s, guestName = %s,
                        nights = %s, guests = %s, amountGross = %s, amountNett = %s,
                        amountChannelFee = %s, amountVat = %s, amountTouristTax = %s,
                        status = %s, pricePerNight = %s, sourceFile = %s
                    WHERE reservationCode = %s AND channel = 'dfDirect'
                    """

                for booking in existing_bookings:
                    values = (
                        booking.get("checkinDate", ""),
                        booking.get("checkoutDate", ""),
                        booking.get("listing", ""),
                        booking.get("guestName", ""),
                        booking.get("nights", 0),
                        booking.get("guests", 0),
                        booking.get("amountGross", 0),
                        booking.get("amountNett", 0),
                        booking.get("amountChannelFee", 0),
                        booking.get("amountVat", 0),
                        booking.get("amountTouristTax", 0),
                        booking.get("status", ""),
                        booking.get("pricePerNight", 0),
                        booking.get("sourceFile", ""),
                        booking.get("reservationCode", ""),
                    )
                    if tenant:
                        values = values + (tenant,)
                    cursor.execute(update_query, values)

                # Step 5: Apply status_updates for non-confirmed re-imported rows
                if status_updates:
                    if tenant:
                        status_update_query = """
                        UPDATE bnb SET status = %s
                        WHERE reservationCode = %s AND channel = 'dfDirect' AND administration = %s
                        """
                    else:
                        status_update_query = """
                        UPDATE bnb SET status = %s
                        WHERE reservationCode = %s AND channel = 'dfDirect'
                        """

                    for update in status_updates:
                        code = update.get("reservationCode", "")
                        status = update.get("status", "")
                        if code and status and code in existing_codes:
                            if tenant:
                                cursor.execute(
                                    status_update_query, (status, code, tenant)
                                )
                            else:
                                cursor.execute(status_update_query, (status, code))

            return {
                "inserted": len(new_bookings),
                "updated": len(existing_bookings),
                "updated_codes": [
                    b.get("reservationCode", "") for b in existing_bookings
                ],
            }

        except DatabaseError as e:
            return {"inserted": 0, "updated": 0, "updated_codes": [], "error": str(e)}

    def get_unenriched_direct_codes(self, tenant: str) -> list[str]:
        """Get dfDirect reservation codes that have no phone/country data."""
        query = """
            SELECT reservationCode FROM bnb
            WHERE channel = 'dfDirect'
              AND administration = %s
              AND (phone IS NULL OR phone = '')
              AND (country IS NULL OR country = '')
            ORDER BY checkinDate DESC
            LIMIT 50
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(query, (tenant,))
            result = cursor.fetchall()
            cursor.close()
            return [row["reservationCode"] for row in result] if result else []
        except DatabaseError:
            return []

    def apply_stripe_enrichments(self, enrichments: list[dict], tenant: str) -> int:
        """Apply Stripe-sourced customer data and actual fee to bnb records.

        When stripe_fee is available, it replaces the estimated 4% channel fee
        and triggers recalculation of amountNett and pricePerNight.
        """
        update_with_fee_query = """
            UPDATE bnb
            SET phone = COALESCE(NULLIF(%s, ''), phone),
                country = COALESCE(NULLIF(%s, ''), country),
                amountChannelFee = %s,
                amountNett = amountGross - %s - amountVat - amountTouristTax,
                pricePerNight = CASE
                    WHEN nights > 0 THEN ROUND((amountGross - %s - amountVat - amountTouristTax) / nights, 2)
                    ELSE 0
                END,
                addInfo = CASE
                    WHEN %s IS NOT NULL AND %s != ''
                    THEN CONCAT(COALESCE(addInfo, ''), ' | email:', %s)
                    ELSE addInfo
                END
            WHERE reservationCode = %s
              AND channel = 'dfDirect'
              AND administration = %s
        """
        update_no_fee_query = """
            UPDATE bnb
            SET phone = COALESCE(NULLIF(%s, ''), phone),
                country = COALESCE(NULLIF(%s, ''), country),
                addInfo = CASE
                    WHEN %s IS NOT NULL AND %s != ''
                    THEN CONCAT(COALESCE(addInfo, ''), ' | email:', %s)
                    ELSE addInfo
                END
            WHERE reservationCode = %s
              AND channel = 'dfDirect'
              AND administration = %s
        """
        try:
            cursor = self.connection.cursor()
            updated = 0
            for e in enrichments:
                email = e.get("email") or ""
                phone = e.get("phone") or ""
                country = e.get("country") or ""
                stripe_fee = e.get("stripe_fee")
                code = e["reservationCode"]

                if stripe_fee is not None:
                    fee = round(stripe_fee, 2)
                    cursor.execute(
                        update_with_fee_query,
                        (
                            phone,
                            country,
                            fee,
                            fee,
                            fee,
                            email,
                            email,
                            email,
                            code,
                            tenant,
                        ),
                    )
                else:
                    cursor.execute(
                        update_no_fee_query,
                        (phone, country, email, email, email, code, tenant),
                    )
                updated += 1

            self.connection.commit()
            cursor.close()
            return updated
        except DatabaseError as e:
            print(f"Error applying Stripe enrichments: {e}", flush=True)
            return 0

    def update_from_payout(self, payout_updates: list[dict]) -> dict:
        """
        Update existing bookings with Payout CSV data

        Args:
            payout_updates: List of update records from Payout CSV processing

        Returns:
            dict with update results: {
                'updated': count of updated records,
                'not_found': list of reservation codes not found,
                'errors': list of error messages
            }
        """
        if not payout_updates:
            return {"updated": 0, "not_found": [], "errors": ["No updates provided"]}

        results = {"updated": 0, "not_found": [], "errors": []}

        update_query = """
        UPDATE bnb 
        SET 
            amountGross = %s,
            amountChannelFee = %s,
            amountVat = %s,
            amountTouristTax = %s,
            amountNett = %s,
            pricePerNight = %s,
            sourceFile = %s
        WHERE reservationCode = %s AND channel = 'booking.com'
        """

        try:
            cursor = self.connection.cursor()

            for update in payout_updates:
                reservation_code = update.get("reservationCode", "")

                # Check if reservation exists
                cursor.execute(
                    "SELECT id FROM bnb WHERE reservationCode = %s AND channel = 'booking.com'",
                    (reservation_code,),
                )

                if not cursor.fetchone():
                    results["not_found"].append(reservation_code)
                    continue

                # Update the record
                values = (
                    update.get("amountGross", 0),
                    update.get("amountChannelFee", 0),
                    update.get("amountVat", 0),
                    update.get("amountTouristTax", 0),
                    update.get("amountNett", 0),
                    update.get("pricePerNight", 0),
                    update.get("sourceFile", ""),
                    reservation_code,
                )

                cursor.execute(update_query, values)
                results["updated"] += 1

            self.connection.commit()
            cursor.close()

            return results

        except DatabaseError as e:
            results["errors"].append(f"Database error: {e!s}")
            return results
