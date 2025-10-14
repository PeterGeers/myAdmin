import mysql.connector
from typing import List, Dict
from database import Database

class STRDatabase(Database):
    def __init__(self, test_mode: bool = False):
        super().__init__(test_mode)
        # Uses existing tables: bnb, bnbplanned, bnbfuture
    
    def insert_realised_bookings(self, bookings: List[Dict]) -> int:
        """Insert realised bookings into bnb table"""
        if not bookings:
            return 0
        
        # Get existing reservation codes to avoid duplicates
        existing_codes = self._get_existing_reservation_codes()
        new_bookings = [b for b in bookings if b.get('reservationCode') not in existing_codes]
        
        if not new_bookings:
            return 0
        
        insert_query = """
        INSERT INTO bnb 
        (sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
         amountGross, amountChannelFee, guestName, reservationCode, reservationDate,
         status, addInfo, amountVat, amountTouristTax, amountNett, pricePerNight,
         year, quarter, month, daysBeforeReservation)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            cursor = self.connection.cursor()
            inserted = 0
            
            for booking in new_bookings:
                values = (
                    booking.get('sourceFile', ''),
                    booking.get('channel', ''),
                    booking.get('listing', ''),
                    booking.get('checkinDate', ''),
                    booking.get('checkoutDate', ''),
                    booking.get('nights', 0),
                    booking.get('guests', 0),
                    booking.get('amountGross', 0),
                    booking.get('amountChannelFee', 0),
                    booking.get('guestName', ''),
                    booking.get('reservationCode', ''),
                    booking.get('reservationDate', ''),
                    booking.get('status', ''),
                    booking.get('addInfo', ''),
                    booking.get('amountVat', 0),
                    booking.get('amountTouristTax', 0),
                    booking.get('amountNett', 0),
                    booking.get('pricePerNight', 0),
                    booking.get('year', 0),
                    booking.get('quarter', 0),
                    booking.get('month', 0),
                    booking.get('daysBeforeReservation', 0)
                )
                
                cursor.execute(insert_query, values)
                inserted += 1
            
            self.connection.commit()
            cursor.close()
            return inserted
            
        except mysql.connector.Error as e:
            print(f"Error inserting realised bookings: {e}")
            return 0
    
    def insert_planned_bookings(self, bookings: List[Dict]) -> int:
        """Insert planned bookings into bnbplanned table (clear first like R script)"""
        try:
            cursor = self.connection.cursor()
            
            # Clear bnbplanned table first (like R script)
            cursor.execute("DELETE FROM bnbplanned")
            
            if not bookings:
                self.connection.commit()
                cursor.close()
                return 0
            
            insert_query = """
            INSERT INTO bnbplanned 
            (sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
             amountGross, amountChannelFee, guestName, reservationCode, reservationDate,
             status, addInfo, amountVat, amountTouristTax, amountNett, pricePerNight,
             year, quarter, month, daysBeforeReservation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            inserted = 0
            for booking in bookings:
                values = (
                    booking.get('sourceFile', ''),
                    booking.get('channel', ''),
                    booking.get('listing', ''),
                    booking.get('checkinDate', ''),
                    booking.get('checkoutDate', ''),
                    booking.get('nights', 0),
                    booking.get('guests', 0),
                    booking.get('amountGross', 0),
                    booking.get('amountChannelFee', 0),
                    booking.get('guestName', ''),
                    booking.get('reservationCode', ''),
                    booking.get('reservationDate', ''),
                    booking.get('status', ''),
                    booking.get('addInfo', ''),
                    booking.get('amountVat', 0),
                    booking.get('amountTouristTax', 0),
                    booking.get('amountNett', 0),
                    booking.get('pricePerNight', 0),
                    booking.get('year', 0),
                    booking.get('quarter', 0),
                    booking.get('month', 0),
                    booking.get('daysBeforeReservation', 0)
                )
                
                cursor.execute(insert_query, values)
                inserted += 1
            
            self.connection.commit()
            cursor.close()
            return inserted
            
        except mysql.connector.Error as e:
            print(f"Error inserting planned bookings: {e}")
            return 0
    
    def insert_future_summary(self, summary_data: List[Dict]) -> int:
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
                    item.get('channel', ''),
                    item.get('listing', ''),
                    item.get('amount', 0),
                    item.get('items', 0),
                    item.get('date', '')
                )
                
                cursor.execute(insert_query, values)
                inserted += 1
            
            self.connection.commit()
            cursor.close()
            return inserted
            
        except mysql.connector.Error as e:
            print(f"Error inserting future summary: {e}")
            return 0
    
    def _get_existing_reservation_codes(self) -> set:
        """Get existing reservation codes from bnb table"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT DISTINCT reservationCode FROM bnb WHERE reservationCode IS NOT NULL")
            codes = {row[0] for row in cursor.fetchall()}
            cursor.close()
            return codes
        except mysql.connector.Error as e:
            print(f"Error getting existing codes: {e}")
            return set()
    
    def get_str_summary(self, start_date: str = None, end_date: str = None) -> Dict:
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
                'total_bookings': sum(r['total_bookings'] for r in results),
                'total_nights': sum(r['total_nights'] or 0 for r in results),
                'total_gross': sum(r['total_gross'] or 0 for r in results),
                'total_net': sum(r['total_net'] or 0 for r in results),
                'channels': {r['channel']: r['channel_count'] for r in results}
            }
            
            return summary
            
        except mysql.connector.Error as e:
            print(f"Error getting STR summary: {e}")
            return {}