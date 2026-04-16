"""
InvoiceBookingHelper: Creates mutaties entries using double-entry bookkeeping
for outgoing invoices, incoming invoices, and credit notes.

Follows TransactionLogic.save_approved_transactions() pattern.
Shared helper — future modules can import without ZZP route dependency.

Reference: .kiro/specs/zzp-module/design.md §5.4
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class InvoiceBookingHelper:
    """Double-entry booking of invoices into mutaties."""

    def __init__(self, db, transaction_logic, tax_rate_service,
                 parameter_service):
        self.db = db
        self.transaction_logic = transaction_logic
        self.tax_rate_service = tax_rate_service
        self.parameter_service = parameter_service

    # ── Outgoing Invoice (Req 6.3) ──────────────────────────

    def book_outgoing_invoice(self, tenant: str, invoice: dict,
                              storage_result: dict = None) -> List[dict]:
        """Book an outgoing invoice: debit debtor, credit revenue + VAT entries.

        VAT entries: debit revenue account, credit received-BTW ledger account
        (e.g. 2021 for high, 2020 for low — driven by TaxRateService).
        Account 2010 (Betaalde BTW) is only used for incoming invoices.
        """
        contact = invoice.get('contact', {})
        client_id = contact.get('client_id', '')
        inv_number = invoice['invoice_number']
        inv_date = invoice['invoice_date']
        grand_total = float(invoice['grand_total'])

        debtor_acct = self._get_param(tenant, 'debtor_account', '1300')
        revenue_acct = self._get_param(tenant, 'revenue_account', '8001')

        pdf_url = (storage_result or {}).get('url', '')
        pdf_filename = (storage_result or {}).get('filename', '')

        exchange_rate = float(invoice.get('exchange_rate', 1.0))

        transactions = []

        # 1. Main entry: debit debtor, credit revenue for grand total
        transactions.append(self._build_entry(
            tenant=tenant,
            description=f"Factuur {inv_number} {client_id}",
            amount=round(grand_total * exchange_rate, 2),
            debet=debtor_acct,
            credit=revenue_acct,
            reference_number=client_id,
            ref2=inv_number,
            ref3=pdf_url,
            ref4=pdf_filename,
            txn_date=inv_date,
        ))

        # 2. VAT entries per rate bucket
        # Outgoing: debit revenue, credit received-BTW ledger (2021/2020)
        vat_summary = invoice.get('vat_summary', [])
        for vat_line in vat_summary:
            vat_amount = round(float(vat_line['vat_amount']) * exchange_rate, 2)
            if vat_amount == 0:
                continue

            vat_code = vat_line['vat_code']
            vat_rate = vat_line['vat_rate']
            # Get the received-BTW ledger account (e.g. 2021 high, 2020 low)
            received_btw_acct = self._get_vat_ledger_account(
                tenant, vat_code, inv_date, '2021'
            )

            transactions.append(self._build_entry(
                tenant=tenant,
                description=f"Factuur {inv_number} {client_id} BTW {vat_rate:.0f}%",
                amount=vat_amount,
                debet=revenue_acct,
                credit=received_btw_acct,
                reference_number=client_id,
                ref2=inv_number,
                ref3=pdf_url,
                ref4=pdf_filename,
                txn_date=inv_date,
            ))

        return self.transaction_logic.save_approved_transactions(transactions)

    # ── Incoming Invoice (Req 6.4) ──────────────────────────

    def book_incoming_invoice(self, tenant: str, invoice: dict,
                              storage_result: dict = None) -> List[dict]:
        """Book an incoming invoice: debit expense, credit creditor + VAT."""
        contact = invoice.get('contact', {})
        client_id = contact.get('client_id', '')
        inv_number = invoice['invoice_number']
        inv_date = invoice['invoice_date']
        grand_total = float(invoice['grand_total'])
        vat_total = float(invoice.get('vat_total', 0))

        creditor_acct = self._get_param(tenant, 'creditor_account', '1600')
        expense_acct = self._get_param(tenant, 'expense_account', '4000')
        btw_debit_acct = self._get_param(tenant, 'btw_debit_account', '2010')

        pdf_url = (storage_result or {}).get('url', '')
        pdf_filename = (storage_result or {}).get('filename', '')

        exchange_rate = float(invoice.get('exchange_rate', 1.0))

        transactions = []

        # 1. Main entry: debit expense, credit creditor
        transactions.append(self._build_entry(
            tenant=tenant,
            description=f"Inkoopfactuur {inv_number}",
            amount=round(grand_total * exchange_rate, 2),
            debet=expense_acct,
            credit=creditor_acct,
            reference_number=client_id,
            ref2=inv_number,
            ref3=pdf_url,
            ref4=pdf_filename,
            txn_date=inv_date,
        ))

        # 2. Single VAT line for total VAT (no split per rate)
        vat_amount = round(vat_total * exchange_rate, 2)
        if vat_amount != 0:
            transactions.append(self._build_entry(
                tenant=tenant,
                description=f"BTW Voorbelasting {inv_number}",
                amount=vat_amount,
                debet=btw_debit_acct,
                credit=creditor_acct,
                reference_number=client_id,
                ref2=inv_number,
                ref3='',
                ref4='',
                txn_date=inv_date,
            ))

        return self.transaction_logic.save_approved_transactions(transactions)

    # ── Credit Note (Req 10.4) ──────────────────────────────

    def book_credit_note(self, tenant: str, credit_note: dict,
                         original_invoice: dict,
                         storage_result: dict = None) -> List[dict]:
        """Book a credit note: reversal entries offsetting the original booking."""
        contact = credit_note.get('contact', {})
        client_id = contact.get('client_id', '')
        cn_number = credit_note['invoice_number']
        cn_date = credit_note['invoice_date']
        grand_total = abs(float(credit_note['grand_total']))

        debtor_acct = self._get_param(tenant, 'debtor_account', '1300')
        revenue_acct = self._get_param(tenant, 'revenue_account', '8001')
        btw_debit_acct = self._get_param(tenant, 'btw_debit_account', '2010')

        pdf_url = (storage_result or {}).get('url', '')
        pdf_filename = (storage_result or {}).get('filename', '')

        exchange_rate = float(credit_note.get('exchange_rate', 1.0))

        transactions = []

        # 1. Reversal: credit debtor, debit revenue (swapped from outgoing)
        transactions.append(self._build_entry(
            tenant=tenant,
            description=f"Creditnota {cn_number} {client_id}",
            amount=round(grand_total * exchange_rate, 2),
            debet=revenue_acct,
            credit=debtor_acct,
            reference_number=client_id,
            ref2=cn_number,
            ref3=pdf_url,
            ref4=pdf_filename,
            txn_date=cn_date,
        ))

        # 2. VAT reversal entries per rate bucket
        vat_summary = credit_note.get('vat_summary', [])
        for vat_line in vat_summary:
            vat_amount = round(abs(float(vat_line['vat_amount'])) * exchange_rate, 2)
            if vat_amount == 0:
                continue

            vat_code = vat_line['vat_code']
            vat_rate = vat_line['vat_rate']
            credit_acct = self._get_vat_ledger_account(
                tenant, vat_code, cn_date, btw_debit_acct
            )

            # Reversed: credit btw_debit, debit vat ledger
            transactions.append(self._build_entry(
                tenant=tenant,
                description=f"BTW Creditnota {vat_code.capitalize()} {vat_rate}% {cn_number}",
                amount=vat_amount,
                debet=credit_acct,
                credit=btw_debit_acct,
                reference_number=client_id,
                ref2=cn_number,
                ref3='',
                ref4='',
                txn_date=cn_date,
            ))

        return self.transaction_logic.save_approved_transactions(transactions)

    # ── Private helpers ─────────────────────────────────────

    def _build_entry(self, tenant, description, amount, debet, credit,
                     reference_number, ref2, ref3, ref4, txn_date) -> dict:
        return {
            'TransactionNumber': reference_number,
            'TransactionDate': txn_date,
            'TransactionDescription': description,
            'TransactionAmount': amount,
            'Debet': debet,
            'Credit': credit,
            'ReferenceNumber': reference_number,
            'Ref1': '',
            'Ref2': ref2,
            'Ref3': ref3,
            'Ref4': ref4,
            'Administration': tenant,
        }

    def _get_param(self, tenant: str, key: str, default: str) -> str:
        if self.parameter_service:
            val = self.parameter_service.get_param('zzp', key, tenant=tenant)
            if val:
                return str(val)
        return default

    def _get_vat_ledger_account(self, tenant: str, vat_code: str,
                                inv_date, fallback: str) -> str:
        """Get the ledger account for a VAT code from TaxRateService."""
        if self.tax_rate_service:
            from datetime import date as date_type
            ref_date = inv_date if isinstance(inv_date, date_type) else date_type.fromisoformat(str(inv_date))
            rate_info = self.tax_rate_service.get_tax_rate(
                tenant, 'btw', vat_code, ref_date
            )
            if rate_info and rate_info.get('ledger_account'):
                return rate_info['ledger_account']
        return fallback
