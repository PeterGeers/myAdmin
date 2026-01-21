import pandas as pd
import re
from datetime import datetime, date
from typing import Dict, List, Optional
import os
from country_detector import detect_country

class STRProcessor:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.platforms = ['airbnb', 'booking', 'direct']
        self.download_folder = "C:\\Users\\peter\\Downloads"
        
        # Property mappings from config
        self.property_mappings = {
            'green': 'Green Apartment',
            'child': 'Garden House', 
            'red': 'Red Apartment'
        }
    
    def get_tax_rates(self, checkin_date: str) -> dict:
        """Get VAT and tourist tax rates based on check-in date"""
        try:
            # Parse check-in date
            if isinstance(checkin_date, str):
                checkin_dt = datetime.strptime(checkin_date, '%Y-%m-%d').date()
            else:
                checkin_dt = checkin_date
            
            # 2026 rate changes effective from January 1, 2026
            rate_change_date = date(2026, 1, 1)
            
            if checkin_dt >= rate_change_date:
                # 2026 rates and later
                return {
                    'vat_rate': 21.0,  # Changed from 9% to 21%
                    'vat_base': 121.0,  # Base for VAT calculation (100 + VAT rate)
                    'tourist_tax_rate': 6.9,  # Changed from 6.02% to 6.9%
                    'tourist_tax_base': 106.9,  # Base for tourist tax calculation
                    'price_uplift': 0.054409  # Uplift from commissionable amount to total price
                }
            else:
                # Pre-2026 rates
                return {
                    'vat_rate': 9.0,  # Original 9% VAT
                    'vat_base': 109.0,  # Base for VAT calculation (100 + VAT rate)
                    'tourist_tax_rate': 6.02,  # Original 6.02% tourist tax
                    'tourist_tax_base': 106.02,  # Base for tourist tax calculation
                    'price_uplift': 0.054409  # Uplift from commissionable amount to total price
                }
        except Exception as e:
            print(f"Error parsing check-in date {checkin_date}: {e}")
            # Default to current rates if date parsing fails
            return {
                'vat_rate': 9.0,
                'vat_base': 109.0,
                'tourist_tax_rate': 6.02,
                'tourist_tax_base': 106.02,
                'price_uplift': 0.054409
            }

    def calculate_str_taxes(self, gross_amount: float, checkin_date: str, channel_fee: float = 0.0) -> dict:
        """
        Generic tax calculation function for all STR channels
        
        Args:
            gross_amount: Total gross booking amount
            checkin_date: Check-in date in YYYY-MM-DD or DD-MM-YYYY format
            channel_fee: Channel commission fee (optional)
            
        Returns:
            dict with calculated amounts: vat, tourist_tax, net_amount, tax_rates_used
        """
        try:
            # Normalize date format to YYYY-MM-DD for tax rate lookup
            if isinstance(checkin_date, str):
                # Try different date formats
                checkin_date_iso = None
                date_formats = ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%d/%m/%Y']
                
                for fmt in date_formats:
                    try:
                        checkin_dt = datetime.strptime(checkin_date, fmt)
                        checkin_date_iso = checkin_dt.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
                
                if not checkin_date_iso:
                    # Fallback to current date if parsing fails
                    checkin_date_iso = datetime.now().strftime('%Y-%m-%d')
            else:
                checkin_date_iso = checkin_date.strftime('%Y-%m-%d')
            
            # Get tax rates based on check-in date
            tax_rates = self.get_tax_rates(checkin_date_iso)
            
            # Step 1: Calculate VAT on gross amount
            vat_base = 100 + tax_rates['vat_rate']  # e.g., 121 for 21% VAT
            amount_vat = (float(gross_amount) / vat_base) * tax_rates['vat_rate']
            
            # Step 2: Calculate Tourist Tax on VAT-exclusive amount
            vat_exclusive_amount = float(gross_amount) - amount_vat
            tourist_base = 100 + tax_rates['tourist_tax_rate']  # e.g., 106.9 for 6.9% tourist tax
            amount_tourist_tax = (vat_exclusive_amount / tourist_base) * tax_rates['tourist_tax_rate']
            
            # Step 3: Net amount = gross - taxes - channel fee
            amount_nett = float(gross_amount) - amount_tourist_tax - amount_vat - float(channel_fee)
            
            return {
                'amount_vat': round(amount_vat, 2),
                'amount_tourist_tax': round(amount_tourist_tax, 2),
                'amount_nett': round(amount_nett, 2),
                'tax_rates_used': tax_rates,
                'vat_base': vat_base,
                'tourist_base': tourist_base,
                'vat_exclusive_amount': round(vat_exclusive_amount, 2)
            }
            
        except Exception as e:
            print(f"Error in tax calculation: {e}")
            # Return zero amounts if calculation fails
            return {
                'amount_vat': 0.0,
                'amount_tourist_tax': 0.0,
                'amount_nett': float(gross_amount) - float(channel_fee),
                'tax_rates_used': self.get_tax_rates(datetime.now().strftime('%Y-%m-%d')),
                'total_tax_base': 115.0  # Fallback
            }
        """Get VAT and tourist tax rates based on check-in date"""
        try:
            # Parse check-in date
            if isinstance(checkin_date, str):
                checkin_dt = datetime.strptime(checkin_date, '%Y-%m-%d').date()
            else:
                checkin_dt = checkin_date
            
            # 2026 rate changes effective from January 1, 2026
            rate_change_date = date(2026, 1, 1)
            
            if checkin_dt >= rate_change_date:
                # 2026 rates and later
                return {
                    'vat_rate': 21.0,  # Changed from 9% to 21%
                    'vat_base': 121.0,  # Base for VAT calculation (100 + VAT rate)
                    'tourist_tax_rate': 6.9,  # Changed from 6.02% to 6.9%
                    'tourist_tax_base': 106.9,  # Base for tourist tax calculation
                    'price_uplift': 0.054409  # Uplift from commissionable amount to total price
                }
            else:
                # Pre-2026 rates
                return {
                    'vat_rate': 9.0,  # Original 9% VAT
                    'vat_base': 109.0,  # Base for VAT calculation (100 + VAT rate)
                    'tourist_tax_rate': 6.02,  # Original 6.02% tourist tax
                    'tourist_tax_base': 106.02,  # Base for tourist tax calculation
                    'price_uplift': 0.054409  # Uplift from commissionable amount to total price
                }
        except Exception as e:
            print(f"Error parsing check-in date {checkin_date}: {e}")
            # Default to current rates if date parsing fails
            return {
                'vat_rate': 9.0,
                'vat_base': 109.0,
                'tourist_tax_rate': 6.02,
                'tourist_tax_base': 106.02,
                'price_uplift': 0.054409
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
            'booking_payout': [],  # New: Payout CSV files
            'direct': []
        }
        
        try:
            for file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path):
                    # Check for Payout CSV files first (more specific pattern)
                    if 'payout_from' in file.lower() and file.endswith('.csv'):
                        files['booking_payout'].append(file_path)
                    # Regular Airbnb files
                    elif 'reservation' in file.lower() and file.endswith('.csv'):
                        files['airbnb'].append(file_path)
                    # Regular Booking.com files
                    elif ('check-in' in file.lower() or 'booking' in file.lower()) and file.endswith(('.xls', '.xlsx')):
                        files['booking'].append(file_path)
                    # Direct booking files
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
        print(f"Processing file: {file_path} as platform: {platform}")
        
        if platform == 'airbnb':
            return self._process_airbnb(file_path)
        elif platform in ['booking', 'booking.com']:
            return self._process_booking(file_path)
        elif platform in ['booking_payout', 'payout']:
            # Payout files return update records, not transactions
            # This should be handled separately
            return []
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
                
                # Use generic tax calculation function
                tax_calc = self.calculate_str_taxes(gross_amount, checkin_date, amount_channel_fee)
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
                add_info = '|'.join(str(row.get(col, '')) for col in df.columns)
                
                # Detect country from phone number (AirBNB)
                country = detect_country('airbnb', phone=phone, addinfo=add_info)
                
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
                    'amountVat': amount_vat,  # Already rounded in calculate_str_taxes()
                    'amountTouristTax': amount_tourist_tax,  # Already rounded in calculate_str_taxes()
                    'amountNett': amount_nett,  # Already rounded in calculate_str_taxes()
                    'pricePerNight': round(float(price_per_night), 2),
                    'year': year,
                    'q': quarter,
                    'm': month,
                    'daysBeforeReservation': days_before_reservation,
                    'country': country  # NEW: Country detection
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            return []
    
    def _process_booking(self, file_path: str) -> List[Dict]:
        """Process Booking.com Excel/CSV export"""
        print(f"Starting booking.com processing for: {file_path}")
        try:
            # Handle both .xls/.xlsx and .csv files
            if file_path.endswith(('.xls', '.xlsx')):
                print(f"Reading Excel file: {file_path}")
                df = pd.read_excel(file_path)
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
            
            transactions = []
            
            for _, row in df.iterrows():
                # Map Booking.com columns with flexible matching
                checkin_date = row.get('Check-in', row.get('Checkin', row.get('Check in', '')))
                checkout_date = row.get('Check-out', row.get('Checkout', row.get('Check out', '')))
                guest_name = row.get('Guest name(s)', row.get('Guest name', row.get('Guest', '')))
                unit_type = row.get('Unit type', row.get('Property', row.get('Accommodation', '')))
                nights = row.get('Duration (nights)', row.get('Nights', row.get('Duration', 0)))
                price_str = row.get('Price', row.get('Total price', row.get('Amount', '0')))
                booking_id = row.get('Book number', row.get('Booking number', row.get('Reservation', '')))
                status = row.get('Status', 'ok')
                commission_amount_str = row.get('Commission amount', row.get('Commission', ''))
                
                print(f"DEBUG - Processing booking: {booking_id}")
                print(f"  Raw price_str: {price_str}")
                print(f"  Raw commission_str: {commission_amount_str}")
                print(f"  Commission field type: {type(commission_amount_str)}")
                
                # Skip cancelled bookings with no commission (no revenue)
                if status == 'cancelled_by_guest' and (pd.isna(commission_amount_str) or commission_amount_str == '' or commission_amount_str is None):
                    continue
                
                # Extract numeric base price from "126.6314 EUR" format
                try:
                    if isinstance(price_str, str) and 'EUR' in price_str:
                        base_price = float(price_str.replace(' EUR', '').replace(',', '.'))
                    else:
                        base_price = float(price_str) if price_str else 0
                except (ValueError, TypeError):
                    base_price = 0
                
                # Skip records with zero or missing base price
                if base_price == 0:
                    print(f"  SKIPPING: Base price is zero")
                    continue
                
                # Extract numeric commission amount from "15.195768 EUR" format
                try:
                    # Check if commission is NaN or empty
                    if pd.isna(commission_amount_str) or commission_amount_str == '' or commission_amount_str is None:
                        commission_amount = 0
                        print(f"  WARNING: No commission data, using 0")
                    elif isinstance(commission_amount_str, str) and 'EUR' in commission_amount_str:
                        commission_amount = float(commission_amount_str.replace(' EUR', '').replace(',', '.'))
                    else:
                        commission_amount = float(commission_amount_str) if commission_amount_str else 0
                except (ValueError, TypeError):
                    commission_amount = 0
                    print(f"  WARNING: Could not parse commission, using 0")
                
                print(f"  Parsed base_price: {base_price}")
                print(f"  Parsed commission_amount: {commission_amount}")
                
                # Get tax rates based on check-in date
                tax_rates = self.get_tax_rates(checkin_date)
                
                # Calculate gross amount using Booking.com algorithm
                # amountGross = (basePrice + commissionAmount) × 1.047826
                uplift_factor = 1.047826
                amount_gross = round((base_price + commission_amount) * uplift_factor, 2)
                
                print(f"  Calculated amount_gross: {amount_gross}")
                print(f"  Formula: ({base_price} + {commission_amount}) × {uplift_factor} = {amount_gross}")
                
                # Calculate channel fee
                # amountChannelFee = amountGross - basePrice
                amount_channel_fee = round(amount_gross - base_price, 2)
                
                price = amount_gross  # Use calculated gross amount
                
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
                
                # Use generic tax calculation function with the calculated gross amount
                tax_calc = self.calculate_str_taxes(price, checkin_date, amount_channel_fee)
                amount_vat = tax_calc['amount_vat']
                amount_tourist_tax = tax_calc['amount_tourist_tax']
                amount_nett = tax_calc['amount_nett']
                
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
                
                # Detect country from addInfo (Booking.com)
                country = detect_country('booking.com', phone='', addinfo=add_info)
                
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
                    'amountVat': amount_vat,  # Already rounded in calculate_str_taxes()
                    'amountTouristTax': amount_tourist_tax,  # Already rounded in calculate_str_taxes()
                    'amountNett': amount_nett,  # Already rounded in calculate_str_taxes()
                    'pricePerNight': round(float(price_per_night), 2),
                    'year': year,
                    'q': quarter,
                    'm': month,
                    'daysBeforeReservation': days_before_reservation,
                    'country': country  # NEW: Country detection
                }
                transactions.append(transaction)
            
            print(f"Booking.com processing completed: {len(transactions)} transactions")
            return transactions
        except Exception as e:
            print(f"Error processing booking.com file: {str(e)}")
            import traceback
            traceback.print_exc()
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
                
                # Use generic tax calculation function
                tax_calc = self.calculate_str_taxes(gross_amount, checkin_date, channel_fee)
                amount_vat = tax_calc['amount_vat']
                amount_tourist_tax = tax_calc['amount_tourist_tax']
                amount_nett = tax_calc['amount_nett']
                
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
                
                # Detect country (direct bookings don't have phone or country data)
                country = detect_country(channel, phone='', addinfo=add_info)
                
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
                    'amountVat': amount_vat,  # Already rounded in calculate_str_taxes()
                    'amountTouristTax': amount_tourist_tax,  # Already rounded in calculate_str_taxes()
                    'amountNett': amount_nett,  # Already rounded in calculate_str_taxes()
                    'pricePerNight': round(float(price_per_night), 2),
                    'year': year,
                    'q': quarter,
                    'm': month,
                    'daysBeforeReservation': days_before_reservation,
                    'country': country  # NEW: Country detection
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            return []
    
    def _process_booking_payout(self, file_path: str) -> Dict:
        """
        Process Booking.com Payout CSV file to update financial figures
        
        This file is available monthly after month closure and contains the final,
        accurate financial figures from Booking.com's settlement.
        
        Args:
            file_path: Path to the Payout CSV file (format: Payout_from_*.csv)
            
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
            'updated': [],
            'not_found': [],
            'errors': [],
            'summary': {
                'total_rows': 0,
                'reservation_rows': 0,
                'updated_count': 0,
                'not_found_count': 0,
                'error_count': 0
            }
        }
        
        try:
            # Read CSV file and strip whitespace from column names
            df = pd.read_csv(file_path)
            df.columns = df.columns.str.strip()  # Remove leading/trailing spaces from column names
            
            results['summary']['total_rows'] = len(df)
            
            print(f"Payout CSV loaded: {len(df)} rows")
            print(f"Columns: {list(df.columns)}")
            
            # Filter only Reservation rows (not Payout summary rows)
            reservation_rows = df[df['Type/Transaction type'].str.strip() == 'Reservation']
            results['summary']['reservation_rows'] = len(reservation_rows)
            
            print(f"Found {len(reservation_rows)} reservation rows to process")
            
            updates = []
            
            for _, row in reservation_rows.iterrows():
                try:
                    # Extract reservation code (Reference number)
                    # Handle both string and numeric reservation codes
                    reservation_code_raw = row.get('Reference number', '')
                    if pd.isna(reservation_code_raw) or reservation_code_raw == '-':
                        continue
                    
                    # Convert to string and remove decimal point if it's a float
                    reservation_code = str(reservation_code_raw).strip()
                    if '.' in reservation_code and reservation_code.replace('.', '').replace('0', '', 1).isdigit():
                        # Remove trailing .0 from floats like 1234567890.0
                        reservation_code = reservation_code.split('.')[0]
                    
                    if not reservation_code or reservation_code == '-':
                        continue
                    
                    # Extract financial data from CSV
                    checkin_date = str(row.get('Check-in date', '')).strip()
                    checkout_date = str(row.get('Check-out date', '')).strip()
                    nights = int(row.get('Room nights', 0)) if pd.notna(row.get('Room nights')) else 0
                    
                    # Gross amount (actual from BDC)
                    gross_amount_str = str(row.get('Gross amount', '0')).strip()
                    gross_amount = float(gross_amount_str) if gross_amount_str and gross_amount_str != '-' else 0.0
                    
                    # Commission (negative value in CSV)
                    commission_str = str(row.get('Commission', '0')).strip()
                    commission = float(commission_str) if commission_str and commission_str != '-' else 0.0
                    
                    # Payments Service Fee (negative value in CSV)
                    service_fee_str = str(row.get('Payments Service Fee', '0')).strip()
                    service_fee = float(service_fee_str) if service_fee_str and service_fee_str != '-' else 0.0
                    
                    # Skip if no gross amount
                    if gross_amount == 0:
                        continue
                    
                    # Calculate channel fee: abs(Commission) + abs(Payments Service Fee)
                    amount_channel_fee = abs(commission) + abs(service_fee)
                    
                    # Get tax rates based on check-in date
                    tax_rates = self.get_tax_rates(checkin_date)
                    
                    # Calculate VAT on gross amount (accommodation VAT, not BDC service VAT)
                    # 9% until 2026-01-01, then 21%
                    vat_base = tax_rates['vat_base']  # 109 or 121
                    vat_rate = tax_rates['vat_rate']  # 9 or 21
                    amount_vat = round((gross_amount / vat_base) * vat_rate, 2)
                    
                    # Calculate tourist tax using existing algorithm (not in CSV)
                    vat_exclusive_amount = gross_amount - amount_vat
                    
                    # Calculate tourist tax
                    tourist_base = tax_rates['tourist_tax_base']
                    tourist_rate = tax_rates['tourist_tax_rate']
                    amount_tourist_tax = round((vat_exclusive_amount / tourist_base) * tourist_rate, 2)
                    
                    # Calculate net amount
                    amount_nett = gross_amount - amount_vat - amount_tourist_tax - amount_channel_fee
                    
                    # Calculate price per night
                    price_per_night = round(amount_nett / nights, 2) if nights > 0 else 0.0
                    
                    # Create update record
                    update_record = {
                        'reservationCode': reservation_code,
                        'amountGross': round(gross_amount, 2),
                        'amountChannelFee': round(amount_channel_fee, 2),
                        'amountVat': round(amount_vat, 2),
                        'amountTouristTax': round(amount_tourist_tax, 2),
                        'amountNett': round(amount_nett, 2),
                        'pricePerNight': round(price_per_night, 2),
                        'checkinDate': checkin_date,
                        'checkoutDate': checkout_date,
                        'nights': nights,
                        'sourceFile': f"PAYOUT_{datetime.now().strftime('%Y-%m-%d')}_{os.path.basename(file_path)}"
                    }
                    
                    updates.append(update_record)
                    results['updated'].append(reservation_code)
                    
                    print(f"Prepared update for reservation {reservation_code}: "
                          f"Gross={gross_amount}, ChannelFee={amount_channel_fee}, "
                          f"VAT={amount_vat}, TouristTax={amount_tourist_tax}, Net={amount_nett}")
                    
                except Exception as e:
                    error_msg = f"Error processing row for reservation {reservation_code}: {str(e)}"
                    print(error_msg)
                    results['errors'].append(error_msg)
                    results['summary']['error_count'] += 1
            
            # Update summary
            results['summary']['updated_count'] = len(updates)
            results['updates'] = updates
            
            print(f"\nPayout processing completed:")
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
            results['errors'].append(error_msg)
            results['summary']['error_count'] += 1
            return results
    
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