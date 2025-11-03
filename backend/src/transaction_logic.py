import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class TransactionLogic:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        
        # Use test database if test_mode is True or TEST_MODE env var is set
        use_test = test_mode or os.getenv('TEST_MODE', 'false').lower() == 'true'
        self.table_name = 'mutaties'  # Use same table name in both databases
        db_name = os.getenv('TEST_DB_NAME', 'testfinance') if use_test else os.getenv('DB_NAME', 'finance')
        
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': db_name
        }
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def get_last_transactions(self, transaction_number):
        """Get last transactions based on TransactionNumber and max date"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # First try to find existing transactions
        query = f"""
            SELECT ID, TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, 
                   Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration
            FROM {self.table_name} 
            WHERE TransactionNumber LIKE %s 
            AND TransactionDate = (SELECT MAX(TransactionDate) FROM {self.table_name} WHERE TransactionNumber LIKE %s)
            ORDER BY Debet DESC
        """
        
        cursor.execute(query, (f"{transaction_number}%", f"{transaction_number}%"))
        results = cursor.fetchall()
        
        # If multiple transactions on same day, group by Ref3 and take first group
        if len(results) > 2:
            ref3_groups = {}
            for row in results:
                ref3 = row.get('Ref3', 'default')
                if ref3 not in ref3_groups:
                    ref3_groups[ref3] = []
                ref3_groups[ref3].append(row)
            
            # Take the first Ref3 group (most recent or first found)
            first_ref3 = list(ref3_groups.keys())[0]
            results = ref3_groups[first_ref3]
            print(f"Multiple transactions found, using Ref3: {first_ref3}")
        
        # If no results, use "Gamma" as fallback
        if not results:
            cursor.execute(query, ("Gamma%", "Gamma%"))
            results = cursor.fetchall()
            
            # Update transaction numbers to current one
            for row in results:
                row['TransactionNumber'] = transaction_number
                row['ReferenceNumber'] = transaction_number
                # Reset amounts to 0 so vendor data will be used
                row['TransactionAmount'] = 0
        
        cursor.close()
        conn.close()
        
        # Only duplicate if exactly 1 transaction (some vendors have single transactions)
        if len(results) == 1:
            # Check if this vendor typically has single transactions
            single_transaction_vendors = ['SomeVendor']  # Add vendors that use single transactions
            
            if transaction_number not in single_transaction_vendors:
                # Duplicate first transaction and modify for credit entry
                credit_transaction = results[0].copy()
                credit_transaction['Debet'] = 2010  # Account 2010 as per R logic
                credit_transaction['Credit'] = results[0]['Debet']
                
                # Set vendor-specific account codes
                if transaction_number.lower() == 'coursera':
                    results[0]['Debet'] = '6200'  # Training/Education expense
                    results[0]['Credit'] = '1600'  # Bank account
                    results[0]['TransactionAmount'] = 0  # Reset to use vendor data
                    credit_transaction['Debet'] = '2010'  # VAT
                    credit_transaction['Credit'] = '6200'  # Training expense
                    credit_transaction['TransactionAmount'] = 0  # Reset to use vendor data
                elif transaction_number.lower() == 'netflix':
                    results[0]['Debet'] = '6400'  # Entertainment expense
                    results[0]['Credit'] = '1600'  # Bank account
                    results[0]['TransactionAmount'] = 0  # Reset to use vendor data
                    credit_transaction['Debet'] = '2010'  # VAT
                    credit_transaction['Credit'] = '6400'  # Entertainment expense
                    credit_transaction['TransactionAmount'] = 0  # Reset to use vendor data
                
                results.append(credit_transaction)
                print(f"Created debet/credit pair for {transaction_number}")
            else:
                print(f"{transaction_number} uses single transactions - no duplication")
        
        return results
    
    def check_file_exists(self, filename, folder_id):
        """Check if file already exists in the folder"""
        # This would integrate with Google Drive API
        # For now, return False (file doesn't exist)
        return False
    
    def generate_unique_filename(self, original_filename, folder_id):
        """Generate unique filename if file exists"""
        if not self.check_file_exists(original_filename, folder_id):
            return original_filename
        
        # Add timestamp to make unique
        name, ext = os.path.splitext(original_filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{name}_{timestamp}{ext}"
    
    def prepare_new_transactions(self, template_transactions, new_data):
        """Prepare new transaction records based on templates (without saving to DB)"""
        new_transactions = []
        vendor_data = new_data.get('vendor_data', {})
        
        for i, template in enumerate(template_transactions):
            # Use vendor data for amounts and descriptions if available
            if vendor_data:
                if i == 0:  # First transaction - main amount
                    amount = vendor_data.get('total_amount', template.get('TransactionAmount', 0))
                    description = vendor_data.get('description', new_data.get('description', template.get('TransactionDescription', '')))
                elif i == 1:  # Second transaction - VAT
                    amount = vendor_data.get('vat_amount', template.get('TransactionAmount', 0))
                    description = vendor_data.get('description', '') + ' BTW'
                else:
                    amount = template.get('TransactionAmount', 0)
                    description = new_data.get('description', template.get('TransactionDescription', ''))
            else:
                amount = new_data.get('amount', template.get('TransactionAmount', 0))
                description = new_data.get('description', template.get('TransactionDescription', ''))
            
            # Use vendor data date if available
            transaction_date = vendor_data.get('date', datetime.now().strftime('%Y-%m-%d')) if vendor_data else datetime.now().strftime('%Y-%m-%d')
            print(f"Transaction {i}: Using date {transaction_date} from vendor_data: {vendor_data.get('date') if vendor_data else 'None'}", flush=True)
            
            # Set Ref1 and Ref2 based on vendor data
            ref1 = None
            ref2 = None
            
            if vendor_data:
                # For Booking.com, use accommodation name in Ref1 and invoice number in Ref2
                if 'accommodation_name' in vendor_data and vendor_data['accommodation_name']:
                    ref1 = vendor_data['accommodation_name']
                elif 'accommodation_number' in vendor_data and vendor_data['accommodation_number']:
                    ref1 = f"Accommodation {vendor_data['accommodation_number']}"
                
                # Only set ref2 for Booking.com, not Amazon
                if 'invoice_number' in vendor_data and vendor_data['invoice_number'] and new_data['folder_name'].lower() != 'amazon':
                    ref2 = vendor_data['invoice_number']
                
                # Update description to include commission type if available
                if 'commission_type' in vendor_data and vendor_data['commission_type']:
                    if i == 0:  # First transaction
                        description = f"{ref1} {ref2} {vendor_data['commission_type']} {transaction_date}"
                    elif i == 1:  # Second transaction (VAT)
                        description = f"{ref1} {ref2} {vendor_data['commission_type']} {transaction_date} BTW"
            
            # Create new transaction based on template
            new_transaction = {
                'ID': f'NEW_{i+1}',  # Temporary ID
                'TransactionNumber': new_data['folder_name'],
                'TransactionDate': transaction_date,
                'TransactionDescription': description,
                'TransactionAmount': amount,
                'Debet': template.get('Debet'),
                'Credit': template.get('Credit'),
                'ReferenceNumber': new_data['folder_name'],  # Base transaction name
                'Ref1': ref1,
                'Ref2': ref2,
                'Ref3': new_data['drive_url'],
                'Ref4': new_data['filename'],
                'Administration': template.get('Administration', 'GoodwinSolutions')
            }
            new_transactions.append(new_transaction)
        
        return new_transactions
    
    def save_approved_transactions(self, transactions):
        """Save approved transactions to database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        saved_transactions = []
        
        for transaction in transactions:
            # Skip transactions with zero amount
            if float(transaction.get('TransactionAmount', 0)) == 0:
                print(f"Skipping transaction with zero amount: {transaction.get('TransactionDescription', 'Unknown')}", flush=True)
                continue
            insert_query = f"""
                INSERT INTO {self.table_name} 
                (TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, 
                 Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            cursor.execute(insert_query, (
                transaction['TransactionNumber'],
                transaction['TransactionDate'],
                transaction['TransactionDescription'],
                transaction['TransactionAmount'],
                transaction['Debet'],
                transaction['Credit'],
                transaction['ReferenceNumber'],
                transaction['Ref1'],
                transaction['Ref2'],
                transaction['Ref3'],
                transaction['Ref4'],
                transaction['Administration']
            ))
            
            transaction['ID'] = cursor.lastrowid
            saved_transactions.append(transaction)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return saved_transactions