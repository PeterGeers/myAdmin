import pandas as pd
import glob
import os
import re
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from database import DatabaseManager
import json

class BankingProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.download_folder = os.path.expanduser("~/Downloads")  # Default download folder
    
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
        """Save approved transactions to database"""
        table_name = 'mutaties_test' if self.test_mode else 'mutaties'
        
        saved_count = 0
        for transaction in transactions:
            try:
                # Remove row_id before saving
                if 'row_id' in transaction:
                    del transaction['row_id']
                
                # Skip if amount is 0
                if float(transaction.get('TransactionAmount', 0)) == 0:
                    continue
                
                self.db.insert_transaction(transaction, table_name)
                saved_count += 1
                
            except Exception as e:
                print(f"Error saving transaction: {e}")
        
        return saved_count

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

if __name__ == '__main__':
    app.run(debug=True, port=5001)