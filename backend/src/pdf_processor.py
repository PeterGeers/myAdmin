"""
PDF Processor - main entry point for file processing and transaction extraction.

Orchestrates parsing strategies, AI extraction, and duplicate decision handling.
Delegates to:
  - pdf_parsing_strategies: file-type specific text extraction
  - pdf_ai_extraction: AI-powered invoice data extraction
  - pdf_decision_handler: duplicate transaction decision handling
"""
import re
import os
from datetime import datetime
from typing import Dict, List, Optional
from csv_rules import CsvRuleEngine
from config import Config
from pdf_parsing_strategies import (
    process_pdf,
    process_image,
    process_csv,
    process_mhtml,
    process_eml,
    generic_parse,
)
from pdf_ai_extraction import extract_with_ai, log_ai_usage
from pdf_decision_handler import (
    handle_duplicate_decision as _handle_duplicate_decision_func,
    handle_continue_decision as _handle_continue_decision_func,
    handle_cancel_decision as _handle_cancel_decision_func,
)


class PDFProcessor:
    def __init__(self, test_mode: bool = False, tenant: str = None):
        self.csv_rule_engine = CsvRuleEngine()
        self.config = Config(test_mode=test_mode)
        self._current_tenant = tenant

    def process_file(self, file_path, drive_result, folder_name='Unknown'):
        """Process PDF, image, or CSV file"""
        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext == '.pdf':
            return process_pdf(file_path, drive_result, self.config, folder_name)
        elif file_ext in ['.jpg', '.jpeg', '.png']:
            return process_image(file_path, drive_result, self.config, folder_name, tenant=self._current_tenant)
        elif file_ext == '.csv':
            return process_csv(file_path, drive_result, self.config, folder_name)
        elif file_ext == '.mhtml':
            return process_mhtml(file_path, drive_result, self.config, folder_name)
        elif file_ext == '.eml':
            return process_eml(file_path, drive_result, self.config, folder_name)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

    def process_pdf(self, file_path, drive_result, folder_name='Unknown'):
        """Legacy method for backward compatibility"""
        return self.process_file(file_path, drive_result, folder_name)

    def extract_transactions(self, file_data):
        """Extract transactions from processed file data.
        
        Uses AI extraction as the primary path, with CSV rule matching
        as an alternative for structured files.
        """
        lines = file_data['txt'].split('\n')
        folder_name = file_data['folder'].lower()

        # Image with pre-extracted AI data
        if 'ai_data' in file_data:
            return self._format_vendor_transactions(file_data['ai_data'], file_data)

        # CSV rule match
        csv_result = self._apply_csv_rule(lines, folder_name)
        if csv_result:
            return self._format_vendor_transactions(csv_result, file_data)

        # AI extraction (sole path for PDF/EML/MHTML/unmatched CSV)
        ai_result = self._extract_with_ai(lines, folder_name)
        if ai_result and ai_result.get('total_amount', 0) > 0:
            return self._format_vendor_transactions(ai_result, file_data)

        # AI failed — return empty transactions with failure marker
        failure_data = ai_result if ai_result else {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'description': f'{folder_name} invoice',
            'vendor': folder_name
        }
        return self._format_vendor_transactions(failure_data, file_data)

    def _extract_with_ai(self, lines, folder_name):
        """Extract invoice data using AI only. No vendor-specific fallback."""
        ai_result = extract_with_ai(lines, folder_name)
        # Log AI usage with actual token counts from the API response
        log_ai_usage(folder_name, ai_result, self._current_tenant)
        return ai_result

    def _format_vendor_transactions(self, vendor_data, file_data):
        """Format vendor-specific data into standard transaction format"""
        transactions = []

        # Get reference number from folder name
        folder_name = file_data['folder'].split('/')[-1] if '/' in file_data['folder'] else file_data['folder']
        reference_number = folder_name.replace('testFacturen/', '').replace('Facturen/', '')

        # Get last transactions to copy debit/credit accounts like R script
        try:
            from transaction_logic import TransactionLogic
            tl = TransactionLogic(test_mode=self.config.test_mode if hasattr(self.config, 'test_mode') else False)
            last_transactions = tl.get_last_transactions(reference_number)
            # Handle error result (no booking history for vendor)
            if isinstance(last_transactions, dict) and last_transactions.get('error'):
                raise ValueError(last_transactions['message'])
            # Use first transaction for main amount, second for VAT (like R script df[1] and df[2])
            main_debet = last_transactions[0]['Debet'] if last_transactions else '4000'
            main_credit = last_transactions[0]['Credit'] if last_transactions else '1300'
            vat_debet = last_transactions[1]['Debet'] if len(last_transactions) > 1 else '2010'
            vat_credit = last_transactions[1]['Credit'] if len(last_transactions) > 1 else main_debet
        except Exception as e:
            print(f"Error getting last transactions: {e}")
            main_debet, main_credit = '4000', '1300'
            vat_debet, vat_credit = '2010', '4000'

        if isinstance(vendor_data, list):  # Multiple transactions (e.g., credit cards)
            for item in vendor_data:
                transactions.append({
                    'date': item['date'],
                    'description': item['description'],
                    'amount': item['amount'],
                    'debet': main_debet,
                    'credit': main_credit,
                    'ref': file_data['folder'],
                    'ref1': None,
                    'ref2': None,
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
        else:  # Single transaction with amounts
            if 'total_amount' in vendor_data:
                transactions.append({
                    'date': vendor_data['date'],
                    'description': vendor_data['description'],
                    'amount': vendor_data['total_amount'],
                    'debet': main_debet,
                    'credit': main_credit,
                    'ref': file_data['folder'],
                    'ref1': None,
                    'ref2': None,
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })
            # Only add VAT transaction if VAT amount > 0
            if 'vat_amount' in vendor_data and vendor_data['vat_amount'] > 0:
                transactions.append({
                    'date': vendor_data['date'],
                    'description': f"VAT - {vendor_data['description']}",
                    'amount': vendor_data['vat_amount'],
                    'debet': vat_debet,
                    'credit': vat_credit,
                    'ref': file_data['folder'],
                    'ref1': None,
                    'ref2': None,
                    'ref3': file_data['url'],
                    'ref4': file_data['name']
                })

        # Pass through parser_used_hint from vendor_data to transactions
        if isinstance(vendor_data, dict) and vendor_data.get('parser_used_hint'):
            for transaction in transactions:
                transaction['parser_used_hint'] = vendor_data['parser_used_hint']

        # Perform duplicate detection after data extraction but before database insertion
        try:
            duplicate_info = self._check_for_duplicates(transactions, reference_number, file_data)
            if duplicate_info and duplicate_info.get('has_duplicates', False):
                for transaction in transactions:
                    transaction['duplicate_info'] = duplicate_info
                print(f"Duplicate detected for {reference_number}: {duplicate_info['duplicate_count']} matches found")
        except Exception as e:
            print(f"Error during duplicate detection: {e}")

        return transactions

    def _generic_parse(self, lines, file_data):
        """Generic parsing for unknown vendors — delegates to pdf_parsing_strategies."""
        return generic_parse(lines, file_data)

    def _apply_csv_rule(self, lines, folder_name):
        """Apply CSV aggregation rule if folder matches a configured rule."""
        rule = self.csv_rule_engine.get_rule(folder_name)
        if not rule:
            return None
        return self.csv_rule_engine.apply(rule, lines, folder_name)

    def _check_for_duplicates(self, transactions, reference_number, file_data):
        """
        Check for duplicate transactions using the DuplicateChecker component.
        
        Args:
            transactions: List of formatted transaction dictionaries
            reference_number: The reference number (folder name) for the transactions
            file_data: File data containing URL and other metadata
        
        Returns:
            Dictionary containing duplicate information or None if no duplicates found
        """
        if not transactions:
            return None

        try:
            from duplicate_checker import DuplicateChecker
            from database import DatabaseManager

            db = DatabaseManager()
            duplicate_checker = DuplicateChecker(db)

            main_transaction = transactions[0]
            transaction_date = main_transaction['date']
            transaction_amount = float(main_transaction['amount'])

            # Normalize date format to YYYY-MM-DD if needed
            if '/' in transaction_date:
                date_parts = transaction_date.split('/')
                if len(date_parts) == 3:
                    day, month, year = date_parts
                    transaction_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            elif '-' in transaction_date and len(transaction_date.split('-')[0]) == 2:
                date_parts = transaction_date.split('-')
                if len(date_parts) == 3:
                    day, month, year = date_parts
                    transaction_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            duplicates = duplicate_checker.check_for_duplicates(
                reference_number=reference_number,
                transaction_date=transaction_date,
                transaction_amount=transaction_amount
            )

            if duplicates:
                duplicate_info = duplicate_checker.format_duplicate_info(duplicates)
                duplicate_info['new_transaction'] = {
                    'ReferenceNumber': reference_number,
                    'TransactionDate': transaction_date,
                    'TransactionAmount': transaction_amount,
                    'TransactionDescription': main_transaction['description'],
                    'Debet': main_transaction['debet'],
                    'Credit': main_transaction['credit'],
                    'Ref3': file_data['url'],
                    'Ref4': file_data['name']
                }
                return duplicate_info

            return None

        except ImportError as e:
            print(f"Duplicate checker not available: {e}")
            return None
        except Exception as e:
            print(f"Error during duplicate detection: {e}")
            return None

    # --- Decision handling (delegates to pdf_decision_handler) ---

    def handle_duplicate_decision(
        self,
        decision: str,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict:
        """
        Handle user decision regarding duplicate transactions.
        Delegates to pdf_decision_handler module.
        """
        return _handle_duplicate_decision_func(
            decision, duplicate_info, transactions, file_data, user_id, session_id
        )

    def _handle_continue_decision(
        self,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        log_success: bool
    ) -> Dict:
        """Handle the 'Continue' decision for duplicate imports."""
        return _handle_continue_decision_func(
            duplicate_info, transactions, file_data, log_success
        )

    def _handle_cancel_decision(
        self,
        duplicate_info: Dict,
        transactions: List[Dict],
        file_data: Dict,
        file_cleanup_manager,
        log_success: bool
    ) -> Dict:
        """Handle the 'Cancel' decision for duplicate imports."""
        return _handle_cancel_decision_func(
            duplicate_info, transactions, file_data, file_cleanup_manager, log_success
        )
