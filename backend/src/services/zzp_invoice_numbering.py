"""
ZZP Invoice Numbering Helper

Handles invoice number generation with database-level row locking,
prefix resolution, and sequence management.

Extracted from zzp_invoice_service.py to keep files under 500 lines.

Reference: .kiro/specs/zzp-module/design.md §5.3 (Req 5)
"""

import logging

logger = logging.getLogger(__name__)


class ZZPInvoiceNumberingHelper:
    """Generates unique invoice/credit-note numbers using DB row locking."""

    def __init__(self, db, parameter_service=None) -> None:
        self.db = db
        self.parameter_service = parameter_service

    def generate_invoice_number(self, tenant: str, prefix: str, year: int) -> str:
        """Generate next invoice number with database-level row locking.

        Uses SELECT ... FOR UPDATE on invoice_number_sequences to prevent
        concurrent duplicate numbers for the same tenant/prefix/year.
        """
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("START TRANSACTION")
            cursor.execute(
                """SELECT last_sequence FROM invoice_number_sequences
                   WHERE administration = %s AND prefix = %s AND year = %s
                   FOR UPDATE""",
                (tenant, prefix, year),
            )
            row = cursor.fetchone()

            if row:
                next_seq = row["last_sequence"] + 1
                cursor.execute(
                    """UPDATE invoice_number_sequences SET last_sequence = %s
                       WHERE administration = %s AND prefix = %s AND year = %s""",
                    (next_seq, tenant, prefix, year),
                )
            else:
                next_seq = 1
                cursor.execute(
                    """INSERT INTO invoice_number_sequences
                       (administration, prefix, year, last_sequence)
                       VALUES (%s, %s, %s, %s)""",
                    (tenant, prefix, year, next_seq),
                )

            conn.commit()

            padding = 4
            if self.parameter_service:
                p = self.parameter_service.get_param(
                    "zzp", "invoice_number_padding", tenant=tenant
                )
                if p is not None:
                    padding = int(p)

            return f"{prefix}-{year}-{str(next_seq).zfill(padding)}"
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def get_invoice_prefix(self, tenant: str) -> str:
        """Read invoice prefix from parameters, default 'INV'."""
        if self.parameter_service:
            p = self.parameter_service.get_param("zzp", "invoice_prefix", tenant=tenant)
            if p:
                return p
        return "INV"

    def get_credit_note_prefix(self, tenant: str) -> str:
        """Read credit note prefix from parameters, default 'CN'."""
        if self.parameter_service:
            p = self.parameter_service.get_param(
                "zzp", "credit_note_prefix", tenant=tenant
            )
            if p:
                return p
        return "CN"
