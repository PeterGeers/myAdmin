from datetime import datetime
import os
from dotenv import load_dotenv
from database import DatabaseManager
from db_exceptions import ClosedPeriodError

load_dotenv()

class TransactionLogic:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.table_name = 'mutaties'  # Use same table name in both databases
        self.db = DatabaseManager(test_mode=test_mode)
    
    def get_connection(self):
        return self.db.get_connection()
    
    def get_last_transactions(self, transaction_number, administration=None):
        """Get last transactions based on TransactionNumber and max date
        
        Args:
            transaction_number: The transaction number to search for
            administration: The tenant/administration to filter by (optional)
        """
        # Build query with optional administration filter
        admin_filter = "AND administration = %s" if administration else ""
        
        # First try to find existing transactions
        query = f"""
            SELECT ID, TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, 
                   Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration
            FROM {self.table_name} 
            WHERE TransactionNumber LIKE %s 
            {admin_filter}
            AND TransactionDate = (
                SELECT MAX(TransactionDate) 
                FROM {self.table_name} 
                WHERE TransactionNumber LIKE %s 
                {admin_filter}
            )
            ORDER BY Debet DESC
        """
        
        # Build params based on whether administration is provided
        if administration:
            params = (f"{transaction_number}%", administration, f"{transaction_number}%", administration)
        else:
            params = (f"{transaction_number}%", f"{transaction_number}%")
        
        with self.db.get_cursor() as (cursor, conn):
            cursor.execute(query, params)
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
        
        # If no results, return error — no silent fallback
        if not results:
            return {'error': True, 'message': f'No booking history found for vendor "{transaction_number}". Manual account selection required.', 'results': []}
        
        # Only duplicate if exactly 1 transaction (some vendors have single transactions)
        if len(results) == 1:
            # Check if this vendor typically has single transactions
            single_transaction_vendors = ['SomeVendor']  # Add vendors that use single transactions
            
            if transaction_number not in single_transaction_vendors:
                # Resolve VAT account from TaxRateService instead of hardcoding '2010'
                from services.tax_rate_service import TaxRateService
                tax_svc = TaxRateService(self.db)
                admin = administration or results[0].get('Administration', '')
                rate_info = tax_svc.get_tax_rate(admin, 'btw', 'high', datetime.now().date())
                vat_account = rate_info['ledger_account'] if rate_info else '2010'  # graceful fallback
                
                # Duplicate first transaction and modify for credit entry
                credit_transaction = results[0].copy()
                credit_transaction['Debet'] = vat_account
                credit_transaction['Credit'] = results[0]['Debet']
                
                # No vendor-specific overrides — DB accounts are the correct template
                
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
                'Administration': new_data.get('administration', template.get('Administration', 'GoodwinSolutions'))
            }
            new_transactions.append(new_transaction)
        
        return new_transactions
    
    def save_approved_transactions(self, transactions):
        """Save approved transactions to database.
        
        Zero-amount transactions are silently skipped (e.g. VAT line when VAT = 0).
        Before saving, checks that no non-zero-amount transaction targets a closed
        fiscal year.  If any do, raises ``ClosedPeriodError`` and no inserts occur.
        Returns only the transactions that were actually saved.
        """
        # --- Closed-period guard (before any DB writes) ---
        # Collect distinct (year, administration) pairs from non-zero-amount txns
        year_admin_pairs = {}  # admin -> set of years
        for txn in transactions:
            if float(txn.get('TransactionAmount', 0)) == 0:
                continue
            admin = txn.get('Administration') or txn.get('administration')
            if not admin:
                continue
            txn_date = str(txn.get('TransactionDate', ''))
            try:
                year = int(txn_date[:4])
            except (ValueError, IndexError):
                continue
            year_admin_pairs.setdefault(admin, set()).add(year)

        # Query year_closure_status for each administration
        offending = []
        for admin, years in year_admin_pairs.items():
            if not years:
                continue
            placeholders = ','.join(['%s'] * len(years))
            query = (
                f"SELECT year FROM year_closure_status "
                f"WHERE administration = %s AND year IN ({placeholders})"
            )
            params = [admin] + sorted(years)
            rows = self.db.execute_query(query, params)
            closed_years = {row['year'] for row in rows} if rows else set()
            if closed_years:
                for txn in transactions:
                    if float(txn.get('TransactionAmount', 0)) == 0:
                        continue
                    txn_admin = txn.get('Administration') or txn.get('administration')
                    if txn_admin != admin:
                        continue
                    txn_date = str(txn.get('TransactionDate', ''))
                    try:
                        txn_year = int(txn_date[:4])
                    except (ValueError, IndexError):
                        continue
                    if txn_year in closed_years:
                        offending.append({'transaction': txn, 'year': txn_year})

        if offending:
            raise ClosedPeriodError(offending)

        # --- Existing save logic ---
        saved_transactions = []
        skipped_count = 0
        
        with self.db.transaction() as (cursor, conn):
            for transaction in transactions:
                # Skip transactions with zero amount (e.g. zero-VAT invoice lines)
                amount = float(transaction.get('TransactionAmount', 0))
                if amount == 0:
                    print(f"Skipping zero-amount transaction: {transaction.get('TransactionDescription', 'Unknown')} "
                          f"(Debet: {transaction.get('Debet')}, Credit: {transaction.get('Credit')})", flush=True)
                    skipped_count += 1
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
        
        if skipped_count > 0:
            print(f"Skipped {skipped_count} zero-amount transaction(s)", flush=True)
        
        return saved_transactions