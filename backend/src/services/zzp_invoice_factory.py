"""
ZZP Invoice Factory Helper

Handles creation of invoices from external sources:
- Time entries → invoice lines
- Trips (rittenregistratie) → invoice lines
- Copy last invoice (recurring)

Extracted from zzp_invoice_service.py to keep files under 500 lines.

Reference: .kiro/specs/zzp-module/design.md §5.3
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class ZZPInvoiceFactoryHelper:
    """Creates invoices from time entries, trips, and by copying previous invoices."""

    def __init__(self, db, parameter_service=None) -> None:
        self.db = db
        self.parameter_service = parameter_service

    def create_invoice_from_time_entries(
        self,
        tenant: str,
        contact_id: int,
        entry_ids: list,
        data: dict,
        created_by: str,
        create_invoice_fn,
        time_tracking_service=None,
    ) -> dict:
        """Create a draft invoice from selected time entries.

        Maps each time entry to an invoice line:
        product_id, description, quantity=hours, unit_price=hourly_rate, vat_code from product.
        Marks entries as billed after invoice creation.
        """
        if not time_tracking_service:
            raise RuntimeError("TimeTrackingService required")

        entries = []
        for eid in entry_ids:
            entry = time_tracking_service.get_entry(tenant, eid)
            if not entry:
                raise ValueError(f"Time entry {eid} not found")
            if entry.get("is_billed"):
                raise ValueError(f"Time entry {eid} is already billed")
            if entry["contact_id"] != contact_id:
                raise ValueError(f"Time entry {eid} belongs to a different contact")
            entries.append(entry)

        # Build invoice lines from time entries
        lines = []
        for entry in entries:
            vat_code = "high"  # default
            if entry.get("product_id"):
                product = self.db.execute_query(
                    "SELECT vat_code FROM products WHERE id = %s AND administration = %s",
                    (entry["product_id"], tenant),
                )
                if product:
                    vat_code = product[0]["vat_code"]

            lines.append(
                {
                    "product_id": entry.get("product_id"),
                    "description": entry.get("description")
                    or f"Uren {entry['entry_date']}",
                    "quantity": float(entry["hours"]),
                    "unit_price": float(entry["hourly_rate"]),
                    "vat_code": vat_code,
                }
            )

        invoice_data = {
            "contact_id": contact_id,
            "invoice_date": data.get("invoice_date", date.today().isoformat()),
            "payment_terms_days": data.get("payment_terms_days"),
            "currency": data.get("currency"),
            "notes": data.get("notes"),
            "lines": lines,
        }
        # Remove None values
        invoice_data = {k: v for k, v in invoice_data.items() if v is not None}

        invoice = create_invoice_fn(tenant, invoice_data, created_by=created_by)

        # Mark entries as billed
        time_tracking_service.mark_as_billed(tenant, entry_ids, invoice["id"])

        return invoice

    def copy_last_invoice(
        self, tenant: str, contact_id: int, created_by: str, create_invoice_fn
    ) -> dict:
        """Create a new draft by copying the most recent invoice for a contact."""
        last = self.db.execute_query(
            """SELECT * FROM invoices
               WHERE administration = %s AND contact_id = %s
                 AND invoice_type = 'invoice'
               ORDER BY invoice_date DESC LIMIT 1""",
            (tenant, contact_id),
        )
        if not last:
            raise ValueError("No previous invoice found for this contact")

        last_invoice = last[0]
        last_lines = (
            self.db.execute_query(
                "SELECT * FROM invoice_lines WHERE invoice_id = %s AND administration = %s ORDER BY sort_order",
                (last_invoice["id"], tenant),
            )
            or []
        )

        new_date = self._advance_date(tenant, contact_id, last_invoice["invoice_date"])
        payment_terms = last_invoice.get("payment_terms_days", 30)

        lines = [
            {
                "product_id": line.get("product_id"),
                "description": line["description"],
                "quantity": float(line["quantity"]),
                "unit_price": float(line["unit_price"]),
                "vat_code": line["vat_code"],
                "sort_order": line.get("sort_order", 0),
            }
            for line in last_lines
        ]

        invoice_data = {
            "contact_id": contact_id,
            "invoice_date": new_date.isoformat(),
            "payment_terms_days": payment_terms,
            "currency": last_invoice.get("currency", "EUR"),
            "revenue_account": last_invoice.get("revenue_account"),
            "notes": last_invoice.get("notes"),
            "lines": lines,
        }
        invoice_data = {k: v for k, v in invoice_data.items() if v is not None}

        new_invoice = create_invoice_fn(tenant, invoice_data, created_by=created_by)
        new_invoice["copied_from_invoice_id"] = last_invoice["id"]
        return new_invoice

    def create_credit_note(
        self,
        tenant: str,
        original_invoice_id: int,
        created_by: str,
        get_invoice_fn,
        generate_invoice_number_fn,
        get_credit_note_prefix_fn,
        save_lines_fn,
        update_totals_fn,
    ) -> dict:
        """Create a credit note linked to an original invoice with negated lines.

        Args:
            tenant: Tenant identifier.
            original_invoice_id: ID of the invoice to credit.
            created_by: User who initiated the credit note.
            get_invoice_fn: Callable(tenant, invoice_id) -> dict.
            generate_invoice_number_fn: Callable(tenant, prefix, year) -> str.
            get_credit_note_prefix_fn: Callable(tenant) -> str.
            save_lines_fn: Callable(invoice_id, lines, tenant, invoice_date) -> list.
            update_totals_fn: Callable(invoice_id, lines, tenant) -> dict.
        """
        original = get_invoice_fn(tenant, original_invoice_id)
        if not original:
            raise ValueError(f"Invoice {original_invoice_id} not found")
        if original["status"] not in ("sent", "paid", "overdue"):
            raise ValueError("Can only credit invoices that have been sent")
        if original.get("invoice_type") == "credit_note":
            raise ValueError("Cannot credit a credit note")

        invoice_date = date.today()
        cn_prefix = get_credit_note_prefix_fn(tenant)
        cn_number = generate_invoice_number_fn(tenant, cn_prefix, invoice_date.year)

        payment_terms = original.get("payment_terms_days", 30)
        due_date = invoice_date + timedelta(days=payment_terms)

        # Insert credit note header
        cn_id = self.db.execute_query(
            """INSERT INTO invoices
               (administration, invoice_number, invoice_type, contact_id,
                invoice_date, due_date, payment_terms_days, currency,
                exchange_rate, revenue_account, status, notes, original_invoice_id, created_by)
               VALUES (%s,%s,'credit_note',%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s)""",
            (
                tenant,
                cn_number,
                original["contact_id"],
                invoice_date,
                due_date,
                payment_terms,
                original.get("currency", "EUR"),
                original.get("exchange_rate", 1.0),
                original.get("revenue_account"),
                f"Creditnota voor {original['invoice_number']}",
                original_invoice_id,
                created_by,
            ),
            fetch=False,
            commit=True,
        )

        # Copy lines with negated amounts
        original_lines = original.get("lines", [])
        negated_lines = []
        for line in original_lines:
            neg = {
                "product_id": line.get("product_id"),
                "description": line["description"],
                "quantity": -abs(float(line["quantity"])),
                "unit_price": float(line["unit_price"]),
                "vat_code": line["vat_code"],
                "sort_order": line.get("sort_order", 0),
            }
            negated_lines.append(neg)

        if negated_lines:
            calculated = save_lines_fn(cn_id, negated_lines, tenant, invoice_date)
            update_totals_fn(cn_id, calculated, tenant)

        return get_invoice_fn(tenant, cn_id)

    def _advance_date(self, tenant: str, contact_id: int, last_date) -> date:
        """Calculate next invoice date based on gap between last two invoices.

        If only one invoice exists, defaults to +1 month.
        """
        if isinstance(last_date, str):
            last_date = date.fromisoformat(last_date)

        prev_two = (
            self.db.execute_query(
                """SELECT invoice_date FROM invoices
               WHERE administration = %s AND contact_id = %s
                 AND invoice_type = 'invoice'
               ORDER BY invoice_date DESC LIMIT 2""",
                (tenant, contact_id),
            )
            or []
        )

        if len(prev_two) >= 2:
            d1 = prev_two[0]["invoice_date"]
            d2 = prev_two[1]["invoice_date"]
            if isinstance(d1, str):
                d1 = date.fromisoformat(d1)
            if isinstance(d2, str):
                d2 = date.fromisoformat(d2)
            gap = d1 - d2
            return last_date + gap

        # Default: +1 month
        month = last_date.month % 12 + 1
        year = last_date.year + (1 if month == 1 else 0)
        try:
            return last_date.replace(year=year, month=month)
        except ValueError:
            # Handle end-of-month (e.g., Jan 31 → Feb 28)
            import calendar

            last_day = calendar.monthrange(year, month)[1]
            return last_date.replace(
                year=year, month=month, day=min(last_date.day, last_day)
            )
