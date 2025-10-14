import pandas as pd
import glob
import os
import re
from datetime import datetime
from database import DatabaseManager
import yaml

class RaboCsvProcessor:
    def __init__(self, config_file="conf/config.yml"):
        """Initialize processor with configuration"""
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)['production']
        self.db = DatabaseManager()
    
    def get_csv_files(self):
        """Get all CSV files matching pattern CSV_[O|A]"""
        pattern = os.path.join(self.config['download'], "CSV_[OA]*")
        return glob.glob(pattern)
    
    def read_csv_files(self, files):
        """Read and combine all CSV files"""
        bookings = pd.DataFrame()
        
        for i, file in enumerate(files):
            print(f"Processing file {i+1}: {file}")
            df = pd.read_csv(
                file,
                encoding='latin1',
                dtype=str,
                quotechar='"'
            )
            
            if i == 0:
                bookings = df
            else:
                bookings = pd.concat([bookings, df], ignore_index=True)
        
        return bookings
    
    def clean_column_names(self, bookings):
        """Clean and rename columns"""
        # Fix special character in column names
        columns = list(bookings.columns)
        if len(columns) > 11:
            columns[11] = "iniPartij"
            bookings.columns = columns
        
        return bookings
    
    def join_accounts(self, bookings):
        """Join with bank account lookup table"""
        # Get bank accounts from database
        accounts = self.db.get_records("lookupbankaccounts_R")
        accounts_df = pd.DataFrame(accounts)
        
        # Rename first column to match
        bookings.columns.values[0] = "rekeningNummer"
        
        # Join with accounts
        bookings = bookings.merge(accounts_df, on="rekeningNummer", how="left")
        
        return bookings
    
    def rename_standard_columns(self, bookings):
        """Rename columns to standard format"""
        column_mapping = {
            bookings.columns[0]: 'Ref1',
            bookings.columns[3]: 'Ref2', 
            bookings.columns[4]: 'TransactionDate',
            bookings.columns[6]: 'TransactionAmount'
        }
        
        bookings = bookings.rename(columns=column_mapping)
        return bookings
    
    def add_transaction_number(self, bookings):
        """Add transaction number with current date"""
        today = datetime.now().strftime("%Y-%m-%d")
        bookings['TransactionNumber'] = f'Rabo {today}'
        return bookings
    
    def clean_ref2(self, bookings):
        """Clean Ref2 column"""
        bookings['Ref2'] = pd.to_numeric(bookings['Ref2'], errors='coerce').astype(str)
        return bookings
    
    def standardize_vendor_names(self, bookings):
        """Standardize vendor names"""
        if 'Naam tegenpartij' in bookings.columns:
            bookings.loc[bookings['Naam tegenpartij'].str.contains('SHELL TO', na=False), 'Naam tegenpartij'] = 'Shell Kosovar'
        return bookings
    
    def build_transaction_description(self, bookings):
        """Build transaction description from multiple fields"""
        # Find column indices for description fields
        description_fields = [
            'Naam tegenpartij',
            'Naam uiteindelijke partij', 
            'Code',
            'Omschrijving',
            'Betalingskenmerk',
            'Tegenrekening',
            'BIC tegenpartij',
            'Transactiereferentie',
            'Machtigingskenmerk',
            'Incassant ID',
            'Ref2',
            'Saldo na trn'
        ]
        
        # Get indices of existing columns
        field_indices = []
        for field in description_fields:
            if field in bookings.columns:
                field_indices.append(bookings.columns.get_loc(field))
        
        # Build descriptions
        descriptions = []
        for idx, row in bookings.iterrows():
            desc_parts = []
            for col_idx in field_indices:
                value = str(row.iloc[col_idx]) if pd.notna(row.iloc[col_idx]) else ""
                if value and value != "nan":
                    desc_parts.append(value)
            
            description = " ".join(desc_parts)
            # Clean up description
            description = re.sub(r'\bNA\b', ' ', description)
            description = re.sub(r'\s+', ' ', description)
            description = description.replace('Google Pay', 'GPay')
            descriptions.append(description.strip())
        
        bookings['TransactionDescription'] = descriptions
        return bookings
    
    def process_amounts(self, bookings):
        """Process transaction amounts and determine debit/credit"""
        # Extract sign and amount
        bookings['dc'] = bookings['TransactionAmount'].str[0]
        bookings['TransactionAmount'] = bookings['TransactionAmount'].str[1:]
        
        # Convert amount to numeric (replace comma with dot)
        bookings['TransactionAmount'] = bookings['TransactionAmount'].str.replace(',', '.')
        bookings['TransactionAmount'] = pd.to_numeric(bookings['TransactionAmount'], errors='coerce')
        
        # Set debit/credit based on sign
        bookings['Debet'] = bookings.apply(
            lambda row: row['Account'] if row['dc'] == '+' else '', axis=1
        )
        bookings['Credit'] = bookings.apply(
            lambda row: row['Account'] if row['dc'] == '-' else '', axis=1
        )
        
        return bookings
    
    def add_reference_columns(self, bookings):
        """Add empty reference columns"""
        bookings['ReferenceNumber'] = ''
        bookings['Ref3'] = ''
        bookings['Ref4'] = ''
        return bookings
    
    def get_transaction_codes(self, bookings):
        """Get transaction codes for each administration"""
        administrations = bookings['Administration'].unique()
        processed_data = pd.DataFrame()
        
        for admin in administrations:
            admin_data = bookings[bookings['Administration'] == admin]
            # Apply transaction codes logic (would need to implement getTransactionsCodes equivalent)
            codes_data = self.apply_transaction_codes(admin_data)
            
            if processed_data.empty:
                processed_data = codes_data
            else:
                processed_data = pd.concat([processed_data, codes_data], ignore_index=True)
        
        return processed_data
    
    def apply_transaction_codes(self, data):
        """Apply transaction codes logic (placeholder for R function)"""
        # This would implement the logic from getTransactionsCodes R function
        # For now, return data as-is
        return data
    
    def prevent_duplicates_and_write(self, df):
        """Prevent duplicate entries and write to database"""
        ref1_numbers = sorted(df['Ref1'].unique())
        
        for ref1 in ref1_numbers:
            # Get existing transaction numbers from database
            used_transactions = self.db.get_used_transaction_numbers(ref1)
            existing_ref2s = [t['Ref2'] for t in used_transactions]
            
            # Filter out already existing transactions
            to_write = df[
                (df['Ref1'] == ref1) & 
                (~df['Ref2'].isin(existing_ref2s))
            ]
            
            # Write to database if there are new transactions
            if len(to_write) > 0:
                self.db.write_transactions(to_write.to_dict('records'))
                print(f"Written {len(to_write)} transactions for {ref1}")
    
    def cleanup_files(self):
        """Remove processed CSV files"""
        pattern = os.path.join(self.config['download'], "CSV_[OA]*_accounts*")
        files_to_remove = glob.glob(pattern)
        
        for file in files_to_remove:
            try:
                os.remove(file)
                print(f"Removed: {file}")
            except Exception as e:
                print(f"Error removing {file}: {e}")
    
    def process_rabo_csv_files(self):
        """Main processing function"""
        print("Starting Rabobank CSV processing...")
        
        # Get CSV files
        files = self.get_csv_files()
        if not files:
            print("No CSV files found matching pattern CSV_[OA]*")
            return
        
        print(f"Found {len(files)} CSV files to process")
        
        # Read and combine files
        bookings = self.read_csv_files(files)
        print(f"Loaded {len(bookings)} transactions")
        
        # Process data
        bookings = self.clean_column_names(bookings)
        bookings = self.join_accounts(bookings)
        bookings = self.rename_standard_columns(bookings)
        bookings = self.add_transaction_number(bookings)
        bookings = self.clean_ref2(bookings)
        bookings = self.standardize_vendor_names(bookings)
        bookings = self.build_transaction_description(bookings)
        bookings = self.process_amounts(bookings)
        bookings = self.add_reference_columns(bookings)
        
        # Get transaction codes and process by administration
        processed_df = self.get_transaction_codes(bookings)
        
        # Prevent duplicates and write to database
        self.prevent_duplicates_and_write(processed_df)
        
        # Cleanup processed files
        self.cleanup_files()
        
        print("Rabobank CSV processing completed")

if __name__ == "__main__":
    processor = RaboCsvProcessor()
    processor.process_rabo_csv_files()