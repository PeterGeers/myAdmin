"""
InvoiceEmailService: Sends invoice and reminder emails with PDF attachments
via SESEmailService.send_email_with_attachments().

Resolves recipient from ContactService (invoice email → primary → first).
Uses configurable subject/body templates from ParameterService.

Reference: .kiro/specs/zzp-module/design.md §5.7
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class InvoiceEmailService:
    """Send invoice and reminder emails with attachments."""

    def __init__(self, ses_email_service, contact_service,
                 parameter_service=None):
        self.ses = ses_email_service
        self.contact_service = contact_service
        self.parameter_service = parameter_service

    def send_invoice_email(self, tenant: str, invoice: dict,
                           attachments: List[dict],
                           sent_by: str = None) -> dict:
        """Send invoice email with PDF attachment(s).

        Args:
            tenant: Administration identifier
            invoice: Full invoice dict (with contact, lines, etc.)
            attachments: List of {'filename', 'content' (bytes), 'content_type'}
            sent_by: User who triggered the send

        Returns:
            dict with 'success' and 'message_id' or 'error'
        """
        contact = invoice.get('contact', {})
        contact_id = contact.get('id')

        recipient = self.contact_service.get_invoice_email(tenant, contact_id)
        if not recipient:
            return {'success': False, 'error': 'No email address found for contact'}

        subject = self._build_subject(tenant, invoice)
        html_body = self._build_body(tenant, invoice, template_type='invoice')
        bcc = self._get_bcc(tenant)

        result = self.ses.send_email_with_attachments(
            to_email=recipient,
            subject=subject,
            html_body=html_body,
            attachments=attachments,
            bcc=bcc,
            email_type='invoice',
            administration=tenant,
            sent_by=sent_by,
        )
        return result

    def send_reminder_email(self, tenant: str, invoice: dict,
                            sent_by: str = None) -> dict:
        """Send payment reminder for an overdue invoice (no attachment)."""
        contact = invoice.get('contact', {})
        contact_id = contact.get('id')

        recipient = self.contact_service.get_invoice_email(tenant, contact_id)
        if not recipient:
            return {'success': False, 'error': 'No email address found for contact'}

        subject = f"Betalingsherinnering {invoice.get('invoice_number', '')}"
        html_body = self._build_body(tenant, invoice, template_type='reminder')
        bcc = self._get_bcc(tenant)

        result = self.ses.send_email_with_attachments(
            to_email=recipient,
            subject=subject,
            html_body=html_body,
            attachments=[],
            bcc=bcc,
            email_type='reminder',
            administration=tenant,
            sent_by=sent_by,
        )
        return result

    # ── Private helpers ─────────────────────────────────────

    def _build_subject(self, tenant: str, invoice: dict) -> str:
        template = 'Factuur {invoice_number} - {company_name}'
        if self.parameter_service:
            t = self.parameter_service.get_param(
                'zzp', 'email_subject_template', tenant=tenant
            )
            if t:
                template = t

        contact = invoice.get('contact', {})
        return template.format(
            invoice_number=invoice.get('invoice_number', ''),
            company_name=contact.get('company_name', ''),
        )

    def _build_body(self, tenant: str, invoice: dict,
                    template_type: str) -> str:
        """Build HTML email body. Simple default, overridable via params."""
        contact = invoice.get('contact', {})
        inv_number = invoice.get('invoice_number', '')

        if template_type == 'reminder':
            return (
                f"<p>Geachte {contact.get('company_name', '')},</p>"
                f"<p>Wij willen u vriendelijk herinneren aan de openstaande factuur "
                f"<strong>{inv_number}</strong> met een bedrag van "
                f"&euro; {invoice.get('grand_total', 0):.2f}, "
                f"vervaldatum {invoice.get('due_date', '')}.</p>"
                f"<p>Wij verzoeken u het bedrag zo spoedig mogelijk over te maken "
                f"onder vermelding van referentie <strong>{contact.get('client_id', '')}</strong>.</p>"
                f"<p>Met vriendelijke groet</p>"
            )

        return (
            f"<p>Geachte {contact.get('company_name', '')},</p>"
            f"<p>Bijgaand ontvangt u factuur <strong>{inv_number}</strong> "
            f"met een bedrag van &euro; {invoice.get('grand_total', 0):.2f}.</p>"
            f"<p>Gelieve het bedrag binnen {invoice.get('payment_terms_days', 30)} dagen "
            f"over te maken onder vermelding van referentie "
            f"<strong>{contact.get('client_id', '')}</strong>.</p>"
            f"<p>Met vriendelijke groet</p>"
        )

    def _get_bcc(self, tenant: str) -> List[str]:
        if self.parameter_service:
            bcc = self.parameter_service.get_param(
                'zzp', 'invoice_email_bcc', tenant=tenant
            )
            if bcc:
                return [bcc] if isinstance(bcc, str) else bcc
        return []
