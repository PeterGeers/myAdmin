import pandas as pd
import re
from datetime import datetime, date
from typing import Dict, List, Optional
import os

class STRProcessor:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.platforms = ['airbnb', 'booking', 'direct']
        self.download_folder = "C:\\Users\\peter\\Downloads"
        
        # Tax parameters (change annually on Jan 1st)
        self.vat_rate = 9  # VAT percentage
        self.vat_base = 109  # Base for VAT calculation (100 + VAT rate)
        self.tourist_tax_rate = 6  # Tourist tax percentage
        self.tourist_tax_base = 106  # Base for tourist tax calculation
        self.price_uplift = 0.054409  # Uplift from commissionable amount to total price
        
        # Property mappings from config
        self.property_mappings = {
            'green': 'Green Apartment',
            'child': 'Garden House', 
            'red': 'Red Apartment'
        }
    
    def _normalize_listing_name(self, listing: str) -> str:
        """Normalize listing names to standard format"""
        import re
        if not listing:
            return listing
        
        # Green Studio: One|groen|Groen|green|Green
        if re.search(r'One|groen|Groen|green|Green', listing):
            return 'Green Studio'
        
        # Child Friendly: ^Apartment$|Tuinhuis|[G|g]arden|[C|c]hild
        if re.search(r'^Apartment$|Tuinhuis|[Gg]arden|[Cc]hild', listing):
            return 'Child Friendly'
        
        # Red Studio: Rode|rode|Red|Rood|rood|red
        if re.search(r'Rode|rode|Red|Rood|rood|red', listing):
            return 'Red Studio'
        
        return listing
    
    def scan_str_files(self, folder_path: str = None) -> Dict[str, List[str]]:
        """Scan folder for STR files by platform"""
        if not folder_path:
            folder_path = self.download_folder
            
        files = {
            'airbnb': [],
            'booking': [],
            'direct': []
        }
        
        try:
            for file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path):
                    if 'reservation' in file.lower() and file.endswith('.csv'):
                        files['airbnb'].append(file_path)
                    elif 'check-in' in file.lower() and file.endswith(('.xls', '.xlsx')):
                        files['booking'].append(file_path)
                    elif 'jabakirechtstreeks' in file.lower() and file.endswith(('.xlsx')):
                        files['direct'].append(file_path)
        except Exception as e:
            print(f"Error scanning folder: {e}")
            
        return files
    
    def process_str_files(self, file_paths: List[str], platform: str) -> List[Dict]:
        """Process multiple STR files for a platform"""
        all_bookings = []
        
        for file_path in file_paths:
            try:
                bookings = self._process_single_file(file_path, platform)
                all_bookings.extend(bookings)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                
        return all_bookings
    
    def _process_single_file(self, file_path: str, platform: str) -> List[Dict]:
        """Process single STR file based on platform"""
        platform = platform.lower()
        
        if platform == 'airbnb':
            return self._process_airbnb(file_path)
        elif platform in ['booking', 'booking.com']:
            return self._process_booking(file_path)
        elif platform == 'direct':
            return self._process_direct(file_path)
        else:
            raise ValueError(f"Unsupported platform: {platform}")
    

    
    def _process_airbnb(self, file_path: str) -> List[Dict]:
        """Process Airbnb CSV export"""
        try:
            df = pd.read_csv(file_path)
            transactions = []
            
            for _, row in df.iterrows():
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
                
                # Parse earnings "€ 190,10" format like R getAmount() function
                try:
                    if pd.isna(earnings_str) or earnings_str == '':
                        earnings = 0
                    else:
                        # Remove € symbol, spaces, and convert comma to dot
                        clean_amount = str(earnings_str).replace('€', '').replace(' ', '').replace(',', '.')
                        earnings = float(clean_amount) if clean_amount else 0
                except (ValueError, TypeError):
                    earnings = 0
                
                # Skip cancelled bookings with no earnings (like R code filter)
                if 'Geannuleerd' in status and earnings == 0:
                    continue
                
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
                
                # Apply same VAT/tourist tax as Booking.com (from writeJaBakiMySQL.R)
                amount_vat = (gross_amount / 115) * 9
                amount_tourist_tax = (gross_amount / 115) * 6
                amount_nett = gross_amount - amount_tourist_tax - amount_vat - amount_channel_fee
                
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
                add_info = '|'.join(str(row.get(col, '')) for col in df.columns)
                
                # Source file info
                source_file = f"{datetime.now().strftime('%Y-%m-%d')} {os.path.basename(file_path)}"
                
                transaction = {
                    'sourceFile': source_file,
                    'channel': 'airbnb',
                    'listing': self._normalize_listing_name(str(listing)),
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
                    'amountVat': round(float(amount_vat), 2),
                    'amountTouristTax': round(float(amount_tourist_tax), 2),
                    'amountNett': round(float(amount_nett), 2),
                    'pricePerNight': round(float(price_per_night), 2),
                    'year': year,
                    'q': quarter,
                    'm': month,
                    'daysBeforeReservation': days_before_reservation
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            return []
    
    def _process_booking(self, file_path: str) -> List[Dict]:
        """Process Booking.com Excel/CSV export"""
        try:
            # Handle both .xls/.xlsx and .csv files
            if file_path.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path)
            

            
            transactions = []
            
            for _, row in df.iterrows():
                # Map actual Booking.com columns
                checkin_date = row.get('Check-in', '')
                checkout_date = row.get('Check-out', '')
                guest_name = row.get('Guest name(s)', '')
                unit_type = row.get('Unit type', '')
                nights = row.get('Duration (nights)', 0)
                price_str = row.get('Price', '0')
                booking_id = row.get('Book number', '')
                status = row.get('Status', 'ok')
                commission_amount = row.get('Commission amount', '')
                
                # Skip cancelled bookings with no commission (no revenue)
                if status == 'cancelled_by_guest' and (pd.isna(commission_amount) or commission_amount == '' or commission_amount is None):
                    continue
                
                # Extract numeric price from "101.468 EUR" format
                try:
                    if isinstance(price_str, str) and 'EUR' in price_str:
                        base_price = float(price_str.replace(' EUR', '').replace(',', '.'))
                    else:
                        base_price = float(price_str) if price_str else 0
                except (ValueError, TypeError):
                    base_price = 0
                
                # Calculate tourist tax amount and add to base price for gross amount
                tourist_tax_amount = (base_price / 100) * self.tourist_tax_rate
                price = round(base_price + tourist_tax_amount, 2)
                
                # Determine status based on check-in date and booking status
                from datetime import datetime, date
                today = date.today()
                try:
                    checkin_dt = datetime.strptime(checkin_date, '%Y-%m-%d').date()
                    if status == 'cancelled_by_guest':
                        booking_status = 'cancelled'
                    elif checkin_dt > today:
                        booking_status = 'planned'
                    else:
                        booking_status = 'realised'
                except:
                    booking_status = 'realised'
                
                # Calculate additional fields based on R script logic
                channel_fee_factor = 0.15  # 15% like in R script
                paid_out = price / (1 + channel_fee_factor)  # Reverse calculate paid out
                amount_channel_fee = paid_out * channel_fee_factor
                amount_vat = (price / self.vat_base) * self.vat_rate
                amount_tourist_tax = tourist_tax_amount
                amount_nett = price - amount_vat - amount_tourist_tax - amount_channel_fee
                
                # Extract persons from Excel data
                persons = row.get('Persons', 0) or 0
                adults = row.get('Adults', 0) or 0
                children = row.get('Children', 0) or 0
                guests = persons if persons > 0 else (adults + children)
                
                # Calculate dates and periods
                try:
                    checkin_dt = datetime.strptime(checkin_date, '%Y-%m-%d')
                    checkout_dt = datetime.strptime(checkout_date, '%Y-%m-%d')
                    reservation_dt = datetime.strptime(str(row.get('Booked on', '')).split(' ')[0], '%Y-%m-%d')
                    
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
                
                # Additional info - concatenate all Excel fields with |
                add_info = '|'.join(str(row.get(col, '')) for col in df.columns)
                
                # Source file info
                source_file = f"{datetime.now().strftime('%Y-%m-%d')} {os.path.basename(file_path)}"
                
                transaction = {
                    'sourceFile': source_file,
                    'channel': 'booking.com',
                    'listing': self._normalize_listing_name(str(unit_type)),
                    'checkinDate': str(checkin_date),
                    'checkoutDate': str(checkout_date),
                    'nights': int(nights) if nights else 0,
                    'guests': int(guests),
                    'amountGross': round(float(price), 2),
                    'amountChannelFee': round(float(amount_channel_fee), 2),
                    'guestName': str(guest_name),
                    'phone': '',  # Phone not available in booking.com data
                    'reservationCode': str(booking_id),
                    'reservationDate': reservation_dt.strftime('%Y-%m-%d'),
                    'status': str(booking_status),
                    'addInfo': add_info,
                    'amountVat': round(float(amount_vat), 2),
                    'amountTouristTax': round(float(amount_tourist_tax), 2),
                    'amountNett': round(float(amount_nett), 2),
                    'pricePerNight': round(float(price_per_night), 2),
                    'year': year,
                    'q': quarter,
                    'm': month,
                    'daysBeforeReservation': days_before_reservation
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            return []
    
    def _process_direct(self, file_path: str) -> List[Dict]:
        """Process direct bookings Excel/CSV"""
        try:
            # Handle both .xlsx and .csv files
            if file_path.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path)
            
            transactions = []
            
            for _, row in df.iterrows():
                # Filter only reservation type records like R code
                record_type = row.get('type', '')
                if str(record_type).lower() != 'reservation':
                    continue
                
                # Map direct booking columns
                checkin_date = row.get('startDate', '')
                guest_name = row.get('guestName', '')
                listing = row.get('listing', '')
                nights = row.get('nights', 0)
                guests = row.get('guests', 0)
                gross_amount = row.get('amountGross', 0)
                paid_out = row.get('paidOut', 0)
                # Calculate channel fee as amountGross - paidOut
                channel_fee = float(gross_amount) - float(paid_out)
                booking_id = row.get('reservationCode', '')
                trade_type = row.get('typeTrade', '')
                details = row.get('details', '')
                currency = row.get('currency', '')
                cleaning_fee = row.get('cleaningFee', 0)
                
                # Determine channel based on typeTrade like R code
                if 'goodwin' in str(trade_type).lower():
                    channel = 'dfDirect'
                elif 'vrbo' in str(trade_type).lower():
                    channel = 'VRBO'
                else:
                    channel = 'dfZwart'
                
                # Determine booking status based on check-in date
                today = date.today()
                try:
                    checkin_dt = datetime.strptime(str(checkin_date), '%Y-%m-%d').date()
                    if checkin_dt > today:
                        booking_status = 'planned'
                    else:
                        booking_status = 'realised'
                except:
                    booking_status = 'realised'
                
                # Calculate checkout date
                try:
                    checkin_dt = datetime.strptime(str(checkin_date), '%Y-%m-%d')
                    checkout_dt = checkin_dt + pd.Timedelta(days=int(nights))
                    checkout_date = checkout_dt.strftime('%Y-%m-%d')
                except:
                    checkout_date = str(checkin_date)
                
                # Apply same VAT/tourist tax as other channels (from generic part)
                amount_vat = (float(gross_amount) / 115) * 9
                amount_tourist_tax = (float(gross_amount) / 115) * 6
                amount_nett = float(gross_amount) - amount_tourist_tax - amount_vat - float(channel_fee)
                
                # Reservation date = checkin date (like R code)
                reservation_date = checkin_date
                
                # Calculate dates and periods
                try:
                    checkin_dt = datetime.strptime(str(checkin_date), '%Y-%m-%d')
                    reservation_dt = checkin_dt  # Same as checkin date
                    
                    year = checkin_dt.year
                    quarter = (checkin_dt.month - 1) // 3 + 1
                    month = checkin_dt.month
                    days_before_reservation = 0  # Same date
                except Exception as e:
                    # If date parsing fails, try to extract from string
                    try:
                        # Fallback: use current date for calculations
                        now = datetime.now()
                        year = now.year
                        quarter = (now.month - 1) // 3 + 1
                        month = now.month
                        days_before_reservation = 0
                        reservation_dt = now
                    except:
                        year = 2025
                        quarter = 4
                        month = 10
                        days_before_reservation = 0
                        reservation_dt = datetime.now()
                
                # Price per night based on net amount
                price_per_night = amount_nett / int(nights) if int(nights) > 0 else 0
                
                # Additional info like R code
                filename = os.path.basename(file_path)
                add_info = f"{filename} | {guest_name} | {record_type} | {trade_type} | {details} | {booking_id} | {currency} | {gross_amount} | {channel_fee} | {cleaning_fee}"
                
                # Source file info
                source_file = f"{datetime.now().strftime('%Y-%m-%d')} {os.path.basename(file_path)}"
                
                transaction = {
                    'sourceFile': source_file,
                    'channel': channel,
                    'listing': self._normalize_listing_name(str(listing)),
                    'checkinDate': str(checkin_date),
                    'checkoutDate': checkout_date,
                    'nights': int(nights) if nights else 0,
                    'guests': int(guests) if guests else 0,
                    'amountGross': round(float(gross_amount), 2),
                    'amountChannelFee': round(float(channel_fee), 2),
                    'guestName': str(guest_name).replace("'", " "),  # Remove quotes like R code
                    'phone': '',  # Not available in direct bookings
                    'reservationCode': str(booking_id),
                    'reservationDate': reservation_dt.strftime('%Y-%m-%d'),
                    'status': str(booking_status),
                    'addInfo': add_info,
                    'amountVat': round(float(amount_vat), 2),
                    'amountTouristTax': round(float(amount_tourist_tax), 2),
                    'amountNett': round(float(amount_nett), 2),
                    'pricePerNight': round(float(price_per_night), 2),
                    'year': year,
                    'q': quarter,
                    'm': month,
                    'daysBeforeReservation': days_before_reservation
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            return []
    
    def _parse_date(self, date_str: str) -> str:
        """Parse various date formats"""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        
        # Try common date formats
        formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']
        
        for fmt in formats:
            try:
                return datetime.strptime(str(date_str), fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return datetime.now().strftime('%Y-%m-%d')
    
    def generate_summary(self, bookings: List[Dict]) -> Dict:
        """Generate STR performance summary"""
        if not bookings:
            return {}
        
        df = pd.DataFrame(bookings)
        
        return {
            'total_bookings': len(bookings),
            'total_nights': df['nights'].sum() if 'nights' in df.columns else 0,
            'total_gross': df['amountGross'].sum() if 'amountGross' in df.columns else 0,
            'total_net': df['amountNett'].sum() if 'amountNett' in df.columns else 0,
            'avg_nightly_rate': df['pricePerNight'].mean() if 'pricePerNight' in df.columns else 0,
            'channels': df['channel'].value_counts().to_dict() if 'channel' in df.columns else {},
            'listings': df['listing'].value_counts().to_dict() if 'listing' in df.columns else {},
            'date_range': {
                'start': df['checkinDate'].min() if 'checkinDate' in df.columns else '',
                'end': df['checkinDate'].max() if 'checkinDate' in df.columns else ''
            }
        }
    
    def separate_by_status(self, bookings: List[Dict]) -> Dict[str, List[Dict]]:
        """Separate bookings by status and check for duplicates"""
        try:
            from str_database import STRDatabase
            
            # Group bookings by channel and get existing codes for each channel
            str_db = STRDatabase(test_mode=self.test_mode)
            
            # Get unique channels from bookings
            channels = set(booking.get('channel', '') for booking in bookings)
            existing_codes_by_channel = {}
            

            
            for channel in channels:
                if channel:
                    existing_codes = str_db.get_existing_reservation_codes_for_channel(channel)
                    existing_codes_by_channel[channel] = existing_codes
            
            realised = []
            planned = []
            already_loaded = []
            
            for booking in bookings:
                channel = booking.get('channel', '')
                code = str(booking.get('reservationCode', ''))
                status = booking.get('status', '')
                

                
                # Check if this reservation code already exists for this channel
                if channel in existing_codes_by_channel and code in existing_codes_by_channel[channel]:
                    already_loaded.append(booking)
                elif status in ['realised', 'cancelled']:
                    realised.append(booking)
                elif status == 'planned':
                    planned.append(booking)
                else:
                    realised.append(booking)  # Default to realised
            

            
            return {
                'realised': realised,
                'planned': planned,
                'already_loaded': already_loaded
            }
        except Exception as e:
            pass
            
            # Fallback to original logic if database check fails
            realised = [b for b in bookings if b.get('status') in ['realised', 'cancelled']]
            planned = [b for b in bookings if b.get('status') == 'planned']
            
            return {
                'realised': realised,
                'planned': planned,
                'already_loaded': []
            }
    
    def generate_future_summary(self, planned_bookings: List[Dict]) -> List[Dict]:
        """Generate future bookings summary by channel and listing"""
        if not planned_bookings:
            return []
        
        df = pd.DataFrame(planned_bookings)
        
        # Group by channel and listing
        summary = df.groupby(['channel', 'listing']).agg({
            'amountGross': 'sum',
            'reservationCode': 'count'
        }).reset_index()
        
        summary.columns = ['channel', 'listing', 'amount', 'items']
        summary['date'] = date.today().strftime('%Y-%m-%d')
        
        return summary.to_dict('records')