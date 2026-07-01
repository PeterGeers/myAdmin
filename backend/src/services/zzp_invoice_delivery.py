"""
ZZP Invoice Delivery Helper

Handles the send/delivery flow for ZZP invoices:
- Sending invoices (PDF generation → storage → booking → email)
- PDF retrieval and storage
- Email preview composition
- Status transitions

Extracted from zzp_invoice_service.py to keep files under 500 lines.

Reference: .kiro/specs/zzp-module/design-parameter-enhancements.md §14.7
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ZZPInvoiceDeliveryHelper:
    """Handles invoice delivery: send flow, PDF, email, status updates."""

    def __init__(
        self,
        db,
        parameter_service=None,
        booking_helper=None,
        pdf_generator=None,
        email_service=None,
    ) -> None:
        self.db = db
        self.parameter_service = parameter_service
        self.booking_helper = booking_helper
        self.pdf_generator = pdf_generator
        self.email_service = email_service

    def send_invoice(
        self,
        tenant: str,
        invoice_id: int,
        options: dict,
        get_invoice_fn,
        output_service=None,
    ) -> dict:
        """Send invoice or credit note with strict ordering guarantees.

        Flow: health check → generate PDF → store PDF → book mutaties → send email
        Storage failure = hard stop (invoice stays draft, no mutaties created)
        Email failure = soft failure (invoice booked as sent, user resends manually)

        Args:
            tenant: Tenant identifier
            invoice_id: Invoice ID to send
            options: Send options (output_destination, send_email)
            get_invoice_fn: Callable to retrieve invoice by (tenant, invoice_id)
            output_service: Optional OutputService instance
        """
        invoice = get_invoice_fn(tenant, invoice_id)
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice["status"] != "draft":
            raise ValueError("Only draft invoices can be sent")

        is_credit_note = invoice.get("invoice_type") == "credit_note"

        # Resolve output service
        if not output_service:
            try:
                from services.output_service import OutputService

                output_service = OutputService(self.db)
            except Exception as e:
                raise RuntimeError(f"OutputService unavailable: {e}")

        # Resolve output destination before health check
        destination = options.get("output_destination")
        if not destination and self.parameter_service:
            provider = (
                self.parameter_service.get_param(
                    "storage", "invoice_provider", tenant=tenant
                )
                or "s3_shared"
            )
            destination = {
                "google_drive": "gdrive",
                "s3_shared": "s3",
                "s3_tenant": "s3",
            }.get(provider, "s3")
        destination = destination or "s3"

        # 0. Pre-flight storage health check
        try:
            health = output_service.check_health(destination, tenant)
            if not health.get("healthy", False):
                return {
                    "success": False,
                    "error": f"Storage unavailable: {health.get('reason', 'health check failed')}. Invoice not sent.",
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Storage health check failed: {e}. Invoice not sent.",
            }

        # 1. Generate PDF
        if not self.pdf_generator:
            raise RuntimeError("PDFGeneratorService not configured")
        pdf_bytes = self.pdf_generator.generate_invoice_pdf(tenant, invoice)

        # 2. Store PDF — HARD STOP on failure (no mutaties, stay draft)
        try:
            storage_result = self._store_pdf(
                tenant,
                invoice,
                pdf_bytes,
                destination,
                output_service,
            )
            if not storage_result.get("url"):
                return {
                    "success": False,
                    "error": "Storage failed — no URL returned. Invoice not sent.",
                }
        except Exception as e:
            logger.error("PDF storage failed for %s: %s", invoice["invoice_number"], e)
            return {
                "success": False,
                "error": f"Storage unavailable — invoice not sent: {e}",
            }

        # 3. Book in FIN (with storage_result containing url + filename)
        if self.booking_helper:
            if is_credit_note:
                original = get_invoice_fn(tenant, invoice.get("original_invoice_id"))
                self.booking_helper.book_credit_note(
                    tenant, invoice, original, storage_result
                )
                self._update_status(tenant, invoice["original_invoice_id"], "credited")
            else:
                self.booking_helper.book_outgoing_invoice(
                    tenant, invoice, storage_result
                )

        # 4. Update status to sent (financial records are now complete)
        self._update_status(tenant, invoice_id, "sent", sent_at=datetime.utcnow())

        # 5. Send email — SOFT FAILURE (invoice already booked and marked sent)
        email_warning = None
        if options.get("send_email", True) and self.email_service:
            try:
                pdf_content = pdf_bytes.getvalue()
                attachments = [
                    {
                        "filename": f"{invoice['invoice_number']}.pdf",
                        "content": pdf_content,
                        "content_type": "application/pdf",
                    }
                ]
                email_result = self.email_service.send_invoice_email(
                    tenant,
                    invoice,
                    attachments,
                )
                if not email_result.get("success"):
                    email_warning = (
                        f"Invoice booked successfully, but email failed: "
                        f"{email_result.get('error')}. Please resend manually."
                    )
                    logger.error(
                        "Email failed for %s: %s",
                        invoice["invoice_number"],
                        email_result.get("error"),
                    )
            except Exception as e:
                email_warning = (
                    f"Invoice booked successfully, but email failed: {e}. "
                    f"Please resend manually."
                )
                logger.error("Email exception for %s: %s", invoice["invoice_number"], e)

        result = {"success": True, "invoice_number": invoice["invoice_number"]}
        if email_warning:
            result["warning"] = email_warning
        return result

    def get_invoice_pdf(
        self, tenant: str, invoice_id: int, get_invoice_fn
    ) -> Optional[dict]:
        """Retrieve stored PDF or regenerate as copy."""
        invoice = get_invoice_fn(tenant, invoice_id)
        if not invoice:
            return None

        # Try to find stored PDF via mutaties
        contact = invoice.get("contact", {})
        stored = self.db.execute_query(
            """SELECT Ref3, Ref4 FROM mutaties
               WHERE administration = %s AND Ref2 = %s AND ReferenceNumber = %s
               LIMIT 1""",
            (tenant, invoice["invoice_number"], contact.get("client_id", "")),
        )
        if stored and stored[0].get("Ref3"):
            return {
                "url": stored[0]["Ref3"],
                "filename": stored[0].get("Ref4", f"{invoice['invoice_number']}.pdf"),
            }

        # Regenerate as copy
        if self.pdf_generator:
            pdf_bytes = self.pdf_generator.generate_copy_invoice_pdf(tenant, invoice)
            return {
                "content": pdf_bytes,
                "filename": f"{invoice['invoice_number']}_COPY.pdf",
                "content_type": "application/pdf",
            }

        return None

    def get_email_preview(self, tenant: str, invoice_id: int, get_invoice_fn) -> dict:
        """Compose an email preview without sending.

        Returns:
            dict with subject, html_body, recipient, bcc, attachment_filename

        Raises:
            ValueError: If invoice not found, not draft, or contact has no email.
        """
        invoice = get_invoice_fn(tenant, invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        if invoice["status"] != "draft":
            raise ValueError("Only draft invoices can be previewed")

        if not self.email_service:
            raise RuntimeError("InvoiceEmailService not configured")

        return self.email_service.compose_email_preview(tenant, invoice)

    def _store_pdf(
        self,
        tenant: str,
        invoice: dict,
        pdf_bytes,
        destination: str,
        output_service=None,
    ) -> dict:
        """Store PDF via OutputService using tenant's configured storage provider.

        Raises on failure — caller (send_invoice) handles the error.
        """
        filename = f"{invoice['invoice_number']}.pdf"

        # Resolve destination from tenant config if not explicitly provided
        if not destination and self.parameter_service:
            provider = (
                self.parameter_service.get_param(
                    "storage", "invoice_provider", tenant=tenant
                )
                or "s3_shared"
            )
            destination = {
                "google_drive": "gdrive",
                "s3_shared": "s3",
                "s3_tenant": "s3",
            }.get(provider, "s3")
        destination = destination or "s3"

        if not output_service:
            raise RuntimeError("OutputService not available for PDF storage")

        result = output_service.handle_output(
            content=pdf_bytes.getvalue(),
            filename=filename,
            destination=destination,
            administration=tenant,
            content_type="application/pdf",
        )
        url = result.get("url", "")
        logger.info("PDF stored: %s → %s (%s)", filename, url, destination)
        return {"url": url, "filename": filename}

    def _update_status(self, tenant, invoice_id, status, sent_at=None):
        """Update invoice status and optionally sent_at timestamp."""
        if sent_at:
            self.db.execute_query(
                "UPDATE invoices SET status = %s, sent_at = %s WHERE id = %s AND administration = %s",
                (status, sent_at, invoice_id, tenant),
                fetch=False,
                commit=True,
            )
        else:
            self.db.execute_query(
                "UPDATE invoices SET status = %s WHERE id = %s AND administration = %s",
                (status, invoice_id, tenant),
                fetch=False,
                commit=True,
            )
