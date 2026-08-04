"""
ZZPInvoiceService: Core invoice lifecycle management.

Handles invoice CRUD, numbering, line calculations, and totals.
Delegates delivery (send, PDF, email) to ZZPInvoiceDeliveryHelper,
factory methods (time entries, trips, copy-last, credit notes) to ZZPInvoiceFactoryHelper,
and numbering to ZZPInvoiceNumberingHelper.

Reference: .kiro/specs/zzp-module/design.md §5.3
"""

import logging
from datetime import date, timedelta

from dialect_helpers import dialect
from services.field_config_mixin import FieldConfigMixin
from services.zzp_invoice_delivery import ZZPInvoiceDeliveryHelper
from services.zzp_invoice_factory import ZZPInvoiceFactoryHelper
from services.zzp_invoice_numbering import ZZPInvoiceNumberingHelper

logger = logging.getLogger(__name__)


class ZZPInvoiceService(FieldConfigMixin):
    """Invoice lifecycle: create, calculate, number, send, credit, copy."""

    FIELD_CONFIG_KEY = "invoice_field_config"
    ALWAYS_REQUIRED = ["contact_id", "invoice_date"]  # noqa: RUF012

    def __init__(
        self,
        db,
        tax_rate_service=None,
        parameter_service=None,
        booking_helper=None,
        pdf_generator=None,
        email_service=None,
    ) -> None:
        self.db = db
        self.tax_rate_service = tax_rate_service
        self.parameter_service = parameter_service
        self.booking_helper = booking_helper
        self.pdf_generator = pdf_generator
        self.email_service = email_service
        self._delivery = ZZPInvoiceDeliveryHelper(
            db=db,
            parameter_service=parameter_service,
            booking_helper=booking_helper,
            pdf_generator=pdf_generator,
            email_service=email_service,
        )
        self._factory = ZZPInvoiceFactoryHelper(
            db=db, parameter_service=parameter_service
        )
        self._numbering = ZZPInvoiceNumberingHelper(
            db=db, parameter_service=parameter_service
        )

    # ── Invoice Numbering (delegated to numbering helper) ───

    def _generate_invoice_number(self, tenant: str, prefix: str, year: int) -> str:
        return self._numbering.generate_invoice_number(tenant, prefix, year)

    def _get_invoice_prefix(self, tenant: str) -> str:
        return self._numbering.get_invoice_prefix(tenant)

    def _get_credit_note_prefix(self, tenant: str) -> str:
        return self._numbering.get_credit_note_prefix(tenant)

    # ── Line & Total Calculations (Req 4.3–4.5) ────────────

    def _calculate_line(self, tenant: str, line: dict, invoice_date: date) -> dict:
        """Calculate vat_rate, line_total, and vat_amount for a single line."""
        vat_rate = 0.0
        if self.tax_rate_service:
            rate_info = self.tax_rate_service.get_tax_rate(
                tenant, "btw", line["vat_code"], invoice_date
            )
            if rate_info:
                vat_rate = rate_info["rate"]

        line_total = round(float(line["quantity"]) * float(line["unit_price"]), 2)
        vat_amount = round(line_total * vat_rate / 100, 2)

        return {
            **line,
            "vat_rate": vat_rate,
            "line_total": line_total,
            "vat_amount": vat_amount,
        }

    def _save_lines(
        self, invoice_id: int, lines: list, tenant: str, invoice_date: date
    ) -> list:
        """Calculate and insert all invoice lines, return calculated lines."""
        calculated = []
        for idx, line in enumerate(lines):
            calc = self._calculate_line(tenant, line, invoice_date)
            self.db.execute_query(
                """INSERT INTO invoice_lines
                   (invoice_id, administration, product_id, description, quantity,
                    unit_price, vat_code, vat_rate, vat_amount, line_total, sort_order)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    invoice_id,
                    tenant,
                    calc.get("product_id"),
                    calc["description"],
                    calc["quantity"],
                    calc["unit_price"],
                    calc["vat_code"],
                    calc["vat_rate"],
                    calc["vat_amount"],
                    calc["line_total"],
                    calc.get("sort_order", idx),
                ),
                fetch=False,
                commit=True,
            )
            calculated.append(calc)
        return calculated

    def _update_totals(self, invoice_id: int, lines: list, tenant: str) -> dict:
        """Calculate and persist invoice header totals from lines."""
        subtotal = round(sum(line["line_total"] for line in lines), 2)
        vat_total = round(sum(line["vat_amount"] for line in lines), 2)
        grand_total = round(subtotal + vat_total, 2)

        self.db.execute_query(
            """UPDATE invoices SET subtotal=%s, vat_total=%s, grand_total=%s
               WHERE id=%s""",
            (subtotal, vat_total, grand_total, invoice_id),
            fetch=False,
            commit=True,
        )

        # Read VAT summary from view
        vat_summary = (
            self.db.execute_query(
                """SELECT vat_code, vat_rate, base_amount, vat_amount
               FROM vw_invoice_vat_summary
               WHERE invoice_id = %s AND administration = %s""",
                (invoice_id, tenant),
            )
            or []
        )

        return {
            "subtotal": subtotal,
            "vat_total": vat_total,
            "grand_total": grand_total,
            "vat_summary": vat_summary,
        }

    # ── CRUD (Req 4) ───────────────────────────────────────

    def create_invoice(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a draft invoice with lines."""
        # Validate contact exists
        contact = self.db.execute_query(
            "SELECT id FROM contacts WHERE id = %s AND administration = %s",
            (data["contact_id"], tenant),
        )
        if not contact:
            raise ValueError(
                f"Contact {data['contact_id']} not found for tenant {tenant}"
            )

        invoice_date_str = data.get("invoice_date", "")
        if not invoice_date_str:
            raise ValueError("invoice_date is required")
        invoice_date = (
            date.fromisoformat(invoice_date_str)
            if isinstance(invoice_date_str, str)
            else invoice_date_str
        )

        payment_terms = data.get(
            "payment_terms_days", self._default_payment_terms(tenant)
        )
        due_date = invoice_date + timedelta(days=payment_terms)

        prefix = self._get_invoice_prefix(tenant)
        invoice_number = self._generate_invoice_number(
            tenant, prefix, invoice_date.year
        )

        currency = data.get("currency", self._default_currency(tenant))
        exchange_rate = data.get("exchange_rate", 1.0) if currency != "EUR" else 1.0

        revenue_account = data.get("revenue_account")
        if not revenue_account:
            revenue_account = self._get_default_revenue_account(tenant)

        invoice_id = self.db.execute_query(
            """INSERT INTO invoices
               (administration, invoice_number, invoice_type, contact_id,
                invoice_date, due_date, payment_terms_days, currency,
                exchange_rate, revenue_account, status, notes, created_by)
               VALUES (%s,%s,'invoice',%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s)""",
            (
                tenant,
                invoice_number,
                data["contact_id"],
                invoice_date,
                due_date,
                payment_terms,
                currency,
                exchange_rate,
                revenue_account,
                data.get("notes"),
                created_by,
            ),
            fetch=False,
            commit=True,
        )

        # Save lines and calculate totals
        lines = data.get("lines", [])
        if lines:
            calculated = self._save_lines(invoice_id, lines, tenant, invoice_date)
            self._update_totals(invoice_id, calculated, tenant)

        return self.get_invoice(tenant, invoice_id)

    def update_invoice(self, tenant: str, invoice_id: int, data: dict) -> dict:
        """Update a draft invoice. Sent invoices cannot be modified."""
        existing = self._get_invoice_raw(tenant, invoice_id)
        if not existing:
            raise ValueError(f"Invoice {invoice_id} not found for tenant {tenant}")
        if existing["status"] != "draft":
            raise ValueError(
                f"Only draft invoices can be edited (current status: {existing['status']})"
            )

        # Update header fields
        header_fields = [
            "contact_id",
            "invoice_date",
            "payment_terms_days",
            "currency",
            "exchange_rate",
            "notes",
            "revenue_account",
        ]
        sets = []
        params = []
        for f in header_fields:
            if f in data:
                sets.append(f"{f} = %s")
                params.append(data[f])

        # Recalculate due_date if invoice_date or payment_terms changed
        inv_date = data.get("invoice_date", existing["invoice_date"])
        if isinstance(inv_date, str) and inv_date:
            inv_date = date.fromisoformat(inv_date)
        elif isinstance(inv_date, str) and not inv_date:
            inv_date = existing["invoice_date"]
        terms = data.get("payment_terms_days", existing["payment_terms_days"])
        new_due = inv_date + timedelta(days=terms)
        sets.append("due_date = %s")
        params.append(new_due)

        if sets:
            params.extend([invoice_id, tenant])
            self.db.execute_query(
                f"UPDATE invoices SET {', '.join(sets)} WHERE id = %s AND administration = %s",
                tuple(params),
                fetch=False,
                commit=True,
            )

        # Replace lines if provided
        if "lines" in data:
            self.db.execute_query(
                "DELETE FROM invoice_lines WHERE invoice_id = %s AND administration = %s",
                (invoice_id, tenant),
                fetch=False,
                commit=True,
            )
            calculated = self._save_lines(invoice_id, data["lines"], tenant, inv_date)
            self._update_totals(invoice_id, calculated, tenant)

        return self.get_invoice(tenant, invoice_id)

    def get_invoice(self, tenant: str, invoice_id: int) -> dict | None:
        """Get invoice with lines, VAT summary, and contact info."""
        inv = self._get_invoice_raw(tenant, invoice_id)
        if not inv:
            return None

        # Attach contact summary
        contact = self.db.execute_query(
            "SELECT id, client_id, company_name FROM contacts WHERE id = %s AND administration = %s",
            (inv["contact_id"], tenant),
        )
        inv["contact"] = contact[0] if contact else None

        # Attach lines
        inv["lines"] = (
            self.db.execute_query(
                """SELECT id, product_id, description, quantity, unit_price,
                      vat_code, vat_rate, vat_amount, line_total, sort_order
               FROM invoice_lines
               WHERE invoice_id = %s AND administration = %s
               ORDER BY sort_order""",
                (invoice_id, tenant),
            )
            or []
        )

        # Attach VAT summary
        inv["vat_summary"] = (
            self.db.execute_query(
                """SELECT vat_code, vat_rate, base_amount, vat_amount
               FROM vw_invoice_vat_summary
               WHERE invoice_id = %s AND administration = %s""",
                (invoice_id, tenant),
            )
            or []
        )

        return inv

    def list_invoices(self, tenant: str, filters: dict | None = None) -> list:
        """List invoices with optional filters and pagination."""
        filters = filters or {}
        query = """SELECT i.*, c.client_id, c.company_name
                   FROM invoices i
                   JOIN contacts c ON i.contact_id = c.id
                   WHERE i.administration = %s"""
        params: list = [tenant]

        if filters.get("status"):
            query += " AND i.status = %s"
            params.append(filters["status"])
        if filters.get("contact_id"):
            query += " AND i.contact_id = %s"
            params.append(filters["contact_id"])
        if filters.get("invoice_type"):
            query += " AND i.invoice_type = %s"
            params.append(filters["invoice_type"])
        if filters.get("date_from"):
            query += " AND i.invoice_date >= %s"
            params.append(filters["date_from"])
        if filters.get("date_to"):
            query += " AND i.invoice_date <= %s"
            params.append(filters["date_to"])

        query += " ORDER BY i.invoice_date DESC, i.id DESC"

        limit = filters.get("limit", 50)
        offset = filters.get("offset", 0)
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        rows = self.db.execute_query(query, tuple(params)) or []
        results = []
        for r in rows:
            r = self._format_dates(r)
            # Nest contact fields for frontend consistency with get_invoice
            if "client_id" in r or "company_name" in r:
                r["contact"] = {
                    "id": r.get("contact_id"),
                    "client_id": r.pop("client_id", None),
                    "company_name": r.pop("company_name", None),
                }
            results.append(r)
        return results

    def _get_invoice_raw(self, tenant: str, invoice_id: int) -> dict | None:
        """Get raw invoice row without joins."""
        rows = self.db.execute_query(
            "SELECT * FROM invoices WHERE id = %s AND administration = %s",
            (invoice_id, tenant),
        )
        return self._format_dates(rows[0]) if rows else None

    @staticmethod
    def _format_dates(row: dict) -> dict:
        """Convert date/datetime objects to ISO strings for JSON serialization."""
        for key in ("invoice_date", "due_date", "sent_at", "created_at", "updated_at"):
            val = row.get(key)
            if val is not None and hasattr(val, "isoformat"):
                row[key] = val.isoformat() if not isinstance(val, str) else val
        return row

    def _default_payment_terms(self, tenant: str) -> int:
        """Return tenant-configured payment terms or 30 days."""
        if self.parameter_service:
            p = self.parameter_service.get_param(
                "zzp", "default_payment_terms_days", tenant=tenant
            )
            if p is not None:
                return int(p)
        return 30

    def _default_currency(self, tenant: str) -> str:
        """Return tenant-configured default currency or EUR."""
        if self.parameter_service:
            p = self.parameter_service.get_param(
                "zzp", "default_currency", tenant=tenant
            )
            if p:
                return p
        return "EUR"

    def _get_default_revenue_account(self, tenant: str) -> str | None:
        """Return tenant-configured default revenue account."""
        if self.parameter_service:
            p = self.parameter_service.get_param(
                "zzp", "revenue_account", tenant=tenant
            )
            if p:
                return str(p)
        return None

    # ── Delegated: Delivery (PDF, Email, Send) ────────────────

    def preview_invoice(self, tenant: str, invoice_id: int):
        """Generate a preview PDF for a draft invoice (delegated to delivery helper)."""
        return self._delivery.preview_invoice(tenant, invoice_id, self.get_invoice)

    def get_email_preview(self, tenant: str, invoice_id: int) -> dict:
        """Compose an email preview without sending (delegated to delivery helper)."""
        return self._delivery.get_email_preview(tenant, invoice_id, self.get_invoice)

    def send_invoice(
        self, tenant: str, invoice_id: int, options: dict, output_service=None
    ) -> dict:
        """Send invoice or credit note (delegated to delivery helper)."""
        return self._delivery.send_invoice(
            tenant, invoice_id, options, self.get_invoice, output_service
        )

    def get_invoice_pdf(self, tenant: str, invoice_id: int) -> dict | None:
        """Retrieve stored PDF or regenerate as copy (delegated to delivery helper)."""
        return self._delivery.get_invoice_pdf(tenant, invoice_id, self.get_invoice)

    def _store_pdf(self, tenant, invoice, pdf_bytes, destination, output_service=None):
        """Store PDF via OutputService (delegated to delivery helper)."""
        return self._delivery._store_pdf(
            tenant, invoice, pdf_bytes, destination, output_service
        )

    def _update_status(self, tenant, invoice_id, status, sent_at=None):
        """Update invoice status (delegated to delivery helper)."""
        self._delivery._update_status(tenant, invoice_id, status, sent_at)

    # ── Delegated: Factory (Credit Notes, Time Entries, Trips, Copy) ──

    def create_credit_note(
        self, tenant: str, original_invoice_id: int, created_by: str
    ) -> dict:
        """Create a credit note linked to an original invoice (delegated to factory helper)."""
        return self._factory.create_credit_note(
            tenant,
            original_invoice_id,
            created_by,
            get_invoice_fn=self.get_invoice,
            generate_invoice_number_fn=self._generate_invoice_number,
            get_credit_note_prefix_fn=self._get_credit_note_prefix,
            save_lines_fn=self._save_lines,
            update_totals_fn=self._update_totals,
        )

    def create_invoice_from_time_entries(
        self,
        tenant: str,
        contact_id: int,
        entry_ids: list,
        data: dict,
        created_by: str,
        time_tracking_service=None,
    ) -> dict:
        """Create a draft invoice from selected time entries (delegated to factory helper)."""
        return self._factory.create_invoice_from_time_entries(
            tenant,
            contact_id,
            entry_ids,
            data,
            created_by,
            create_invoice_fn=self.create_invoice,
            time_tracking_service=time_tracking_service,
        )

    def create_invoice_from_trips(
        self,
        tenant: str,
        contact_id: int,
        trip_ids: list,
        km_rate: float,
        data: dict,
        created_by: str,
        trip_service=None,
    ) -> dict:
        """Create a draft invoice from selected trips (delegated to factory helper)."""
        return self._factory.create_invoice_from_trips(
            tenant,
            contact_id,
            trip_ids,
            km_rate,
            data,
            created_by,
            create_invoice_fn=self.create_invoice,
            trip_service=trip_service,
        )

    def copy_last_invoice(self, tenant: str, contact_id: int, created_by: str) -> dict:
        """Create a new draft by copying the most recent invoice (delegated to factory helper)."""
        return self._factory.copy_last_invoice(
            tenant,
            contact_id,
            created_by,
            create_invoice_fn=self.create_invoice,
        )

    def _advance_date(self, tenant: str, contact_id: int, last_date) -> date:
        """Calculate next invoice date (delegated to factory helper)."""
        return self._factory._advance_date(tenant, contact_id, last_date)

    # ── Overdue Detection (Req 12.3) ────────────────────────

    def mark_overdue(self, tenant: str) -> int:
        """Batch update all sent invoices past due date to overdue. Returns count updated."""
        result = self.db.execute_query(
            f"""UPDATE invoices SET status = 'overdue'
               WHERE administration = %s
                 AND status = 'sent'
                 AND due_date < {dialect.current_date()}""",
            (tenant,),
            fetch=False,
            commit=True,
        )
        count = result if isinstance(result, int) else 0
        if count:
            logger.info("Marked %d invoice(s) as overdue for tenant %s", count, tenant)
        return count
