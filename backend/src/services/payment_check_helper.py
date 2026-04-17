"""
PaymentCheckHelper: Matches bank transactions against open invoices.
Uses ReferenceNumber (= contact client_id) for matching.
Reference: design.md 5.5
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)
DEFAULT_TOLERANCE = 0.01


class PaymentCheckHelper:
    """Match bank transactions to open invoices."""

    def __init__(self, db):
        self.db = db

    def run_payment_check(self, tenant: str) -> dict:
        """Run payment matching for all open invoices."""
        open_invoices = self.db.execute_query(
            """SELECT i.id, i.invoice_number, i.grand_total, i.status,
                      i.currency, i.exchange_rate, c.client_id
               FROM invoices i
               JOIN contacts c ON i.contact_id = c.id
               WHERE i.administration = %s
                 AND i.status IN ('sent', 'overdue')
                 AND i.invoice_type = 'invoice'
               ORDER BY i.due_date""",
            (tenant,),
        ) or []

        if not open_invoices:
            return {'success': True, 'matched': 0, 'partial': 0,
                    'unmatched': 0, 'details': []}

        matched = 0
        partial = 0
        unmatched = 0
        details = []

        for inv in open_invoices:
            result = self._match_invoice(tenant, inv)
            details.append(result)
            if result['match_type'] == 'exact':
                matched += 1
            elif result['match_type'] == 'partial':
                partial += 1
            else:
                unmatched += 1

        return {'success': True, 'matched': matched, 'partial': partial,
                'unmatched': unmatched, 'details': details}

    def _match_invoice(self, tenant: str, invoice: dict) -> dict:
        """Try to match a single invoice against bank transactions."""
        client_id = invoice['client_id']
        invoice_total = float(invoice['grand_total'])

        bank_txns = self.db.execute_query(
            """SELECT ID, TransactionDate, TransactionAmount,
                      TransactionDescription
               FROM mutaties
               WHERE administration = %s AND ReferenceNumber = %s
                 AND Credit IN (
                     SELECT Account FROM rekeningschema
                     WHERE administration = %s
                       AND JSON_EXTRACT(parameters, '$.bank_account') = true
                 )
               ORDER BY TransactionDate DESC""",
            (tenant, client_id, tenant),
        ) or []

        if not bank_txns:
            return {'invoice_number': invoice['invoice_number'],
                    'invoice_id': invoice['id'],
                    'match_type': 'none',
                    'message': 'No matching bank transactions found'}

        for txn in bank_txns:
            txn_amount = abs(float(txn['TransactionAmount']))
            match_result = self._match_amount(txn_amount, invoice_total)

            if match_result == 'exact':
                self.db.execute_query(
                    "UPDATE invoices SET status = 'paid' WHERE id = %s AND administration = %s",
                    (invoice['id'], tenant), fetch=False, commit=True)
                return {'invoice_number': invoice['invoice_number'],
                        'invoice_id': invoice['id'], 'match_type': 'exact',
                        'bank_txn_id': txn['ID'], 'bank_amount': txn_amount,
                        'invoice_amount': invoice_total,
                        'message': 'Payment matched'}

            if match_result == 'partial':
                return {'invoice_number': invoice['invoice_number'],
                        'invoice_id': invoice['id'], 'match_type': 'partial',
                        'bank_txn_id': txn['ID'], 'bank_amount': txn_amount,
                        'invoice_amount': invoice_total,
                        'message': 'Partial payment detected'}

        return {'invoice_number': invoice['invoice_number'],
                'invoice_id': invoice['id'], 'match_type': 'none',
                'message': 'No amount match found'}

    @staticmethod
    def _match_amount(bank_amount: float, invoice_total: float,
                      tolerance: float = DEFAULT_TOLERANCE) -> str:
        """Returns 'exact', 'partial', or 'none'."""
        diff = abs(bank_amount - invoice_total)
        if diff <= tolerance:
            return 'exact'
        if 0 < bank_amount < invoice_total:
            return 'partial'
        return 'none'
