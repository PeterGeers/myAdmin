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

from typing import Any, Dict, List, Optional

from database import DatabaseManager
from banking_processor import BankingProcessor
from db_exceptions import ClosedPeriodError


class BankingService:
    """Service class for banking operations"""
    
    def __init__(self, test_mode: bool = False) -> None:
        """
        Initialize BankingService
        
        Args:
            test_mode (bool): Whether to run in test mode (uses test database)
        """
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
        self.processor = BankingProcessor(test_mode=test_mode)
    
    def scan_banking_files(self, folder_path: Optional[str] = None) -> Dict[str, Any]:
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

    def validate_iban_tenant(self, iban: str, tenant: str) -> Dict[str, Any]:
        """
        Validate that an IBAN belongs to the specified tenant
        
        Uses get_bank_account_lookups() to resolve bank accounts from
        rekeningschema with $.bank_account flag instead of vw_lookup_accounts.
        
        Args:
            iban (str): IBAN to validate
            tenant (str): Tenant/administration name
            
        Returns:
            dict: Validation result with 'valid', 'tenant', and optional 'error' keys
        """
        try:
            # Get all bank accounts using canonical $.bank_account flag source
            all_accounts = self.db.get_bank_account_lookups(administration=None)
            
            # Find the IBAN in the bank account list
            matching_account = None
            for account in all_accounts:
                if account['rekeningNummer'] == iban:
                    matching_account = account
                    break
            
            if matching_account:
                iban_tenant = matching_account['administration']
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
                print(f"Warning: IBAN {iban} not found in bank account lookups", flush=True)
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

    def process_banking_files(self, file_paths: List[str], tenant: str, test_mode: Optional[bool] = None) -> Dict[str, Any]:
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

    def check_sequences(self, iban: str, sequences: List[Dict[str, Any]], test_mode: Optional[bool] = None, administration: Optional[str] = None) -> Dict[str, Any]:
        """
        Check sequence numbers against database for duplicates
        
        Args:
            iban (str): IBAN to check sequences for
            sequences (list): List of sequence numbers to check
            test_mode (bool, optional): Override test mode for this operation
            administration (str, optional): Tenant to scope the sequence check to
            
        Returns:
            dict: Result with existing sequences and duplicates
        """
        try:
            if test_mode is None:
                test_mode = self.test_mode
            
            db = DatabaseManager(test_mode=test_mode)
            table_name = 'mutaties'  # Always use 'mutaties' table
            existing_sequences = db.get_existing_sequences(iban, table_name, administration=administration)
            
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

    def apply_patterns(self, transactions: List[Dict[str, Any]], tenant: str, use_enhanced: bool = True, test_mode: Optional[bool] = None) -> Dict[str, Any]:
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

    def save_transactions(self, transactions: List[Dict[str, Any]], tenant: str, test_mode: Optional[bool] = None) -> Dict[str, Any]:
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
            
        except ClosedPeriodError:
            raise
            
        except Exception as e:
            print(f"Banking save transactions error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    def get_lookups(self, tenant: str) -> Dict[str, Any]:
        """
        Get mapping data for account codes and descriptions
        
        Args:
            tenant (str): Tenant/administration name
            
        Returns:
            dict: Lookup data with accounts, descriptions, and bank accounts
        """
        try:
            db = DatabaseManager(test_mode=self.test_mode)
            
            # Get bank account lookups filtered by tenant at SQL level
            bank_accounts = db.get_bank_account_lookups(administration=tenant)
            
            # Get credit card account lookups filtered by tenant
            credit_card_accounts = db.get_credit_card_lookups(administration=tenant)
            
            # Get exchange rate account for foreign currency difference bookings
            exchange_rate_accounts = db.get_exchange_rate_account(administration=tenant)
            
            # Get recent transactions for account mapping filtered by tenant at SQL level
            recent_transactions = db.get_recent_transactions(limit=100, administration=tenant)
            
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
                'bank_accounts': bank_accounts,
                'credit_card_accounts': credit_card_accounts,
                'exchange_rate_account': exchange_rate_accounts[0]['Account'] if exchange_rate_accounts else None
            }
            
        except Exception as e:
            print(f"Banking lookups error: {e}", flush=True)
            return {
                'success': False,
                'error': str(e)
            }

    def get_mutaties(self, filters: Dict[str, Any], tenant: str, user_tenants: List[str]) -> Dict[str, Any]:
        """Get mutaties with filters. Delegates to BankingMutatieService."""
        from services.banking_mutatie_service import BankingMutatieService
        svc = BankingMutatieService(test_mode=self.test_mode)
        return svc.get_mutaties(filters, tenant, user_tenants)

    def update_mutatie(self, mutatie_id: int, data: Dict[str, Any], tenant: str) -> Dict[str, Any]:
        """Update a mutatie record. Delegates to BankingMutatieService."""
        from services.banking_mutatie_service import BankingMutatieService
        svc = BankingMutatieService(test_mode=self.test_mode)
        return svc.update_mutatie(mutatie_id, data, tenant)

    def check_accounts(self, tenant: str, end_date: Optional[str] = None) -> Dict[str, Any]:
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
    
    def check_revolut_balance(self, iban: str, account_code: str, start_date: str, expected_balance: float) -> Dict[str, Any]:
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
