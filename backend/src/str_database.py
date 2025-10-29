import mysql.connector
from typing import List, Dict
from database import DatabaseManager

class STRDatabase(DatabaseManager):
    def __init__(self, test_mode: bool = False):
        super().__init__(test_mode)
        self.connection = self.get_connection()
        # Uses existing tables: bnb, bnbplanned, bnbfuture
    
    def insert_realised_bookings(self, bookings: List[Dict]) -> int:
        """Insert realised bookings into bnb table"""
        if not bookings:
            return 0
        
        # Get existing reservation codes by channel to avoid duplicates
        new_bookings = []
        
        for booking in bookings:
            channel = booking.get('channel', '')
            code = booking.get('reservationCode', '')
            existing_codes = self.get_existing_reservation_codes_for_channel(channel)
            if code not in existing_codes:
                new_bookings.append(booking)
        
        if not new_bookings:
            return 0
        
        insert_query = """
        INSERT INTO bnb 
        (sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
         amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat,
         guestName, phone, reservationCode, reservationDate, status, pricePerNight,
         daysBeforeReservation, addInfo, year, q, m)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            cursor = self.connection.cursor()
            inserted = 0
            
            # Check table structure first
            available_columns = self.check_bnb_table_structure()
            
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
                    booking.get('amountNett', 0),
                    booking.get('amountChannelFee', 0),
                    booking.get('amountTouristTax', 0),
                    booking.get('amountVat', 0),
                    booking.get('guestName', ''),
                    booking.get('phone', ''),
                    booking.get('reservationCode', ''),
                    booking.get('reservationDate', ''),
                    booking.get('status', ''),
                    booking.get('pricePerNight', 0),
                    booking.get('daysBeforeReservation', 0),
                    booking.get('addInfo', ''),
                    booking.get('year', 0),
                    booking.get('q', 0),
                    booking.get('m', 0)
                )
                
                cursor.execute(insert_query, values)
                inserted += 1
            
            self.connection.commit()
            cursor.close()
            return inserted
            
        except mysql.connector.Error as e:
            return 0
    
    def insert_planned_bookings(self, bookings: List[Dict]) -> int:
        """Insert planned bookings into bnbplanned table (delete by channel/listing first)"""
        try:
            cursor = self.connection.cursor()
            
            if not bookings:
                cursor.close()
                return 0
            
            # Get unique channel/listing combinations from new bookings
            channel_listings = set((booking.get('channel', ''), booking.get('listing', '')) for booking in bookings)
            
            # Delete existing records for these channel/listing combinations
            for channel, listing in channel_listings:
                cursor.execute("DELETE FROM bnbplanned WHERE channel = %s AND listing = %s", (channel, listing))
            
            insert_query = """
            INSERT INTO bnbplanned 
            (sourceFile, channel, listing, checkinDate, checkoutDate, nights, guests,
             amountGross, amountNett, amountChannelFee, amountTouristTax, amountVat,
             guestName, phone, reservationCode, reservationDate, status, pricePerNight,
             daysBeforeReservation, addInfo, year, q, m)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    booking.get('amountNett', 0),
                    booking.get('amountChannelFee', 0),
                    booking.get('amountTouristTax', 0),
                    booking.get('amountVat', 0),
                    booking.get('guestName', ''),
                    booking.get('phone', ''),
                    booking.get('reservationCode', ''),
                    booking.get('reservationDate', ''),
                    booking.get('status', ''),
                    booking.get('pricePerNight', 0),
                    booking.get('daysBeforeReservation', 0),
                    booking.get('addInfo', ''),
                    booking.get('year', 0),
                    booking.get('q', 0),
                    booking.get('m', 0)
                )
                
                cursor.execute(insert_query, values)
                inserted += 1
            
            self.connection.commit()
            cursor.close()
            return inserted
            
        except mysql.connector.Error as e:
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
            return 0
    
    def get_existing_reservation_codes_for_channel(self, channel: str) -> set:
        """Get existing reservation codes for a specific channel from bnb table"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT DISTINCT reservationCode FROM bnb WHERE channel = %s AND reservationCode IS NOT NULL", (channel,))
            codes = {str(row[0]) for row in cursor.fetchall()}
            cursor.close()
            return codes
        except mysql.connector.Error as e:
            return set()
    
    def check_bnb_table_structure(self):
        """Check the actual structure of the bnb table"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("DESCRIBE bnb")
            columns = cursor.fetchall()
            cursor.close()
            

            
            return [col[0] for col in columns]
        except mysql.connector.Error as e:
            return []
    
    def write_bnb_future_summary(self) -> Dict:
        """Write current planned BNB data summary to bnbfuture table"""
        try:
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
                return {'success': False, 'message': 'No planned bookings found'}
            
            # Get current date
            from datetime import date
            current_date = date.today().strftime('%Y-%m-%d')
            
            # Check for existing records with same date and delete them
            delete_query = "DELETE FROM bnbfuture WHERE date = %s"
            cursor.execute(delete_query, (current_date,))
            
            # Insert new records
            insert_query = """
            INSERT INTO bnbfuture (date, channel, listing, amount, items)
            VALUES (%s, %s, %s, %s, %s)
            """
            
            inserted = 0
            for row in results:
                values = (
                    current_date,
                    row['channel'],
                    row['listing'],
                    round(float(row['amount']), 2),
                    row['items']
                )
                cursor.execute(insert_query, values)
                inserted += 1
            
            self.connection.commit()
            cursor.close()
            
            return {
                'success': True,
                'inserted': inserted,
                'date': current_date,
                'summary': results
            }
            
        except mysql.connector.Error as e:
            return {'success': False, 'error': str(e)}
    
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
            return {}