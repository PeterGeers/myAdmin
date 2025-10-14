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
        
        # Property mappings from config
        self.property_mappings = {
            'green': 'Green Apartment',
            'child': 'Garden House', 
            'red': 'Red Apartment'
        }
    
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
                
        return self._merge_and_calculate(all_bookings)
    
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
                # Airbnb standard columns
                transaction = {
                    'date': self._parse_date(row.get('Date', '')),
                    'guest_name': row.get('Guest', ''),
                    'listing': row.get('Listing', ''),
                    'nights': row.get('Nights', 0),
                    'gross_earnings': float(row.get('Gross Earnings', 0)),
                    'host_fee': float(row.get('Host Fee', 0)),
                    'cleaning_fee': float(row.get('Cleaning Fee', 0)),
                    'net_earnings': float(row.get('Net Earnings', 0)),
                    'platform': 'airbnb',
                    'booking_id': row.get('Confirmation Code', ''),
                    'status': row.get('Status', 'completed')
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            print(f"Error processing Airbnb data: {e}")
            return []
    
    def _process_booking(self, file_path: str) -> List[Dict]:
        """Process Booking.com CSV export"""
        try:
            df = pd.read_csv(file_path)
            transactions = []
            
            for _, row in df.iterrows():
                # Booking.com standard columns
                transaction = {
                    'date': self._parse_date(row.get('Check-in Date', '')),
                    'guest_name': row.get('Guest Name', ''),
                    'listing': row.get('Property Name', ''),
                    'nights': row.get('Number of Nights', 0),
                    'gross_earnings': float(row.get('Total Price', 0)),
                    'commission': float(row.get('Commission', 0)),
                    'net_earnings': float(row.get('Net Amount', 0)),
                    'platform': 'booking.com',
                    'booking_id': row.get('Booking ID', ''),
                    'status': row.get('Status', 'completed')
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            print(f"Error processing Booking.com data: {e}")
            return []
    
    def _process_direct(self, file_path: str) -> List[Dict]:
        """Process direct bookings CSV"""
        try:
            df = pd.read_csv(file_path)
            transactions = []
            
            for _, row in df.iterrows():
                transaction = {
                    'date': self._parse_date(row.get('checkin_date', '')),
                    'guest_name': row.get('guest_name', ''),
                    'listing': row.get('property', ''),
                    'nights': row.get('nights', 0),
                    'gross_earnings': float(row.get('total_amount', 0)),
                    'cleaning_fee': float(row.get('cleaning_fee', 0)),
                    'net_earnings': float(row.get('net_amount', 0)),
                    'platform': 'direct',
                    'booking_id': row.get('booking_ref', ''),
                    'status': row.get('status', 'completed')
                }
                transactions.append(transaction)
            
            return transactions
        except Exception as e:
            print(f"Error processing direct booking data: {e}")
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
        """Separate bookings by status like R script"""
        realised = [b for b in bookings if b.get('status') in ['realised', 'cancelled']]
        planned = [b for b in bookings if b.get('status') == 'planned']
        
        return {
            'realised': realised,
            'planned': planned
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