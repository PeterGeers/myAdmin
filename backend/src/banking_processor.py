import pandas as pd
import glob
import os
import re
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer
import json
import unicodedata

class BankingProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.pattern_analyzer = PatternAnalyzer(test_mode=test_mode)
        self.download_folder = os.path.expanduser("~/Downloads")  # Default download folder
    
    def normalize_text(self, text):
        """Normalize text to NFD form for consistent duplicate detection"""
        if not text:
            return ''
        return unicodedata.normalize('NFD', str(text))
    
    def get_csv_files(self, folder_path=None):
        """Get all CSV files from specified folder"""
        if not folder_path:
            folder_path = self.download_folder
        
        # Look for Rabobank CSV files (pattern: CSV_[O|A])
        rabo_pattern = os.path.join(folder_path, "CSV_[OA]*.csv")
        rabo_files = glob.glob(rabo_pattern)
        
        # Look for other bank files
        other_pattern = os.path.join(folder_path, "*.csv")
        all_files = glob.glob(other_pattern)
        
        return {
            'rabo_files': rabo_files,
            'other_files': [f for f in all_files if f not in rabo_files]
        }
    
    def read_rabo_csv(self, file_path):
        """Read Rabobank CSV file and extract necessary columns"""
        try:
            df = pd.read_csv(file_path, encoding='latin1', dtype=str)
            
            # Map Rabobank columns to standard format
            standard_columns = {
                'TransactionNumber': f'Rabo {datetime.now().strftime("%Y-%m-%d")}',
                'TransactionDate': df.iloc[:, 4] if len(df.columns) > 4 else '',  # Date column
                'TransactionDescription': '',  # Will be built from multiple columns
                'TransactionAmount': df.iloc[:, 6] if len(df.columns) > 6 else '',  # Amount column
                'Debet': '',
                'Credit': '',
                'ReferenceNumber': f'Rabo {datetime.now().strftime("%Y-%m-%d")}',
                'Ref1': df.iloc[:, 0] if len(df.columns) > 0 else '',  # Account number
                'Ref2': df.iloc[:, 3] if len(df.columns) > 3 else '',  # Transaction reference
                'Ref3': '',
                'Ref4': file_path,
                'Administration': 'GoodwinSolutions'
            }
            
            # Build transaction description from available columns
            desc_fields = []
            if len(df.columns) > 8:  # Naam tegenpartij
                desc_fields.append(df.iloc[:, 8].fillna(''))
            if len(df.columns) > 19:  # Omschrijving
                desc_fields.append(df.iloc[:, 19].fillna(''))
            
            # Combine description fields
            if desc_fields:
                standard_columns['TransactionDescription'] = desc_fields[0].astype(str) + ' ' + desc_fields[1].astype(str) if len(desc_fields) > 1 else desc_fields[0].astype(str)
            
            # Process amounts and debit/credit
            if 'TransactionAmount' in standard_columns and not standard_columns['TransactionAmount'].empty:
                amounts = standard_columns['TransactionAmount'].astype(str)
                signs = amounts.str[0]  # First character is +/-
                amounts_clean = amounts.str[1:].str.replace(',', '.').astype(float)
                
                # Determine debit/credit based on sign
                account = standard_columns['Ref1']
                standard_columns['Debet'] = account.where(signs == '+', '')
                standard_columns['Credit'] = account.where(signs == '-', '')
                standard_columns['TransactionAmount'] = amounts_clean
            
            return pd.DataFrame(standard_columns)
            
        except Exception as e:
            print(f"Error reading Rabo CSV {file_path}: {e}")
            return pd.DataFrame()
    
    def read_generic_csv(self, file_path):
        """Read generic CSV file and map to standard format"""
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            
            # Try to auto-detect columns based on common names
            date_col = self.find_column(df, ['date', 'datum', 'transaction_date'])
            amount_col = self.find_column(df, ['amount', 'bedrag', 'transaction_amount'])
            desc_col = self.find_column(df, ['description', 'omschrijving', 'memo'])
            
            standard_data = {
                'TransactionNumber': f'Import {datetime.now().strftime("%Y-%m-%d")}',
                'TransactionDate': df[date_col] if date_col else '',
                'TransactionDescription': df[desc_col] if desc_col else '',
                'TransactionAmount': df[amount_col] if amount_col else 0,
                'Debet': '',
                'Credit': '',
                'ReferenceNumber': f'Import {datetime.now().strftime("%Y-%m-%d")}',
                'Ref1': '',
                'Ref2': '',
                'Ref3': '',
                'Ref4': file_path,
                'Administration': 'GoodwinSolutions'
            }
            
            return pd.DataFrame(standard_data)
            
        except Exception as e:
            print(f"Error reading generic CSV {file_path}: {e}")
            return pd.DataFrame()
    
    def find_column(self, df, possible_names):
        """Find column by possible names (case insensitive)"""
        for col in df.columns:
            if col.lower() in [name.lower() for name in possible_names]:
                return col
        return None
    
    def process_csv_files(self, file_paths):
        """Process multiple CSV files and combine into single dataset"""
        combined_data = pd.DataFrame()
        
        for file_path in file_paths:
            print(f"Processing: {file_path}")
            
            # Determine file type and process accordingly
            if 'CSV_' in os.path.basename(file_path):
                df = self.read_rabo_csv(file_path)
            else:
                df = self.read_generic_csv(file_path)
            
            if not df.empty:
                if combined_data.empty:
                    combined_data = df
                else:
                    combined_data = pd.concat([combined_data, df], ignore_index=True)
        
        return combined_data
    
    def prepare_for_review(self, df):
        """Prepare data for frontend review"""
        # Convert to records for JSON serialization
        records = df.to_dict('records')
        
        # Add row IDs for frontend tracking
        for i, record in enumerate(records):
            record['row_id'] = i
            # Ensure all values are JSON serializable
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = ''
                elif isinstance(value, (pd.Timestamp, datetime)):
                    record[key] = value.strftime('%Y-%m-%d')
        
        return records
    
    def save_approved_transactions(self, transactions):
        """Save approved transactions to database with duplicate detection"""
        table_name = 'mutaties'
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        saved_count = 0
        for transaction in transactions:
            try:
                if 'row_id' in transaction:
                    del transaction['row_id']
                
                if float(transaction.get('TransactionAmount', 0)) == 0:
                    continue
                
                # Check for duplicate using normalized text
                desc_normalized = self.normalize_text(transaction.get('TransactionDescription', ''))
                cursor.execute(f"""
                    SELECT ID FROM {table_name}
                    WHERE TransactionAmount = %s
                    AND TransactionDate = %s
                    AND Administration = %s
                    LIMIT 1
                """, (
                    transaction.get('TransactionAmount'),
                    transaction.get('TransactionDate'),
                    transaction.get('Administration')
                ))
                
                existing = cursor.fetchall()
                if existing:
                    # Check if any match after normalization
                    for row in existing:
                        cursor.execute(f"SELECT TransactionDescription FROM {table_name} WHERE ID = %s", (row['ID'],))
                        existing_desc = cursor.fetchone()['TransactionDescription']
                        if self.normalize_text(existing_desc) == desc_normalized:
                            print(f"Skipping duplicate: {transaction.get('TransactionDescription')}")
                            continue
                
                self.db.insert_transaction(transaction, table_name)
                saved_count += 1
                
            except Exception as e:
                print(f"Error saving transaction: {e}")
        
        cursor.close()
        conn.close()
        return saved_count
    
    def check_banking_accounts(self, end_date=None):
        """Check banking account balances based on internal calculation vs last transaction"""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get bank accounts to validate
        cursor.execute("SELECT * FROM lookupbankaccounts_r")
        accounts = cursor.fetchall()
        
        if not accounts:
            return []
        
        # Get administrations and account patterns
        administrations = list(set([acc['Administration'] for acc in accounts]))
        account_codes = list(set([acc['Account'] for acc in accounts]))
        
        # Build WHERE clauses
        admin_pattern = '|'.join(administrations)
        account_pattern = '|'.join(account_codes)
        
        # Get calculated balances from vw_mutaties with account names
        if end_date:
            cursor.execute("""
                SELECT Reknum, Administration, 
                       ROUND(SUM(Amount), 2) as calculated_balance,
                       MAX(AccountName) as account_name
                FROM vw_mutaties 
                WHERE Administration REGEXP %s 
                AND Reknum REGEXP %s
                AND TransactionDate <= %s
                GROUP BY Reknum, Administration
            """, (admin_pattern, account_pattern, end_date))
        else:
            cursor.execute("""
                SELECT Reknum, Administration, 
                       ROUND(SUM(Amount), 2) as calculated_balance,
                       MAX(AccountName) as account_name
                FROM vw_mutaties 
                WHERE Administration REGEXP %s 
                AND Reknum REGEXP %s
                GROUP BY Reknum, Administration
            """, (admin_pattern, account_pattern))
        
        balances = cursor.fetchall()
        
        # For each balance, find the last transaction description
        for balance in balances:
            # Get all transactions for the last transaction date (up to end_date if specified)
            if end_date:
                cursor.execute("""
                    SELECT TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit, Ref2, Ref3
                    FROM mutaties 
                    WHERE Administration = %s 
                    AND (Debet = %s OR Credit = %s)
                    AND TransactionDate <= %s
                    AND TransactionDate = (
                        SELECT MAX(TransactionDate) 
                        FROM mutaties 
                        WHERE Administration = %s 
                        AND (Debet = %s OR Credit = %s)
                        AND TransactionDate <= %s
                    )
                    ORDER BY Ref2 DESC
                """, (
                    balance['Administration'], balance['Reknum'], balance['Reknum'], end_date,
                    balance['Administration'], balance['Reknum'], balance['Reknum'], end_date
                ))
            else:
                cursor.execute("""
                    SELECT TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit, Ref2, Ref3
                    FROM mutaties 
                    WHERE Administration = %s 
                    AND (Debet = %s OR Credit = %s)
                    AND TransactionDate = (
                        SELECT MAX(TransactionDate) 
                        FROM mutaties 
                        WHERE Administration = %s 
                        AND (Debet = %s OR Credit = %s)
                    )
                    ORDER BY Ref2 DESC
                """, (
                    balance['Administration'], balance['Reknum'], balance['Reknum'],
                    balance['Administration'], balance['Reknum'], balance['Reknum']
                ))
            
            last_transactions = cursor.fetchall()
            
            if last_transactions:
                balance['last_transaction_date'] = last_transactions[0]['TransactionDate']
                balance['last_transaction_description'] = last_transactions[0]['TransactionDescription']
                balance['last_transaction_amount'] = last_transactions[0]['TransactionAmount']
                # Ensure Ref3 is included in each transaction
                for tx in last_transactions:
                    if 'Ref3' not in tx:
                        tx['Ref3'] = ''
                balance['last_transactions'] = last_transactions
            else:
                balance['last_transaction_date'] = None
                balance['last_transaction_description'] = 'No transactions found'
                balance['last_transaction_amount'] = 0
                balance['last_transactions'] = []
        
        cursor.close()
        conn.close()
        
        return balances
    
    def check_sequence_numbers(self, account_code=None, administration=None, start_date='2025-01-01'):
        """Check if Ref2 sequence numbers are consecutive for specific accounts since start_date"""
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # If account_code and administration provided, get IBAN from lookup
        if account_code and administration:
            cursor.execute("""
                SELECT rekeningNummer FROM lookupbankaccounts_r 
                WHERE Account = %s AND Administration = %s
            """, (account_code, administration))
            lookup_result = cursor.fetchone()
            if not lookup_result:
                cursor.close()
                conn.close()
                return {'success': False, 'message': f'No IBAN found for account {account_code} in {administration}'}
            iban = lookup_result['rekeningNummer']
        else:
            iban = 'NL80RABO0107936917'  # Default
        
        # Get all transactions for the IBAN since start_date, ordered by Ref2
        cursor.execute("""
            SELECT TransactionDate, TransactionDescription, Ref2, TransactionAmount
            FROM mutaties 
            WHERE Ref1 = %s 
            AND TransactionDate >= %s
            AND Ref2 IS NOT NULL 
            AND Ref2 != ''
            ORDER BY CAST(Ref2 AS UNSIGNED)
        """, (iban, start_date))
        
        transactions = cursor.fetchall()
        
        if not transactions:
            cursor.close()
            conn.close()
            return {'success': False, 'message': 'No transactions found'}
        
        # Check for sequence gaps
        sequence_issues = []
        expected_next = None
        
        for i, tx in enumerate(transactions):
            try:
                current_seq = int(tx['Ref2'])
                
                if i == 0:
                    expected_next = current_seq + 1
                else:
                    if current_seq != expected_next:
                        sequence_issues.append({
                            'expected': expected_next,
                            'found': current_seq,
                            'gap': current_seq - expected_next,
                            'date': tx['TransactionDate'],
                            'description': tx['TransactionDescription'],
                            'amount': tx['TransactionAmount']
                        })
                    expected_next = current_seq + 1
                    
            except ValueError:
                sequence_issues.append({
                    'error': f"Invalid sequence number: {tx['Ref2']}",
                    'date': tx['TransactionDate'],
                    'description': tx['TransactionDescription']
                })
        
        cursor.close()
        conn.close()
        
        # Handle first and last sequence safely
        first_sequence = None
        last_sequence = None
        if transactions:
            try:
                first_sequence = int(transactions[0]['Ref2'])
            except ValueError:
                pass
            try:
                last_sequence = int(transactions[-1]['Ref2'])
            except ValueError:
                pass
        
        return {
            'success': True,
            'iban': iban,
            'account_code': account_code,
            'administration': administration,
            'start_date': start_date,
            'total_transactions': len(transactions),
            'first_sequence': first_sequence,
            'last_sequence': last_sequence,
            'sequence_issues': sequence_issues,
            'has_gaps': len(sequence_issues) > 0
        }
    
    def analyze_patterns_for_administration(self, administration='GoodwinSolutions',
                                          reference_number=None, debet_account=None, 
                                          credit_account=None):
        """
        Analyze patterns for an administration using the enhanced pattern analyzer
        
        This method implements:
        - REQ-PAT-001: Analyze transactions from the last 2 years for pattern discovery
        - REQ-PAT-002: Filter patterns by Administration, ReferenceNumber, Debet/Credit values, and Date
        
        Args:
            administration: Administration to analyze
            reference_number: Optional filter by specific reference number
            debet_account: Optional filter by specific debet account
            credit_account: Optional filter by specific credit account
        """
        try:
            filter_desc = f"for {administration}"
            if reference_number:
                filter_desc += f" (ReferenceNumber: {reference_number})"
            if debet_account:
                filter_desc += f" (Debet: {debet_account})"
            if credit_account:
                filter_desc += f" (Credit: {credit_account})"
                
            print(f"🔍 Starting enhanced pattern analysis {filter_desc}...")
            
            # Use the enhanced pattern analyzer with filtering (REQ-PAT-002)
            patterns = self.pattern_analyzer.analyze_historical_patterns(
                administration, reference_number, debet_account, credit_account
            )
            
            print(f"✅ Pattern analysis complete:")
            print(f"   - Processed {patterns['total_transactions']} transactions")
            print(f"   - Discovered {patterns['patterns_discovered']} patterns")
            print(f"   - Date range: {patterns['date_range']['from']} to {patterns['date_range']['to']}")
            
            return patterns
            
        except Exception as e:
            print(f"❌ Pattern analysis failed: {e}")
            raise e
    
    def apply_enhanced_patterns(self, transactions, administration='GoodwinSolutions'):
        """
        Apply enhanced pattern matching to predict missing values
        
        This method implements:
        - REQ-PAT-003: Create pattern matching based on known variables
        - REQ-PAT-004: Implement bank account lookup logic
        """
        try:
            print(f"🔧 Applying enhanced patterns to {len(transactions)} transactions...")
            
            # Convert to list of dicts if it's a DataFrame
            if hasattr(transactions, 'to_dict'):
                transactions = transactions.to_dict('records')
            
            # Apply patterns using the enhanced analyzer
            updated_transactions, results = self.pattern_analyzer.apply_patterns_to_transactions(
                transactions, administration
            )
            
            print(f"✅ Enhanced pattern application complete:")
            print(f"   - Debet predictions: {results['predictions_made']['debet']}")
            print(f"   - Credit predictions: {results['predictions_made']['credit']}")
            print(f"   - Reference predictions: {results['predictions_made']['reference']}")
            print(f"   - Average confidence: {results['average_confidence']:.2f}")
            
            return updated_transactions, results
            
        except Exception as e:
            print(f"❌ Enhanced pattern application failed: {e}")
            raise e
    
    def get_pattern_summary(self, administration='GoodwinSolutions'):
        """Get a summary of discovered patterns for an administration"""
        try:
            return self.pattern_analyzer.get_pattern_summary(administration)
        except Exception as e:
            print(f"❌ Failed to get pattern summary: {e}")
            raise e

