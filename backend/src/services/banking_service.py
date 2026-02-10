"""
Banking Service

Handles banking transaction processing business logic including:
- CSV file scanning and processing
- IBAN validation and tenant checking
- Pattern matching for account assignment
- Sequence checking for duplicates
- Transaction saving and retrieval

Extracted from app.py during refactoring (Phase 3.1)
"""

from database import DatabaseManager
from banking_processor import BankingProcessor


class BankingService:
    """Service class for banking operations"""
    
    def __init__(self, test_mode=False):
        """
        Initialize BankingService
        
        Args:
            test_mode (bool): Whether to run in test mode (uses test database)
        """
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.processor = BankingProcessor(test_mode=test_mode)
    
    def scan_banking_files(self, folder_path=None):
        """
        Scan download folder for CSV files
        
        Args:
            folder_path (str, optional): Path to folder to scan. 
                                        Defaults to processor's download folder.
        
        Returns:
            dict: Result with 'success', 'files', and 'folder' keys
        """
        try:
            if folder_path is None:
                folder_path = self.processor.download_folder
            
            files = self.processor.get_csv_files(folder_path)
            
            return {
                'success': True,
                'files': files,
                'folder': folder_path
            }
        except Exception as e:
            print(f"Banking scan files error: {e}", flush=True)
            return {
                'success': False,
                'error': str(e)
            }

    def validate_iban_tenant(self, iban, tenant):
        """
        Validate that an IBAN belongs to the specified tenant
        
        Args:
            iban (str): IBAN to validate
            tenant (str): Tenant/administration name
            
        Returns:
            dict: Validation result with 'valid', 'tenant', and optional 'error' keys
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT administration FROM vw_lookup_accounts 
                WHERE rekeningNummer = %s
            """, (iban,))
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                iban_tenant = result['administration']
                if iban_tenant != tenant:
                    return {
                        'valid': False,
                        'tenant': iban_tenant,
                        'error': f'Access denied: Bank account {iban} belongs to {iban_tenant}. You are currently working in {tenant}. Please switch to {iban_tenant} to upload this file.'
                    }
                else:
                    return {
                        'valid': True,
                        'tenant': iban_tenant
                    }
            else:
                # IBAN not found in lookup - might be okay for new accounts
                print(f"Warning: IBAN {iban} not found in vw_lookup_accounts", flush=True)
                return {
                    'valid': True,  # Allow processing
                    'tenant': None,
                    'warning': f'IBAN {iban} not found in lookup table'
                }
        except Exception as e:
            print(f"Error validating IBAN: {e}", flush=True)
            return {
                'valid': False,
                'error': str(e)
            }

    def process_banking_files(self, file_paths, tenant, test_mode=None):
        """
        Process selected CSV banking files
        
        Args:
            file_paths (list): List of file paths to process
            tenant (str): Tenant/administration name
            test_mode (bool, optional): Override test mode for this operation
            
        Returns:
            dict: Processing result with transactions or error
        """
        try:
            if test_mode is None:
                test_mode = self.test_mode
            
            processor = BankingProcessor(test_mode=test_mode)
            df = processor.process_csv_files(file_paths)
            
            if df.empty:
                return {
                    'success': False,
                    'error': 'No data found in files'
                }
            
            # Validate that the IBAN(s) in the file belong to the current tenant
            if 'Ref1' in df.columns:
                ibans = df['Ref1'].dropna().unique().tolist()
                print(f"[TENANT VALIDATION] Current tenant: {tenant}", flush=True)
                print(f"[TENANT VALIDATION] Found IBANs in file: {ibans}", flush=True)
                
                for iban in ibans:
                    print(f"[TENANT VALIDATION] Checking IBAN: {iban}", flush=True)
                    validation = self.validate_iban_tenant(iban, tenant)
                    
                    if not validation['valid']:
                        return {
                            'success': False,
                            'error': validation['error']
                        }
                    else:
                        print(f"[TENANT VALIDATION] ALLOWED: IBAN matches current tenant", flush=True)
            
            records = processor.prepare_for_review(df)
            
            return {
                'success': True,
                'transactions': records,
                'count': len(records),
                'test_mode': test_mode
            }
            
        except Exception as e:
            print(f"Banking process files error: {e}", flush=True)
            return {
                'success': False,
                'error': str(e)
            }

    def check_sequences(self, iban, sequences, test_mode=None):
        """
        Check sequence numbers against database for duplicates
        
        Args:
            iban (str): IBAN to check sequences for
            sequences (list): List of sequence numbers to check
            test_mode (bool, optional): Override test mode for this operation
            
        Returns:
            dict: Result with existing sequences and duplicates
        """
        try:
            if test_mode is None:
                test_mode = self.test_mode
            
            db = DatabaseManager(test_mode=test_mode)
            table_name = 'mutaties'  # Always use 'mutaties' table
            existing_sequences = db.get_existing_sequences(iban, table_name)
            
            # Check for duplicates
            duplicates = [seq for seq in sequences if seq in existing_sequences]
            
            return {
                'success': True,
                'existing_sequences': existing_sequences,
                'duplicates': duplicates
            }
            
        except Exception as e:
            print(f"Check sequences error: {e}", flush=True)
            return {
                'success': False,
                'error': str(e)
            }

    def apply_patterns(self, transactions, tenant, use_enhanced=True, test_mode=None):
        """
        Apply pattern matching to predict debet/credit accounts
        
        Args:
            transactions (list): List of transaction dictionaries
            tenant (str): Tenant/administration name
            use_enhanced (bool): Whether to use enhanced pattern analysis
            test_mode (bool, optional): Override test mode for this operation
            
        Returns:
            dict: Result with updated transactions and pattern info
        """
        try:
            if test_mode is None:
                test_mode = self.test_mode
            
            if not transactions:
                return {
                    'success': False,
                    'error': 'No transactions provided'
                }
            
            # Add administration to each transaction if not present
            for tx in transactions:
                if 'administration' not in tx or not tx['administration']:
                    tx['administration'] = tenant
            
            if use_enhanced:
                # Use enhanced pattern analysis system
                processor = BankingProcessor(test_mode=test_mode)
                updated_transactions, results = processor.apply_enhanced_patterns(transactions, tenant)
                
                return {
                    'success': True,
                    'transactions': updated_transactions,
                    'enhanced_results': results,
                    'method': 'enhanced'
                }
            else:
                # Fall back to legacy pattern matching
                import re
                db = DatabaseManager(test_mode=test_mode)
                
                # Get patterns for this administration
                patterns_data = db.get_patterns(tenant)
                
                # Build pattern groups
                debet_patterns = {}
                credit_patterns = {}
                
                for pattern in patterns_data:
                    ref_num = pattern.get('referenceNumber')
                    if not ref_num:
                        continue
                        
                    # Escape special regex characters
                    escaped_ref = str(ref_num).replace('/', '\\/')
                    
                    debet_val = pattern.get('debet')
                    credit_val = pattern.get('credit')
                    
                    if debet_val and str(debet_val) < '1300':
                        key = f"{pattern.get('administration')}_{debet_val}_{credit_val}"
                        if key not in debet_patterns:
                            debet_patterns[key] = {
                                'debet': debet_val,
                                'credit': credit_val,
                                'patterns': []
                            }
                        debet_patterns[key]['patterns'].append(escaped_ref)
                        
                    if credit_val and str(credit_val) < '1300':
                        key = f"{pattern.get('administration')}_{debet_val}_{credit_val}"
                        if key not in credit_patterns:
                            credit_patterns[key] = {
                                'debet': debet_val,
                                'credit': credit_val,
                                'patterns': []
                            }
                        credit_patterns[key]['patterns'].append(escaped_ref)
                
                # Apply patterns to transactions
                for transaction in transactions:
                    description = str(transaction.get('TransactionDescription', ''))
                    
                    # If Credit is empty, try debet patterns
                    if not transaction.get('Credit'):
                        for pattern_group in debet_patterns.values():
                            if pattern_group['patterns']:
                                pattern_regex = '|'.join(pattern_group['patterns'])
                                try:
                                    match = re.search(pattern_regex, description, re.IGNORECASE)
                                    if match:
                                        transaction['ReferenceNumber'] = match.group(0)
                                        transaction['Credit'] = pattern_group['credit']
                                        break
                                except re.error:
                                    continue
                    
                    # If Debet is empty, try credit patterns  
                    elif not transaction.get('Debet'):
                        for pattern_group in credit_patterns.values():
                            if pattern_group['patterns']:
                                pattern_regex = '|'.join(pattern_group['patterns'])
                                try:
                                    match = re.search(pattern_regex, description, re.IGNORECASE)
                                    if match:
                                        transaction['ReferenceNumber'] = match.group(0)
                                        transaction['Debet'] = pattern_group['debet']
                                        break
                                except re.error:
                                    continue
                
                return {
                    'success': True,
                    'transactions': transactions,
                    'patterns_found': len(patterns_data),
                    'method': 'legacy'
                }
            
        except Exception as e:
            print(f"Pattern matching error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    def save_transactions(self, transactions, tenant, test_mode=None):
        """
        Save approved transactions to database with duplicate filtering
        
        Args:
            transactions (list): List of transaction dictionaries
            tenant (str): Tenant/administration name
            test_mode (bool, optional): Override test mode for this operation
            
        Returns:
            dict: Result with saved count and duplicate info
        """
        try:
            if test_mode is None:
                test_mode = self.test_mode
            
            # Add administration field to all transactions
            for transaction in transactions:
                transaction['administration'] = tenant
            
            db = DatabaseManager(test_mode=test_mode)
            table_name = 'mutaties'  # Always use 'mutaties' table
            
            # Group transactions by IBAN (Ref1)
            ibans = list(set([t.get('Ref1') for t in transactions if t.get('Ref1')]))
            transactions_to_save = []
            
            for iban in ibans:
                # Get existing sequences for this IBAN (filtered by tenant)
                existing_sequences = db.get_existing_sequences(iban, table_name, administration=tenant)
                
                # Filter transactions for this IBAN that don't exist
                iban_transactions = [t for t in transactions if t.get('Ref1') == iban]
                new_transactions = [t for t in iban_transactions if t.get('Ref2') not in existing_sequences]
                
                transactions_to_save.extend(new_transactions)
            
            # Save only new transactions
            processor = BankingProcessor(test_mode=test_mode)
            saved_count = processor.save_approved_transactions(transactions_to_save)
            
            # Invalidate cache after saving transactions
            if saved_count > 0:
                from mutaties_cache import invalidate_cache
                invalidate_cache()
                print(f"[CACHE] Invalidated cache after saving {saved_count} transactions", flush=True)
            
            total_count = len(transactions)
            duplicate_count = total_count - len(transactions_to_save)
            
            return {
                'success': True,
                'saved_count': saved_count,
                'total_count': total_count,
                'duplicate_count': duplicate_count,
                'table': table_name,
                'tenant': tenant,
                'message': f'Saved {saved_count} new transactions for {tenant}, skipped {duplicate_count} duplicates'
            }
            
        except Exception as e:
            print(f"Banking save transactions error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    def get_lookups(self, tenant):
        """
        Get mapping data for account codes and descriptions
        
        Args:
            tenant (str): Tenant/administration name
            
        Returns:
            dict: Lookup data with accounts, descriptions, and bank accounts
        """
        try:
            db = DatabaseManager(test_mode=self.test_mode)
            
            # Get bank account lookups - FILTERED BY CURRENT TENANT
            all_bank_accounts = db.get_bank_account_lookups()
            bank_accounts = [acc for acc in all_bank_accounts if acc.get('administration') == tenant]
            
            # Get recent transactions for account mapping - FILTERED BY CURRENT TENANT
            all_recent_transactions = db.get_recent_transactions(limit=100)
            recent_transactions = [tx for tx in all_recent_transactions if tx.get('administration') == tenant]
            
            # Extract unique account codes and descriptions
            accounts = set()
            descriptions = set()
            
            for tx in recent_transactions:
                if tx.get('Debet'):
                    accounts.add(tx['Debet'])
                if tx.get('Credit'):
                    accounts.add(tx['Credit'])
                if tx.get('TransactionDescription'):
                    descriptions.add(tx['TransactionDescription'])
            
            return {
                'success': True,
                'accounts': sorted(list(accounts)),
                'descriptions': sorted(list(descriptions)),
                'bank_accounts': bank_accounts
            }
            
        except Exception as e:
            print(f"Banking lookups error: {e}", flush=True)
            return {
                'success': False,
                'error': str(e)
            }

    def get_mutaties(self, filters, tenant, user_tenants):
        """
        Get mutaties with filters
        
        Args:
            filters (dict): Filter parameters (years, administration)
            tenant (str): Current tenant
            user_tenants (list): List of tenants user has access to
            
        Returns:
            dict: Result with mutaties list
        """
        try:
            from datetime import datetime
            
            db = DatabaseManager(test_mode=self.test_mode)
            table_name = 'mutaties_test' if self.test_mode else 'mutaties'
            
            # Get filter parameters
            years = filters.get('years', [str(datetime.now().year)])
            administration = filters.get('administration', 'all')
            
            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Build WHERE clause
            where_conditions = []
            params = []
            
            # Years filter
            if years and years != ['']:
                year_placeholders = ','.join(['%s'] * len(years))
                where_conditions.append(f"YEAR(TransactionDate) IN ({year_placeholders})")
                params.extend(years)
            
            # Administration filter - MUST respect user's accessible tenants
            if administration == 'all':
                # Show all tenants user has access to
                if len(user_tenants) == 1:
                    where_conditions.append("administration = %s")
                    params.append(user_tenants[0])
                else:
                    placeholders = ','.join(['%s'] * len(user_tenants))
                    where_conditions.append(f"administration IN ({placeholders})")
                    params.extend(user_tenants)
            else:
                # Validate user has access to requested administration
                if administration not in user_tenants:
                    return {
                        'success': False,
                        'error': 'Access denied to administration'
                    }
                where_conditions.append("administration = %s")
                params.append(administration)
            
            where_clause = 'WHERE ' + ' AND '.join(where_conditions) if where_conditions else ''
            
            query = f"""
                SELECT ID, TransactionNumber, TransactionDate, TransactionDescription, 
                       TransactionAmount, Debet, Credit, ReferenceNumber, 
                       Ref1, Ref2, Ref3, Ref4, Administration
                FROM {table_name} 
                {where_clause}
                ORDER BY TransactionDate DESC, ID DESC
            """
            cursor.execute(query, params)
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'mutaties': results,
                'count': len(results),
                'table': table_name
            }
            
        except Exception as e:
            print(f"Get mutaties error: {e}", flush=True)
            return {
                'success': False,
                'error': str(e)
            }

    def update_mutatie(self, mutatie_id, data, tenant):
        """
        Update a mutatie record
        
        Args:
            mutatie_id (int): ID of record to update
            data (dict): Updated field values
            tenant (str): Current tenant (for validation)
            
        Returns:
            dict: Result with success status
        """
        try:
            from datetime import datetime
            
            db = DatabaseManager(test_mode=self.test_mode)
            table_name = 'mutaties_test' if self.test_mode else 'mutaties'
            
            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            # First, verify the record belongs to the current tenant
            cursor.execute(f"SELECT administration FROM {table_name} WHERE ID = %s", (mutatie_id,))
            existing_record = cursor.fetchone()
            
            if not existing_record:
                cursor.close()
                conn.close()
                return {
                    'success': False,
                    'error': 'Record not found'
                }
            
            if existing_record['administration'] != tenant:
                cursor.close()
                conn.close()
                return {
                    'success': False,
                    'error': 'Access denied: Record belongs to different tenant'
                }
            
            # Update the record - FORCE Administration to current tenant
            update_query = f"""
                UPDATE {table_name} SET 
                    TransactionNumber = %s,
                    TransactionDate = %s,
                    TransactionDescription = %s,
                    TransactionAmount = %s,
                    Debet = %s,
                    Credit = %s,
                    ReferenceNumber = %s,
                    Ref1 = %s,
                    Ref2 = %s,
                    Ref3 = %s,
                    Ref4 = %s,
                    administration = %s
                WHERE ID = %s
            """
            
            # Convert date to proper format
            transaction_date = data.get('TransactionDate')
            if transaction_date and 'GMT' in str(transaction_date):
                transaction_date = datetime.strptime(transaction_date, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d')
            
            cursor.execute(update_query, (
                data.get('TransactionNumber'),
                transaction_date,
                data.get('TransactionDescription'),
                data.get('TransactionAmount'),
                data.get('Debet'),
                data.get('Credit'),
                data.get('ReferenceNumber'),
                data.get('Ref1'),
                data.get('Ref2'),
                data.get('Ref3'),
                data.get('Ref4'),
                tenant,  # FORCE to current tenant
                mutatie_id
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Record {mutatie_id} updated successfully with administration={tenant}", flush=True)
            
            return {
                'success': True,
                'message': f'Record {mutatie_id} updated successfully'
            }
            
        except Exception as e:
            print(f"Update error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    def check_accounts(self, tenant, end_date=None):
        """
        Check banking account balances
        
        Args:
            tenant (str): Tenant/administration name
            end_date (str, optional): End date for balance check
            
        Returns:
            dict: Result with account balances
        """
        try:
            processor = BankingProcessor(test_mode=self.test_mode)
            
            # Pass tenant to filter accounts
            balances = processor.check_banking_accounts(end_date=end_date, administration=tenant)
            
            return {
                'success': True,
                'balances': balances
            }
            
        except Exception as e:
            print(f"Banking check accounts error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_revolut_balance(self, iban, account_code, start_date, expected_balance):
        """
        Check Revolut balance gaps by comparing calculated vs Ref3 balance
        
        Args:
            iban (str): IBAN to check
            account_code (str): Account code
            start_date (str): Start date for check
            expected_balance (float): Expected final balance
            
        Returns:
            dict: Result with balance gaps and discrepancies
        """
        try:
            processor = BankingProcessor(test_mode=self.test_mode)
            
            result = processor.check_revolut_balance_gaps(
                iban=iban,
                account_code=account_code,
                start_date=start_date,
                expected_final_balance=expected_balance
            )
            
            # Return only transactions with gaps (non-zero discrepancies)
            if result.get('success'):
                return {
                    'success': True,
                    'iban': result.get('iban'),
                    'account_code': result.get('account_code'),
                    'start_date': result.get('start_date'),
                    'total_transactions': result.get('total_transactions'),
                    'calculated_final_balance': result.get('calculated_final_balance'),
                    'expected_final_balance': result.get('expected_final_balance'),
                    'final_discrepancy': result.get('final_discrepancy'),
                    'balance_gaps_found': result.get('balance_gaps_found'),
                    'transactions_with_gaps': result.get('transactions_with_gaps', []),
                    'summary': result.get('summary')
                }
            else:
                return result
            
        except Exception as e:
            print(f"Check Revolut balance error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
