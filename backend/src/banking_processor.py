"""
Banking Processor

Handles CSV file processing, duplicate detection, and transaction import
for bank statement files (Rabobank, Revolut, generic).

Banking account checks (balance verification, sequence gaps) are in banking_checks.py.
"""

import pandas as pd
import glob
import os
from datetime import datetime
from database import DatabaseManager
from db_exceptions import ClosedPeriodError
from pattern_analyzer import PatternAnalyzer
from banking_checks import BankingChecks, _get_opening_balance_date  # noqa: F401
import unicodedata


class BankingProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.pattern_analyzer = PatternAnalyzer(test_mode=test_mode)
        self.download_folder = os.path.expanduser("~/Downloads")  # Default download folder
        self._checks = BankingChecks(self.db)

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
                'TransactionDate': df.iloc[:, 4] if len(df.columns) > 4 else '',
                'TransactionDescription': '',
                'TransactionAmount': df.iloc[:, 6] if len(df.columns) > 6 else '',
                'Debet': '',
                'Credit': '',
                'ReferenceNumber': f'Rabo {datetime.now().strftime("%Y-%m-%d")}',
                'Ref1': df.iloc[:, 0] if len(df.columns) > 0 else '',
                'Ref2': df.iloc[:, 3] if len(df.columns) > 3 else '',
                'Ref3': '',
                'Ref4': file_path,
                'Administration': 'GoodwinSolutions'
            }

            # Build transaction description from available columns
            desc_fields = []
            if len(df.columns) > 8:
                desc_fields.append(df.iloc[:, 8].fillna(''))
            if len(df.columns) > 19:
                desc_fields.append(df.iloc[:, 19].fillna(''))

            if desc_fields:
                standard_columns['TransactionDescription'] = (
                    desc_fields[0].astype(str) + ' ' + desc_fields[1].astype(str)
                    if len(desc_fields) > 1
                    else desc_fields[0].astype(str)
                )

            # Process amounts and debit/credit
            if 'TransactionAmount' in standard_columns and not standard_columns['TransactionAmount'].empty:
                amounts = standard_columns['TransactionAmount'].astype(str)
                signs = amounts.str[0]
                amounts_clean = amounts.str[1:].str.replace(',', '.').astype(float)

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

            if 'CSV_' in os.path.basename(file_path):
                df = self.read_rabo_csv(file_path)
            elif os.path.basename(file_path).startswith('RA_CC_'):
                df = self.read_generic_csv(file_path)
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
        records = df.to_dict('records')

        for i, record in enumerate(records):
            record['row_id'] = i
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = ''
                elif isinstance(value, (pd.Timestamp, datetime)):
                    record[key] = value.strftime('%Y-%m-%d')

        return records

    def save_approved_transactions(self, transactions):
        """Save approved transactions to database with duplicate detection.

        Before saving, checks that no non-zero-amount transaction targets a
        closed fiscal year.  If any do, raises ``ClosedPeriodError`` and no
        inserts occur.
        """
        # --- Closed-period guard (before any DB writes) ---
        year_admin_pairs = {}
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

        # --- Save logic with duplicate detection ---
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

                # Ref2-based duplicate detection (exact match, takes priority)
                ref2 = transaction.get('Ref2', '').strip()
                if ref2:
                    cursor.execute(f"""
                        SELECT ID FROM {table_name}
                        WHERE Ref2 = %s
                        AND administration = %s
                        LIMIT 1
                    """, (ref2, transaction.get('administration')))

                    if cursor.fetchone():
                        print(f"Skipping duplicate (Ref2 match): {ref2}")
                        continue

                # Check for duplicate using normalized text
                desc_normalized = self.normalize_text(transaction.get('TransactionDescription', ''))
                cursor.execute(f"""
                    SELECT ID FROM {table_name}
                    WHERE TransactionAmount = %s
                    AND TransactionDate = %s
                    AND administration = %s
                    LIMIT 1
                """, (
                    transaction.get('TransactionAmount'),
                    transaction.get('TransactionDate'),
                    transaction.get('administration')
                ))

                existing = cursor.fetchall()
                if existing:
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

    # ──────────────────────────────────────────────────────────────────────────
    # Banking Checks (delegated to BankingChecks helper)
    # ──────────────────────────────────────────────────────────────────────────

    def check_banking_accounts(self, end_date=None, administration=None):
        """Check banking account balances (delegated to BankingChecks)."""
        return self._checks.check_banking_accounts(end_date=end_date, administration=administration)

    def check_sequence_numbers(self, account_code=None, administration=None, start_date='2025-01-01'):
        """Check Ref2 sequence numbers are consecutive (delegated to BankingChecks)."""
        return self._checks.check_sequence_numbers(
            account_code=account_code, administration=administration, start_date=start_date
        )

    def check_revolut_balance_gaps(self, iban, account_code,
                                   start_date='2025-05-01', expected_final_balance=262.54):
        """Check Revolut balance gaps (delegated to BankingChecks)."""
        return self._checks.check_revolut_balance_gaps(
            iban=iban, account_code=account_code,
            start_date=start_date, expected_final_balance=expected_final_balance
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Pattern Analysis
    # ──────────────────────────────────────────────────────────────────────────

    def analyze_patterns_for_administration(self, administration,
                                            reference_number=None, debet_account=None,
                                            credit_account=None):
        """Analyze patterns for an administration using the enhanced pattern analyzer."""
        try:
            filter_desc = f"for {administration}"
            if reference_number:
                filter_desc += f" (ReferenceNumber: {reference_number})"
            if debet_account:
                filter_desc += f" (Debet: {debet_account})"
            if credit_account:
                filter_desc += f" (Credit: {credit_account})"

            print(f"🔍 Starting enhanced pattern analysis {filter_desc}...")

            patterns = self.pattern_analyzer.analyze_historical_patterns(
                administration, reference_number, debet_account, credit_account
            )

            print("✅ Pattern analysis complete:")
            print(f"   - Processed {patterns['total_transactions']} transactions")
            print(f"   - Discovered {patterns['patterns_discovered']} patterns")
            print(f"   - Date range: {patterns['date_range']['from']} to {patterns['date_range']['to']}")

            return patterns

        except Exception as e:
            print(f"❌ Pattern analysis failed: {e}")
            raise e

    def apply_enhanced_patterns(self, transactions, administration):
        """Apply enhanced pattern matching to predict missing values."""
        try:
            print(f"🔧 Applying enhanced patterns to {len(transactions)} transactions...")

            if hasattr(transactions, 'to_dict'):
                transactions = transactions.to_dict('records')

            updated_transactions, results = self.pattern_analyzer.apply_patterns_to_transactions(
                transactions, administration
            )

            print("✅ Enhanced pattern application complete:")
            print(f"   - Debet predictions: {results['predictions_made']['debet']}")
            print(f"   - Credit predictions: {results['predictions_made']['credit']}")
            print(f"   - Reference predictions: {results['predictions_made']['reference']}")
            print(f"   - Average confidence: {results['average_confidence']:.2f}")

            return updated_transactions, results

        except Exception as e:
            print(f"❌ Enhanced pattern application failed: {e}")
            raise e

    def get_pattern_summary(self, administration):
        """Get a summary of discovered patterns for an administration"""
        try:
            return self.pattern_analyzer.get_pattern_summary(administration)
        except Exception as e:
            print(f"❌ Failed to get pattern summary: {e}")
            raise e