# Flask routes for the banking processor
app = Flask(__name__)
CORS(app)

@app.route('/api/banking/scan-files', methods=['GET'])
def scan_files():
    """Scan download folder for CSV files"""
    processor = BankingProcessor()
    folder_path = request.args.get('folder', processor.download_folder)
    
    try:
        files = processor.get_csv_files(folder_path)
        return jsonify({
            'success': True,
            'files': files,
            'folder': folder_path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/process-files', methods=['POST'])
def process_files():
    """Process selected CSV files"""
    data = request.get_json()
    file_paths = data.get('files', [])
    test_mode = data.get('test_mode', True)
    
    processor = BankingProcessor(test_mode=test_mode)
    
    try:
        # Process files
        df = processor.process_csv_files(file_paths)
        
        if df.empty:
            return jsonify({'success': False, 'error': 'No data found in files'}), 400
        
        # Prepare for review
        records = processor.prepare_for_review(df)
        
        return jsonify({
            'success': True,
            'transactions': records,
            'count': len(records),
            'test_mode': test_mode
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/save-transactions', methods=['POST'])
def save_transactions():
    """Save approved transactions to database"""
    data = request.get_json()
    transactions = data.get('transactions', [])
    test_mode = data.get('test_mode', True)
    
    processor = BankingProcessor(test_mode=test_mode)
    
    try:
        saved_count = processor.save_approved_transactions(transactions)
        
        return jsonify({
            'success': True,
            'saved_count': saved_count,
            'table': 'mutaties_test' if test_mode else 'mutaties'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-accounts', methods=['GET'])
def check_banking_accounts():
    """Check banking account balances"""
    test_mode = request.args.get('test_mode', 'false').lower() == 'true'
    processor = BankingProcessor(test_mode=test_mode)
    
    try:
        balances = processor.check_banking_accounts()
        
        return jsonify({
            'success': True,
            'balances': balances,
            'count': len(balances)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-sequence', methods=['GET'])
def check_sequence_numbers():
    """Check sequence numbers for IBAN"""
    test_mode = request.args.get('test_mode', 'false').lower() == 'true'
    iban = request.args.get('iban', 'NL80RABO0107936917')
    start_date = request.args.get('start_date', '2025-01-01')
    
    processor = BankingProcessor(test_mode=test_mode)
    
    try:
        result = processor.check_sequence_numbers(iban, start_date)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/analyze-patterns', methods=['POST'])
def analyze_patterns():
    """
    Analyze historical patterns for an administration
    Implements REQ-PAT-002: Filter patterns by Administration, ReferenceNumber, Debet/Credit values, and Date
    - Administration: Filter by administration
    - Date: Filter by last 2 years
    - ReferenceNumber: Use historical reference numbers to match descriptions  
    - Debet/Credit: Use bank account logic to predict opposite account
    """
    try:
        data = request.get_json()
        administration = data.get('administration', 'GoodwinSolutions')
        test_mode = data.get('test_mode', True)
        
        processor = BankingProcessor(test_mode=test_mode)
        patterns = processor.analyze_patterns_for_administration(administration)
        
        return jsonify({
            'success': True,
            'patterns': patterns,
            'implementation': {
                'administration_filter': f'Filtered by {administration}',
                'date_filter': 'Last 2 years of transaction data',
                'reference_matching': 'Historical reference numbers used for description matching',
                'bank_account_logic': 'Debet/Credit prediction based on bank account identification'
            }
        })
        
    except Exception as e:
        print(f"Pattern analysis error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/pattern-summary', methods=['GET'])
def get_pattern_summary():
    """Get pattern summary for an administration"""
    try:
        administration = request.args.get('administration', 'GoodwinSolutions')
        test_mode = request.args.get('test_mode', 'false').lower() == 'true'
        
        processor = BankingProcessor(test_mode=test_mode)
        summary = processor.get_pattern_summary(administration)
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        print(f"Pattern summary error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)