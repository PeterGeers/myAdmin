"""
InvoiceEmailService: Sends invoice and reminder emails with PDF attachments
via SESEmailService.send_email_with_attachments().

Resolves recipient from ContactService (invoice email → primary → first).
Uses configurable subject/body templates from ParameterService.
Supports locale-aware email composition for the ZZP invoice send flow.

Reference: .kiro/specs/zzp-module/design.md §5.7
Reference: .kiro/specs/zzp-invoice-pdf-preview/design.md §5
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from babel.numbers import format_currency
from babel.dates import format_date as babel_format_date

from services.logo_resolver import resolve_tenant_logo

logger = logging.getLogger(__name__)

# Reuse the same locale map as PDFGeneratorService for consistency
COUNTRY_LOCALE_MAP = {
    'NL': 'nl_NL', 'Nederland': 'nl_NL', 'Netherlands': 'nl_NL',
    'DE': 'de_DE', 'Duitsland': 'de_DE', 'Germany': 'de_DE',
    'US': 'en_US', 'Verenigde Staten': 'en_US', 'United States': 'en_US',
    'GB': 'en_GB', 'Verenigd Koninkrijk': 'en_GB', 'United Kingdom': 'en_GB',
    'FR': 'fr_FR', 'Frankrijk': 'fr_FR', 'France': 'fr_FR',
    'BE': 'nl_BE', 'Belgie': 'nl_BE', 'Belgium': 'nl_BE',
}
DEFAULT_LOCALE = 'nl_NL'


class InvoiceEmailService:
    """Send invoice and reminder emails with attachments.

    Also provides locale-aware email composition for the ZZP invoice
    preview/send flow (compose_email_preview).
    """

    # Fallback sender used when tenant email is not verified
    FALLBACK_SENDER_NAME = 'myAdmin'
    FALLBACK_SENDER_EMAIL = 'support@jabaki.nl'

    def __init__(self, ses_email_service, contact_service,
                 parameter_service=None, email_verification_service=None):
        self.ses = ses_email_service
        self.contact_service = contact_service
        self.parameter_service = parameter_service
        self.email_verification_service = email_verification_service

    # ── Public: Send Methods ────────────────────────────────

    # SES error codes that indicate a verified email is no longer valid
    _VERIFICATION_EXPIRED_ERRORS = ('MessageRejected', 'MailFromDomainNotVerified')

    def send_invoice_email(self, tenant: str, invoice: dict,
                           attachments: List[dict],
                           sent_by: str = None) -> dict:
        """Send invoice email with PDF attachment(s).

        If the send fails with a verification-related SES error
        (MessageRejected or MailFromDomainNotVerified), retries with
        the fallback sender and marks the tenant's verification as expired.

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

        # Resolve sender: use verified tenant email or fallback
        sender_info = self._resolve_sender(tenant)

        result = self.ses.send_email_with_attachments(
            to_email=recipient,
            subject=subject,
            html_body=html_body,
            attachments=attachments,
            bcc=bcc,
            reply_to=sender_info['reply_to'],
            from_name=sender_info['from_name'],
            source_email=sender_info['source_email'],
            email_type='invoice',
            administration=tenant,
            sent_by=sent_by,
        )

        # Error recovery: retry with fallback if verification-related error
        if not result.get('success') and sender_info.get('source_email'):
            result = self._handle_send_error_with_fallback(
                result, tenant, sender_info['source_email'],
                to_email=recipient,
                subject=subject,
                html_body=html_body,
                attachments=attachments,
                bcc=bcc,
                email_type='invoice',
                sent_by=sent_by,
            )

        return result

    def send_reminder_email(self, tenant: str, invoice: dict,
                            sent_by: str = None) -> dict:
        """Send payment reminder for an overdue invoice (no attachment).

        If the send fails with a verification-related SES error
        (MessageRejected or MailFromDomainNotVerified), retries with
        the fallback sender and marks the tenant's verification as expired.
        """
        contact = invoice.get('contact', {})
        contact_id = contact.get('id')

        recipient = self.contact_service.get_invoice_email(tenant, contact_id)
        if not recipient:
            return {'success': False, 'error': 'No email address found for contact'}

        subject = f"Betalingsherinnering {invoice.get('invoice_number', '')}"
        html_body = self._build_body(tenant, invoice, template_type='reminder')
        bcc = self._get_bcc(tenant)

        # Resolve sender: use verified tenant email or fallback
        sender_info = self._resolve_sender(tenant)

        result = self.ses.send_email_with_attachments(
            to_email=recipient,
            subject=subject,
            html_body=html_body,
            attachments=[],
            bcc=bcc,
            reply_to=sender_info['reply_to'],
            from_name=sender_info['from_name'],
            source_email=sender_info['source_email'],
            email_type='reminder',
            administration=tenant,
            sent_by=sent_by,
        )

        # Error recovery: retry with fallback if verification-related error
        if not result.get('success') and sender_info.get('source_email'):
            result = self._handle_send_error_with_fallback(
                result, tenant, sender_info['source_email'],
                to_email=recipient,
                subject=subject,
                html_body=html_body,
                attachments=[],
                bcc=bcc,
                email_type='reminder',
                sent_by=sent_by,
            )

        return result

    # ── Public: Locale-Aware Email Composition ──────────────

    def compose_email_preview(self, tenant: str, invoice: dict) -> dict:
        """Build email subject, body, recipient, BCC without sending.

        Orchestrates locale resolution, subject/body building, recipient
        lookup, BCC resolution, and attachment filename generation.

        Args:
            tenant: Administration identifier
            invoice: Full invoice dict (with contact, lines, etc.)

        Returns:
            dict with 'subject', 'html_body', 'recipient', 'bcc',
            'attachment_filename'

        Raises:
            ValueError: If contact has no email address.
        """
        contact = invoice.get('contact', {})
        contact_id = contact.get('id')

        # Resolve recipient email (invoice → primary → any)
        recipient = self.contact_service.get_invoice_email(tenant, contact_id)
        if not recipient:
            raise ValueError("Contact email address is missing")

        # Resolve locale from contact's country
        locale = self._resolve_locale(contact)

        # Build locale-aware subject and body
        subject = self._build_locale_subject(tenant, invoice, locale)
        html_body = self._build_locale_body(tenant, invoice, locale)

        # Resolve BCC (tenant admin email)
        bcc = self._resolve_tenant_admin_email(tenant)

        # Attachment filename: invoice_number.pdf (NOT the preview version)
        invoice_number = invoice.get('invoice_number', '')
        attachment_filename = f"{invoice_number}.pdf"

        return {
            'subject': subject,
            'html_body': html_body,
            'recipient': recipient,
            'bcc': bcc,
            'attachment_filename': attachment_filename,
        }

    # ── Locale-Aware Helpers ────────────────────────────────

    def _resolve_locale(self, contact: dict) -> str:
        """Resolve Babel locale from contact's country. Default: nl_NL.

        Uses the same COUNTRY_LOCALE_MAP as PDFGeneratorService for
        consistency across PDF and email generation.
        """
        country = (contact.get('country') or '').strip()
        if not country:
            return DEFAULT_LOCALE
        return (COUNTRY_LOCALE_MAP.get(country)
                or COUNTRY_LOCALE_MAP.get(country.upper())
                or COUNTRY_LOCALE_MAP.get(country.title())
                or DEFAULT_LOCALE)

    def _build_locale_subject(self, tenant: str, invoice: dict,
                              locale: str) -> str:
        """Build locale-aware subject line.

        NL (nl_NL): "Factuur {invoice_number} van {tenant_company_name}"
        EN/other:   "Invoice {invoice_number} from {tenant_company_name}"
        """
        invoice_number = invoice.get('invoice_number', '')
        tenant_company = self._get_tenant_company_name(tenant)

        if locale == 'nl_NL':
            return f"Factuur {invoice_number} van {tenant_company}"
        else:
            return f"Invoice {invoice_number} from {tenant_company}"

    def _build_locale_body(self, tenant: str, invoice: dict,
                           locale: str) -> str:
        """Build locale-aware HTML email body with branded signature.

        Contains: greeting (by company_name or contact_person),
        invoice statement, invoice number, total with currency,
        due date, and branded signature block.
        """
        contact = invoice.get('contact', {})
        invoice_number = invoice.get('invoice_number', '')
        currency = invoice.get('currency', 'EUR')
        grand_total = invoice.get('grand_total', 0)
        due_date = invoice.get('due_date', '')

        # Greeting: prefer company_name, fall back to contact_person
        addressee = (contact.get('company_name') or '').strip()
        if not addressee:
            addressee = (contact.get('contact_person') or '').strip()

        # Format amount with locale-appropriate currency symbol
        formatted_total = self._format_amount(grand_total, currency, locale)

        # Format due date according to locale
        formatted_due_date = self._format_date(due_date, locale)

        if locale == 'nl_NL':
            body = self._build_nl_body(
                addressee, invoice_number, formatted_total,
                formatted_due_date
            )
        else:
            body = self._build_en_body(
                addressee, invoice_number, formatted_total,
                formatted_due_date
            )

        # Append branded signature block (graceful degradation: empty string
        # if ParameterService is unavailable)
        signature = self._build_signature_block(tenant, locale)
        if signature:
            body += signature

        return body

    def _build_nl_body(self, addressee: str, invoice_number: str,
                       formatted_total: str, due_date: str) -> str:
        """Build Dutch HTML email body (without closing greeting — handled by signature block)."""
        return (
            f'<p>Geachte {addressee},</p>'
            f'<p>Bijgaand ontvangt u factuur <strong>{invoice_number}</strong> '
            f'met een totaalbedrag van <strong>{formatted_total}</strong>.</p>'
            f'<p>De vervaldatum van deze factuur is '
            f'<strong>{due_date}</strong>.</p>'
        )

    def _build_en_body(self, addressee: str, invoice_number: str,
                       formatted_total: str, due_date: str) -> str:
        """Build English HTML email body (without closing greeting — handled by signature block)."""
        return (
            f'<p>Dear {addressee},</p>'
            f'<p>Please find attached invoice <strong>{invoice_number}</strong> '
            f'for a total amount of <strong>{formatted_total}</strong>.</p>'
            f'<p>The due date for this invoice is '
            f'<strong>{due_date}</strong>.</p>'
        )

    def _resolve_tenant_admin_email(self, tenant: str) -> str:
        """Resolve the tenant administrator's email address for BCC.

        Looks up the tenant profile (zzp_branding namespace) for the
        contact_email parameter. Falls back to invoice_email_bcc parameter.
        Returns the admin email address string, or empty string if not found.
        """
        if not self.parameter_service:
            return ''

        # Primary: zzp_branding contact_email
        admin_email = self.parameter_service.get_param(
            'zzp_branding', 'contact_email', tenant=tenant
        )
        if admin_email and isinstance(admin_email, str):
            return admin_email

        # Fallback: invoice_email_bcc parameter
        bcc = self.parameter_service.get_param(
            'zzp', 'invoice_email_bcc', tenant=tenant
        )
        if bcc:
            return bcc if isinstance(bcc, str) else (bcc[0] if bcc else '')

        return ''

    def _get_tenant_company_name(self, tenant: str) -> str:
        """Get the tenant's company name from branding parameters."""
        if not self.parameter_service:
            return tenant
        company = self.parameter_service.get_param(
            'zzp_branding', 'company_name', tenant=tenant
        )
        return company if company else tenant

    def _format_amount(self, val, currency_code: str, locale: str) -> str:
        """Format currency amount using locale conventions."""
        try:
            n = float(val or 0)
            return format_currency(n, currency_code, locale=locale)
        except Exception:
            return f"{currency_code} {val}"

    def _format_date(self, val, locale: str) -> str:
        """Format date according to locale conventions."""
        s = str(val or '')
        try:
            if isinstance(val, date):
                d = val
            elif len(s) >= 10 and s[4] == '-':
                d = date.fromisoformat(s[:10])
            else:
                return s
            return babel_format_date(d, format='long', locale=locale)
        except Exception:
            return s

    # ── Legacy Helpers (existing send/reminder flow) ────────

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
        """Build HTML email body. Simple default, overridable via params.

        Appends branded signature block after the body content.
        """
        contact = invoice.get('contact', {})
        inv_number = invoice.get('invoice_number', '')

        if template_type == 'reminder':
            body = (
                f"<p>Geachte {contact.get('company_name', '')},</p>"
                f"<p>Wij willen u vriendelijk herinneren aan de openstaande factuur "
                f"<strong>{inv_number}</strong> met een bedrag van "
                f"&euro; {invoice.get('grand_total', 0):.2f}, "
                f"vervaldatum {invoice.get('due_date', '')}.</p>"
                f"<p>Wij verzoeken u het bedrag zo spoedig mogelijk over te maken "
                f"onder vermelding van referentie <strong>{contact.get('client_id', '')}</strong>.</p>"
            )
        else:
            body = (
                f"<p>Geachte {contact.get('company_name', '')},</p>"
                f"<p>Bijgaand ontvangt u factuur <strong>{inv_number}</strong> "
                f"met een bedrag van &euro; {invoice.get('grand_total', 0):.2f}.</p>"
                f"<p>Gelieve het bedrag binnen {invoice.get('payment_terms_days', 30)} dagen "
                f"over te maken onder vermelding van referentie "
                f"<strong>{contact.get('client_id', '')}</strong>.</p>"
            )

        # Append branded signature block (graceful degradation: empty string
        # if ParameterService is unavailable)
        signature = self._build_signature_block(tenant, 'nl_NL')
        if signature:
            body += signature

        return body

    def _get_bcc(self, tenant: str) -> List[str]:
        if self.parameter_service:
            bcc = self.parameter_service.get_param(
                'zzp', 'invoice_email_bcc', tenant=tenant
            )
            if bcc:
                return [bcc] if isinstance(bcc, str) else bcc
        return []

    def _get_bcc_email(self, tenant: str) -> Optional[str]:
        """Get the tenant's admin/contact email for Reply-To header."""
        if self.parameter_service:
            # Try branding contact email first
            email = self.parameter_service.get_param(
                'zzp_branding', 'contact_email', tenant=tenant
            )
            if email:
                return email
            # Fall back to BCC email
            bcc = self.parameter_service.get_param(
                'zzp', 'invoice_email_bcc', tenant=tenant
            )
            if bcc:
                return bcc if isinstance(bcc, str) else bcc[0]
        return None

    # ── Sender Resolution ───────────────────────────────────

    def _resolve_sender(self, tenant: str) -> dict:
        """Resolve the email sender based on tenant verification status.

        Calls EmailVerificationService.get_verified_sender() to determine
        whether to use the tenant's verified email or the fallback sender.

        Args:
            tenant: Administration identifier.

        Returns:
            dict with 'from_name', 'source_email', 'reply_to':
            - If verified: tenant email as source, company name as display name,
              no explicit reply_to (defaults to sender)
            - If not verified: fallback sender, tenant email as reply_to
        """
        if not self.email_verification_service:
            # No verification service available — use fallback behavior
            tenant_email = self._get_bcc_email(tenant)
            tenant_company = self._get_tenant_company_name(tenant)
            return {
                'from_name': tenant_company,
                'source_email': None,  # Uses SES default (support@jabaki.nl)
                'reply_to': tenant_email,
            }

        sender_info = self.email_verification_service.get_verified_sender(tenant)

        if sender_info.get('verified'):
            # Tenant email is verified — use it as the SES Source
            return {
                'from_name': sender_info.get('company_name') or tenant,
                'source_email': sender_info['email'],
                'reply_to': None,  # Reply goes to the verified sender email
            }
        else:
            # Not verified — use fallback sender with Reply-To tenant email
            tenant_email = self._get_bcc_email(tenant)
            return {
                'from_name': self.FALLBACK_SENDER_NAME,
                'source_email': None,  # Uses SES default (support@jabaki.nl)
                'reply_to': tenant_email,
            }

    # ── Error Recovery ──────────────────────────────────────

    def _handle_send_error_with_fallback(
        self, result: dict, tenant: str, verified_email: str,
        to_email: str, subject: str, html_body: str,
        attachments: List[dict], bcc: List[str],
        email_type: str, sent_by: Optional[str] = None,
    ) -> dict:
        """Handle SES send errors by retrying with fallback sender.

        When a send from a verified tenant email fails with MessageRejected
        or MailFromDomainNotVerified, this method:
        1. Retries the send using the fallback sender
        2. Calls mark_expired() to update the verification status
        3. Logs a warning with the tenant identifier and email

        Args:
            result: The failed send result dict (with 'error' key).
            tenant: Administration identifier.
            verified_email: The tenant's verified email that failed.
            to_email: Recipient email address.
            subject: Email subject.
            html_body: HTML email body.
            attachments: List of attachment dicts.
            bcc: BCC addresses.
            email_type: Type for logging ('invoice' or 'reminder').
            sent_by: User who triggered the send.

        Returns:
            The retry result if a verification error was detected,
            or the original result if the error is not verification-related.
        """
        error_str = result.get('error', '')

        # Check if the error is a verification-related SES error
        is_verification_error = any(
            err_code in error_str
            for err_code in self._VERIFICATION_EXPIRED_ERRORS
        )

        if not is_verification_error:
            return result

        # Log warning with tenant identifier and email
        logger.warning(
            f"SES send failed for verified email '{verified_email}' "
            f"(tenant: {tenant}): {error_str}. "
            f"Retrying with fallback sender."
        )

        # Mark the verification as expired
        if self.email_verification_service:
            self.email_verification_service.mark_expired(tenant, verified_email)

        # Retry with fallback sender
        tenant_email = self._get_bcc_email(tenant)
        retry_result = self.ses.send_email_with_attachments(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            attachments=attachments,
            bcc=bcc,
            reply_to=tenant_email,
            from_name=self.FALLBACK_SENDER_NAME,
            source_email=None,  # Uses SES default (support@jabaki.nl)
            email_type=email_type,
            administration=tenant,
            sent_by=sent_by,
        )

        return retry_result

    # ── Signature Builder ───────────────────────────────────

    def _build_signature_block(self, tenant: str, locale: str) -> str:
        """Build branded HTML signature block with logo.

        Retrieves branding parameters (company_name, contact_email) and
        the tenant logo, then assembles a locale-aware HTML signature.

        Data sources:
        - zzp_branding.company_name → company display name
        - zzp_branding.contact_email → contact email in signature
        - Logo via resolve_tenant_logo(tenant, 'zzp_branding', parameter_service)

        Args:
            tenant: Administration identifier.
            locale: Babel locale string (e.g. 'nl_NL', 'en_US').

        Returns:
            HTML string to append after the email body, or empty string
            if ParameterService is unavailable.
        """
        if not self.parameter_service:
            return ''

        # Retrieve branding parameters
        try:
            company_name = self.parameter_service.get_param(
                'zzp_branding', 'company_name', tenant=tenant
            )
        except Exception:
            # ParameterService unavailable — skip signature entirely
            return ''

        # Fall back to tenant identifier if company_name is missing
        if not company_name:
            company_name = tenant

        try:
            contact_email = self.parameter_service.get_param(
                'zzp_branding', 'contact_email', tenant=tenant
            )
        except Exception:
            contact_email = None

        # Resolve logo (returns base64 data URI or None)
        logo_data_uri = None
        try:
            logo_data_uri = resolve_tenant_logo(
                tenant, 'zzp_branding', self.parameter_service
            )
        except Exception:
            # Logo fetch failed — render without logo
            logo_data_uri = None

        # Locale-aware greeting
        if locale == 'nl_NL':
            greeting = 'Met vriendelijke groet,'
        else:
            greeting = 'Kind regards,'

        # Build the HTML signature
        # Horizontal rule separator
        html = (
            '<hr style="border: none; border-top: 1px solid #e0e0e0; '
            'margin: 24px 0 16px 0;" />'
        )

        html += (
            '<table cellpadding="0" cellspacing="0" '
            'style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">'
            '<tr>'
        )

        # Logo column (only rendered when logo is available)
        if logo_data_uri:
            html += (
                '<td style="padding-right: 16px; vertical-align: top;">'
                f'<img src="{logo_data_uri}" alt="Company Logo" '
                'style="max-width: 80px; max-height: 80px; border-radius: 4px;" />'
                '</td>'
            )

        # Text column
        html += '<td style="vertical-align: top;">'
        html += (
            f'<p style="margin: 0 0 4px 0; font-weight: bold;">'
            f'{greeting}</p>'
        )
        html += (
            f'<p style="margin: 0 0 4px 0; font-weight: bold; font-size: 15px;">'
            f'{company_name}</p>'
        )

        # Contact email line (omitted if not configured)
        if contact_email:
            html += (
                f'<p style="margin: 0; color: #555;">'
                f'<a href="mailto:{contact_email}" '
                f'style="color: #0066cc; text-decoration: none;">'
                f'{contact_email}</a></p>'
            )

        html += '</td></tr></table>'

        return html
