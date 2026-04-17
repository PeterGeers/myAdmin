"""
ZZPInvoiceService: Core invoice lifecycle management.

Handles invoice CRUD, numbering, line calculations, totals,
send flow, credit notes, copy-last, and time entry invoicing.

Reference: .kiro/specs/zzp-module/design.md §5.3
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from services.field_config_mixin import FieldConfigMixin

logger = logging.getLogger(__name__)


class ZZPInvoiceService(FieldConfigMixin):
    """Invoice lifecycle: create, calculate, number, send, credit, copy."""

    FIELD_CONFIG_KEY = 'invoice_field_config'
    ALWAYS_REQUIRED = ['contact_id', 'invoice_date']

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

    # ── Invoice Numbering (Req 5) ───────────────────────────

    def _generate_invoice_number(self, tenant: str, prefix: str, year: int) -> str:
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
                next_seq = row['last_sequence'] + 1
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
                    'zzp', 'invoice_number_padding', tenant=tenant
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

    def _get_invoice_prefix(self, tenant: str) -> str:
        """Read invoice prefix from parameters, default 'INV'."""
        if self.parameter_service:
            p = self.parameter_service.get_param('zzp', 'invoice_prefix', tenant=tenant)
            if p:
                return p
        return 'INV'

    def _get_credit_note_prefix(self, tenant: str) -> str:
        """Read credit note prefix from parameters, default 'CN'."""
        if self.parameter_service:
            p = self.parameter_service.get_param('zzp', 'credit_note_prefix', tenant=tenant)
            if p:
                return p
        return 'CN'

    # ── Line & Total Calculations (Req 4.3–4.5) ────────────

    def _calculate_line(self, tenant: str, line: dict, invoice_date: date) -> dict:
        """Calculate vat_rate, line_total, and vat_amount for a single line."""
        vat_rate = 0.0
        if self.tax_rate_service:
            rate_info = self.tax_rate_service.get_tax_rate(
                tenant, 'btw', line['vat_code'], invoice_date,
            )
            if rate_info:
                vat_rate = rate_info['rate']

        line_total = round(float(line['quantity']) * float(line['unit_price']), 2)
        vat_amount = round(line_total * vat_rate / 100, 2)

        return {
            **line,
            'vat_rate': vat_rate,
            'line_total': line_total,
            'vat_amount': vat_amount,
        }

    def _save_lines(self, invoice_id: int, lines: list, tenant: str,
                    invoice_date: date) -> list:
        """Calculate and insert all invoice lines, return calculated lines."""
        calculated = []
        for idx, line in enumerate(lines):
            calc = self._calculate_line(tenant, line, invoice_date)
            self.db.execute_query(
                """INSERT INTO invoice_lines
                   (invoice_id, product_id, description, quantity, unit_price,
                    vat_code, vat_rate, vat_amount, line_total, sort_order)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    invoice_id,
                    calc.get('product_id'),
                    calc['description'],
                    calc['quantity'],
                    calc['unit_price'],
                    calc['vat_code'],
                    calc['vat_rate'],
                    calc['vat_amount'],
                    calc['line_total'],
                    calc.get('sort_order', idx),
                ),
                fetch=False, commit=True,
            )
            calculated.append(calc)
        return calculated

    def _update_totals(self, invoice_id: int, lines: list) -> dict:
        """Calculate and persist invoice header totals from lines."""
        subtotal = round(sum(l['line_total'] for l in lines), 2)
        vat_total = round(sum(l['vat_amount'] for l in lines), 2)
        grand_total = round(subtotal + vat_total, 2)

        self.db.execute_query(
            """UPDATE invoices SET subtotal=%s, vat_total=%s, grand_total=%s
               WHERE id=%s""",
            (subtotal, vat_total, grand_total, invoice_id),
            fetch=False, commit=True,
        )

        # Read VAT summary from view
        vat_summary = self.db.execute_query(
            """SELECT vat_code, vat_rate, base_amount, vat_amount
               FROM vw_invoice_vat_summary WHERE invoice_id = %s""",
            (invoice_id,),
        ) or []

        return {
            'subtotal': subtotal,
            'vat_total': vat_total,
            'grand_total': grand_total,
            'vat_summary': vat_summary,
        }

    # ── CRUD (Req 4) ───────────────────────────────────────

    def create_invoice(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a draft invoice with lines."""
        # Validate contact exists
        contact = self.db.execute_query(
            "SELECT id FROM contacts WHERE id = %s AND administration = %s",
            (data['contact_id'], tenant),
        )
        if not contact:
            raise ValueError(f"Contact {data['contact_id']} not found for tenant {tenant}")

        invoice_date_str = data.get('invoice_date', '')
        if not invoice_date_str:
            raise ValueError("invoice_date is required")
        invoice_date = (date.fromisoformat(invoice_date_str)
                        if isinstance(invoice_date_str, str) else invoice_date_str)

        payment_terms = data.get('payment_terms_days', self._default_payment_terms(tenant))
        due_date = invoice_date + timedelta(days=payment_terms)

        prefix = self._get_invoice_prefix(tenant)
        invoice_number = self._generate_invoice_number(tenant, prefix, invoice_date.year)

        currency = data.get('currency', self._default_currency(tenant))
        exchange_rate = data.get('exchange_rate', 1.0) if currency != 'EUR' else 1.0

        revenue_account = data.get('revenue_account')
        if not revenue_account:
            revenue_account = self._get_default_revenue_account(tenant)

        invoice_id = self.db.execute_query(
            """INSERT INTO invoices
               (administration, invoice_number, invoice_type, contact_id,
                invoice_date, due_date, payment_terms_days, currency,
                exchange_rate, revenue_account, status, notes, created_by)
               VALUES (%s,%s,'invoice',%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s)""",
            (
                tenant, invoice_number, data['contact_id'],
                invoice_date, due_date, payment_terms,
                currency, exchange_rate, revenue_account,
                data.get('notes'), created_by,
            ),
            fetch=False, commit=True,
        )

        # Save lines and calculate totals
        lines = data.get('lines', [])
        if lines:
            calculated = self._save_lines(invoice_id, lines, tenant, invoice_date)
            self._update_totals(invoice_id, calculated)

        return self.get_invoice(tenant, invoice_id)

    def update_invoice(self, tenant: str, invoice_id: int, data: dict) -> dict:
        """Update a draft invoice. Sent invoices cannot be modified."""
        existing = self._get_invoice_raw(tenant, invoice_id)
        if not existing:
            raise ValueError(f"Invoice {invoice_id} not found for tenant {tenant}")
        if existing['status'] != 'draft':
            raise ValueError(f"Only draft invoices can be edited (current status: {existing['status']})")

        # Update header fields
        header_fields = ['contact_id', 'invoice_date', 'payment_terms_days', 'currency',
                         'exchange_rate', 'notes', 'revenue_account']
        sets = []
        params = []
        for f in header_fields:
            if f in data:
                sets.append(f"{f} = %s")
                params.append(data[f])

        # Recalculate due_date if invoice_date or payment_terms changed
        inv_date = data.get('invoice_date', existing['invoice_date'])
        if isinstance(inv_date, str) and inv_date:
            inv_date = date.fromisoformat(inv_date)
        elif isinstance(inv_date, str) and not inv_date:
            inv_date = existing['invoice_date']
        terms = data.get('payment_terms_days', existing['payment_terms_days'])
        new_due = inv_date + timedelta(days=terms)
        sets.append("due_date = %s")
        params.append(new_due)

        if sets:
            params.extend([invoice_id, tenant])
            self.db.execute_query(
                f"UPDATE invoices SET {', '.join(sets)} WHERE id = %s AND administration = %s",
                tuple(params), fetch=False, commit=True,
            )

        # Replace lines if provided
        if 'lines' in data:
            self.db.execute_query(
                "DELETE FROM invoice_lines WHERE invoice_id = %s",
                (invoice_id,), fetch=False, commit=True,
            )
            calculated = self._save_lines(invoice_id, data['lines'], tenant, inv_date)
            self._update_totals(invoice_id, calculated)

        return self.get_invoice(tenant, invoice_id)

    def get_invoice(self, tenant: str, invoice_id: int) -> Optional[dict]:
        """Get invoice with lines, VAT summary, and contact info."""
        inv = self._get_invoice_raw(tenant, invoice_id)
        if not inv:
            return None

        # Attach contact summary
        contact = self.db.execute_query(
            "SELECT id, client_id, company_name FROM contacts WHERE id = %s AND administration = %s",
            (inv['contact_id'], tenant),
        )
        inv['contact'] = contact[0] if contact else None

        # Attach lines
        inv['lines'] = self.db.execute_query(
            """SELECT id, product_id, description, quantity, unit_price,
                      vat_code, vat_rate, vat_amount, line_total, sort_order
               FROM invoice_lines WHERE invoice_id = %s ORDER BY sort_order""",
            (invoice_id,),
        ) or []

        # Attach VAT summary
        inv['vat_summary'] = self.db.execute_query(
            """SELECT vat_code, vat_rate, base_amount, vat_amount
               FROM vw_invoice_vat_summary WHERE invoice_id = %s""",
            (invoice_id,),
        ) or []

        return inv

    def list_invoices(self, tenant: str, filters: dict = None) -> list:
        """List invoices with optional filters and pagination."""
        filters = filters or {}
        query = """SELECT i.*, c.client_id, c.company_name
                   FROM invoices i
                   JOIN contacts c ON i.contact_id = c.id
                   WHERE i.administration = %s"""
        params: list = [tenant]

        if filters.get('status'):
            query += " AND i.status = %s"
            params.append(filters['status'])
        if filters.get('contact_id'):
            query += " AND i.contact_id = %s"
            params.append(filters['contact_id'])
        if filters.get('invoice_type'):
            query += " AND i.invoice_type = %s"
            params.append(filters['invoice_type'])
        if filters.get('date_from'):
            query += " AND i.invoice_date >= %s"
            params.append(filters['date_from'])
        if filters.get('date_to'):
            query += " AND i.invoice_date <= %s"
            params.append(filters['date_to'])

        query += " ORDER BY i.invoice_date DESC, i.id DESC"

        limit = filters.get('limit', 50)
        offset = filters.get('offset', 0)
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        rows = self.db.execute_query(query, tuple(params)) or []
        results = []
        for r in rows:
            r = self._format_dates(r)
            # Nest contact fields for frontend consistency with get_invoice
            if 'client_id' in r or 'company_name' in r:
                r['contact'] = {
                    'id': r.get('contact_id'),
                    'client_id': r.pop('client_id', None),
                    'company_name': r.pop('company_name', None),
                }
            results.append(r)
        return results

    # ── Private helpers ─────────────────────────────────────

    def _get_invoice_raw(self, tenant: str, invoice_id: int) -> Optional[dict]:
        """Get raw invoice row without joins."""
        rows = self.db.execute_query(
            "SELECT * FROM invoices WHERE id = %s AND administration = %s",
            (invoice_id, tenant),
        )
        return self._format_dates(rows[0]) if rows else None

    @staticmethod
    def _format_dates(row: dict) -> dict:
        """Convert date/datetime objects to ISO strings for JSON serialization."""
        for key in ('invoice_date', 'due_date', 'sent_at', 'created_at', 'updated_at'):
            val = row.get(key)
            if val is not None and hasattr(val, 'isoformat'):
                row[key] = val.isoformat() if not isinstance(val, str) else val
        return row

    def _default_payment_terms(self, tenant: str) -> int:
        """Return tenant-configured payment terms or 30 days."""
        if self.parameter_service:
            p = self.parameter_service.get_param(
                'zzp', 'default_payment_terms_days', tenant=tenant
            )
            if p is not None:
                return int(p)
        return 30

    def _default_currency(self, tenant: str) -> str:
        """Return tenant-configured default currency or EUR."""
        if self.parameter_service:
            p = self.parameter_service.get_param(
                'zzp', 'default_currency', tenant=tenant
            )
            if p:
                return p
        return 'EUR'

    def _get_default_revenue_account(self, tenant: str) -> Optional[str]:
        """Return tenant-configured default revenue account from zzp.revenue_account parameter."""
        if self.parameter_service:
            p = self.parameter_service.get_param(
                'zzp', 'revenue_account', tenant=tenant
            )
            if p:
                return str(p)
        return None

    # ── Credit Notes (Req 10) ──────────────────────────────

    def create_credit_note(self, tenant: str, original_invoice_id: int,
                           created_by: str) -> dict:
        """Create a credit note linked to an original invoice with negated lines."""
        original = self.get_invoice(tenant, original_invoice_id)
        if not original:
            raise ValueError(f"Invoice {original_invoice_id} not found")
        if original['status'] not in ('sent', 'paid', 'overdue'):
            raise ValueError("Can only credit invoices that have been sent")
        if original.get('invoice_type') == 'credit_note':
            raise ValueError("Cannot credit a credit note")

        invoice_date = date.today()
        cn_prefix = self._get_credit_note_prefix(tenant)
        cn_number = self._generate_invoice_number(tenant, cn_prefix, invoice_date.year)

        payment_terms = original.get('payment_terms_days', 30)
        due_date = invoice_date + timedelta(days=payment_terms)

        # Insert credit note header
        cn_id = self.db.execute_query(
            """INSERT INTO invoices
               (administration, invoice_number, invoice_type, contact_id,
                invoice_date, due_date, payment_terms_days, currency,
                exchange_rate, revenue_account, status, notes, original_invoice_id, created_by)
               VALUES (%s,%s,'credit_note',%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s)""",
            (
                tenant, cn_number, original['contact_id'],
                invoice_date, due_date, payment_terms,
                original.get('currency', 'EUR'),
                original.get('exchange_rate', 1.0),
                original.get('revenue_account'),
                f"Creditnota voor {original['invoice_number']}",
                original_invoice_id, created_by,
            ),
            fetch=False, commit=True,
        )

        # Copy lines with negated amounts
        original_lines = original.get('lines', [])
        negated_lines = []
        for line in original_lines:
            neg = {
                'product_id': line.get('product_id'),
                'description': line['description'],
                'quantity': -abs(float(line['quantity'])),
                'unit_price': float(line['unit_price']),
                'vat_code': line['vat_code'],
                'sort_order': line.get('sort_order', 0),
            }
            negated_lines.append(neg)

        if negated_lines:
            calculated = self._save_lines(cn_id, negated_lines, tenant, invoice_date)
            self._update_totals(cn_id, calculated)

        return self.get_invoice(tenant, cn_id)

    # ── Send Flow (Req 6, 8, 9) ─────────────────────────────

    def send_invoice(self, tenant: str, invoice_id: int, options: dict,
                     output_service=None) -> dict:
        """Send invoice or credit note with strict ordering guarantees.

        Flow: health check → generate PDF → store PDF → book mutaties → send email
        Storage failure = hard stop (invoice stays draft, no mutaties created)
        Email failure = soft failure (invoice booked as sent, user resends manually)

        Reference: .kiro/specs/zzp-module/design-parameter-enhancements.md §14.7
        """
        invoice = self.get_invoice(tenant, invoice_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice['status'] != 'draft':
            raise ValueError("Only draft invoices can be sent")

        is_credit_note = invoice.get('invoice_type') == 'credit_note'

        # Resolve output service
        if not output_service:
            try:
                from services.output_service import OutputService
                output_service = OutputService(self.db)
            except Exception as e:
                raise RuntimeError(f"OutputService unavailable: {e}")

        # 0. Pre-flight storage health check
        try:
            health = output_service.check_health(tenant)
            if not health.get('healthy', False):
                return {
                    'success': False,
                    'error': f"Storage unavailable: {health.get('reason', 'health check failed')}. Invoice not sent.",
                }
        except Exception as e:
            return {
                'success': False,
                'error': f"Storage health check failed: {e}. Invoice not sent.",
            }

        # 1. Generate PDF
        if not self.pdf_generator:
            raise RuntimeError("PDFGeneratorService not configured")
        pdf_bytes = self.pdf_generator.generate_invoice_pdf(tenant, invoice)

        # 2. Store PDF — HARD STOP on failure (no mutaties, stay draft)
        try:
            storage_result = self._store_pdf(
                tenant, invoice, pdf_bytes,
                options.get('output_destination'),
                output_service,
            )
            if not storage_result.get('url'):
                return {
                    'success': False,
                    'error': 'Storage failed — no URL returned. Invoice not sent.',
                }
        except Exception as e:
            logger.error("PDF storage failed for %s: %s", invoice['invoice_number'], e)
            return {
                'success': False,
                'error': f"Storage unavailable — invoice not sent: {e}",
            }

        # 3. Book in FIN (with storage_result containing url + filename)
        if self.booking_helper:
            if is_credit_note:
                original = self.get_invoice(tenant, invoice.get('original_invoice_id'))
                self.booking_helper.book_credit_note(tenant, invoice, original, storage_result)
                self._update_status(tenant, invoice['original_invoice_id'], 'credited')
            else:
                self.booking_helper.book_outgoing_invoice(tenant, invoice, storage_result)

        # 4. Update status to sent (financial records are now complete)
        self._update_status(tenant, invoice_id, 'sent', sent_at=datetime.utcnow())

        # 5. Send email — SOFT FAILURE (invoice already booked and marked sent)
        email_warning = None
        if options.get('send_email', True) and self.email_service:
            try:
                pdf_content = pdf_bytes.getvalue()
                attachments = [{
                    'filename': f"{invoice['invoice_number']}.pdf",
                    'content': pdf_content,
                    'content_type': 'application/pdf',
                }]
                email_result = self.email_service.send_invoice_email(
                    tenant, invoice, attachments,
                )
                if not email_result.get('success'):
                    email_warning = (
                        f"Invoice booked successfully, but email failed: "
                        f"{email_result.get('error')}. Please resend manually."
                    )
                    logger.error("Email failed for %s: %s",
                                 invoice['invoice_number'], email_result.get('error'))
            except Exception as e:
                email_warning = (
                    f"Invoice booked successfully, but email failed: {e}. "
                    f"Please resend manually."
                )
                logger.error("Email exception for %s: %s",
                             invoice['invoice_number'], e)

        result = {'success': True, 'invoice_number': invoice['invoice_number']}
        if email_warning:
            result['warning'] = email_warning
        return result

    def get_invoice_pdf(self, tenant: str, invoice_id: int) -> Optional[dict]:
        """Retrieve stored PDF or regenerate as copy."""
        invoice = self.get_invoice(tenant, invoice_id)
        if not invoice:
            return None

        # Try to find stored PDF via mutaties
        contact = invoice.get('contact', {})
        stored = self.db.execute_query(
            """SELECT Ref3, Ref4 FROM mutaties
               WHERE administration = %s AND Ref2 = %s AND ReferenceNumber = %s
               LIMIT 1""",
            (tenant, invoice['invoice_number'], contact.get('client_id', '')),
        )
        if stored and stored[0].get('Ref3'):
            return {
                'url': stored[0]['Ref3'],
                'filename': stored[0].get('Ref4', f"{invoice['invoice_number']}.pdf"),
            }

        # Regenerate as copy
        if self.pdf_generator:
            pdf_bytes = self.pdf_generator.generate_copy_invoice_pdf(tenant, invoice)
            return {
                'content': pdf_bytes,
                'filename': f"{invoice['invoice_number']}_COPY.pdf",
                'content_type': 'application/pdf',
            }

        return None

    def _store_pdf(self, tenant: str, invoice: dict, pdf_bytes, destination: str,
                   output_service=None) -> dict:
        """Store PDF via OutputService using tenant's configured storage provider.

        If no explicit destination is given, reads storage.invoice_provider
        from tenant parameters and maps it to the OutputService destination:
          google_drive → gdrive
          s3_shared / s3_tenant → s3

        Raises on failure — caller (send_invoice) handles the error.
        """
        filename = f"{invoice['invoice_number']}.pdf"

        # Resolve destination from tenant config if not explicitly provided
        if not destination and self.parameter_service:
            provider = self.parameter_service.get_param(
                'storage', 'invoice_provider', tenant=tenant
            ) or 'google_drive'
            destination = {'google_drive': 'gdrive', 's3_shared': 's3', 's3_tenant': 's3'}.get(
                provider, 'gdrive'
            )
        destination = destination or 'gdrive'

        if not output_service:
            raise RuntimeError("OutputService not available for PDF storage")

        result = output_service.handle_output(
            content=pdf_bytes.getvalue(),
            filename=filename,
            destination=destination,
            administration=tenant,
            content_type='application/pdf',
        )
        url = result.get('url', '')
        logger.info("PDF stored: %s → %s (%s)", filename, url, destination)
        return {'url': url, 'filename': filename}

    def _update_status(self, tenant, invoice_id, status, sent_at=None):
        """Update invoice status and optionally sent_at timestamp."""
        if sent_at:
            self.db.execute_query(
                "UPDATE invoices SET status = %s, sent_at = %s WHERE id = %s AND administration = %s",
                (status, sent_at, invoice_id, tenant),
                fetch=False, commit=True,
            )
        else:
            self.db.execute_query(
                "UPDATE invoices SET status = %s WHERE id = %s AND administration = %s",
                (status, invoice_id, tenant),
                fetch=False, commit=True,
            )

    # ── Overdue Detection (Req 12.3) ────────────────────────

    def mark_overdue(self, tenant: str) -> int:
        """Batch update all sent invoices past due date to overdue.

        Returns count of invoices updated.
        """
        result = self.db.execute_query(
            """UPDATE invoices SET status = 'overdue'
               WHERE administration = %s
                 AND status = 'sent'
                 AND due_date < CURDATE()""",
            (tenant,),
            fetch=False, commit=True,
        )
        count = result if isinstance(result, int) else 0
        if count:
            logger.info("Marked %d invoice(s) as overdue for tenant %s", count, tenant)
        return count

    # ── Invoice from Time Entries (Req 11.5–11.6) ───────────

    def create_invoice_from_time_entries(self, tenant: str, contact_id: int,
                                         entry_ids: list, data: dict,
                                         created_by: str,
                                         time_tracking_service=None) -> dict:
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
            if entry.get('is_billed'):
                raise ValueError(f"Time entry {eid} is already billed")
            if entry['contact_id'] != contact_id:
                raise ValueError(f"Time entry {eid} belongs to a different contact")
            entries.append(entry)

        # Build invoice lines from time entries
        lines = []
        for entry in entries:
            vat_code = 'high'  # default
            if entry.get('product_id'):
                product = self.db.execute_query(
                    "SELECT vat_code FROM products WHERE id = %s AND administration = %s",
                    (entry['product_id'], tenant),
                )
                if product:
                    vat_code = product[0]['vat_code']

            lines.append({
                'product_id': entry.get('product_id'),
                'description': entry.get('description') or f"Uren {entry['entry_date']}",
                'quantity': float(entry['hours']),
                'unit_price': float(entry['hourly_rate']),
                'vat_code': vat_code,
            })

        invoice_data = {
            'contact_id': contact_id,
            'invoice_date': data.get('invoice_date', date.today().isoformat()),
            'payment_terms_days': data.get('payment_terms_days'),
            'currency': data.get('currency'),
            'notes': data.get('notes'),
            'lines': lines,
        }
        # Remove None values
        invoice_data = {k: v for k, v in invoice_data.items() if v is not None}

        invoice = self.create_invoice(tenant, invoice_data, created_by=created_by)

        # Mark entries as billed
        time_tracking_service.mark_as_billed(tenant, entry_ids, invoice['id'])

        return invoice

    # ── Copy Last Invoice / Recurring (Req 13) ──────────────

    def copy_last_invoice(self, tenant: str, contact_id: int,
                          created_by: str) -> dict:
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
        last_lines = self.db.execute_query(
            "SELECT * FROM invoice_lines WHERE invoice_id = %s ORDER BY sort_order",
            (last_invoice['id'],),
        ) or []

        new_date = self._advance_date(tenant, contact_id, last_invoice['invoice_date'])
        payment_terms = last_invoice.get('payment_terms_days', 30)

        lines = [
            {
                'product_id': line.get('product_id'),
                'description': line['description'],
                'quantity': float(line['quantity']),
                'unit_price': float(line['unit_price']),
                'vat_code': line['vat_code'],
                'sort_order': line.get('sort_order', 0),
            }
            for line in last_lines
        ]

        invoice_data = {
            'contact_id': contact_id,
            'invoice_date': new_date.isoformat(),
            'payment_terms_days': payment_terms,
            'currency': last_invoice.get('currency', 'EUR'),
            'revenue_account': last_invoice.get('revenue_account'),
            'notes': last_invoice.get('notes'),
            'lines': lines,
        }
        invoice_data = {k: v for k, v in invoice_data.items() if v is not None}

        new_invoice = self.create_invoice(tenant, invoice_data, created_by=created_by)
        new_invoice['copied_from_invoice_id'] = last_invoice['id']
        return new_invoice

    def _advance_date(self, tenant: str, contact_id: int,
                      last_date) -> date:
        """Calculate next invoice date based on gap between last two invoices.

        If only one invoice exists, defaults to +1 month.
        """
        if isinstance(last_date, str):
            last_date = date.fromisoformat(last_date)

        prev_two = self.db.execute_query(
            """SELECT invoice_date FROM invoices
               WHERE administration = %s AND contact_id = %s
                 AND invoice_type = 'invoice'
               ORDER BY invoice_date DESC LIMIT 2""",
            (tenant, contact_id),
        ) or []

        if len(prev_two) >= 2:
            d1 = prev_two[0]['invoice_date']
            d2 = prev_two[1]['invoice_date']
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
            return last_date.replace(year=year, month=month, day=min(last_date.day, last_day))
