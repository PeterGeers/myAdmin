"""
PDFGeneratorService: HTML-to-PDF conversion for invoices using weasyprint.

Renders an HTML template with invoice data, injects tenant logo,
and converts to PDF. Falls back to a default template if no
tenant-specific template is configured.

Reference: .kiro/specs/zzp-module/design.md §5.6
"""

import logging
from io import BytesIO
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class PDFGeneratorService:
    """Generate invoice PDFs from HTML templates via weasyprint."""

    def __init__(self, db, template_service=None, parameter_service=None):
        self.db = db
        self.template_service = template_service
        self.parameter_service = parameter_service

    def generate_invoice_pdf(self, tenant: str, invoice: dict) -> BytesIO:
        """Generate a PDF for an invoice or credit note."""
        html = self._render_html(tenant, invoice, is_copy=False)
        return self._html_to_pdf(html)

    def generate_copy_invoice_pdf(self, tenant: str, invoice: dict) -> BytesIO:
        """Generate a PDF marked as COPY."""
        html = self._render_html(tenant, invoice, is_copy=True)
        return self._html_to_pdf(html)

    def _render_html(self, tenant: str, invoice: dict,
                     is_copy: bool = False) -> str:
        """Render the invoice HTML from template + data."""
        template_html = self._load_template(tenant)
        logo_url = self._get_tenant_logo(tenant)
        branding = self._get_branding(tenant)

        contact = invoice.get('contact', {})
        # If contact only has summary fields, try to load full contact
        if contact and not contact.get('street_address'):
            full = self._load_full_contact(tenant, contact.get('id'))
            if full:
                contact = full

        lines = invoice.get('lines', [])
        vat_summary = invoice.get('vat_summary', [])

        def _nl_amount(val) -> str:
            """Format amount in Dutch locale: 1.250,00"""
            n = float(val or 0)
            formatted = f"{n:,.2f}"
            formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
            return formatted

        def _nl_qty(val) -> str:
            """Format quantity: integer if whole, otherwise 2 decimals."""
            n = float(val or 0)
            return str(int(n)) if n == int(n) else f"{n:.2f}".replace('.', ',')

        def _nl_date(val) -> str:
            """Format date as dd-mm-yyyy (Dutch)."""
            s = str(val or '')
            if len(s) >= 10 and s[4] == '-':
                return f"{s[8:10]}-{s[5:7]}-{s[0:4]}"
            return s

        # Build lines HTML
        lines_html = ''
        for line in lines:
            lines_html += (
                f'<tr>'
                f'<td>{line.get("description", "")}</td>'
                f'<td class="right">{_nl_qty(line.get("quantity", 0))}</td>'
                f'<td class="right">&euro; {_nl_amount(line.get("unit_price", 0))}</td>'
                f'<td class="right">{float(line.get("vat_rate", 0)):.0f}%</td>'
                f'<td class="right">&euro; {_nl_amount(line.get("line_total", 0))}</td>'
                f'</tr>'
            )

        # Build VAT summary HTML
        vat_html = ''
        for v in vat_summary:
            vat_html += (
                f'<tr>'
                f'<td>{v.get("vat_code", "")} ({float(v.get("vat_rate", 0)):.0f}%)</td>'
                f'<td class="right">&euro; {_nl_amount(v.get("base_amount", 0))}</td>'
                f'<td class="right">&euro; {_nl_amount(v.get("vat_amount", 0))}</td>'
                f'</tr>'
            )

        logo_tag = f'<img src="{logo_url}" class="logo" />' if logo_url else ''
        copy_watermark = '<div class="watermark">COPY</div>' if is_copy else ''

        replacements = {
            '{{logo}}': logo_tag,
            '{{copy_watermark}}': copy_watermark,
            '{{invoice_number}}': invoice.get('invoice_number', ''),
            '{{invoice_date}}': _nl_date(invoice.get('invoice_date', '')),
            '{{due_date}}': _nl_date(invoice.get('due_date', '')),
            '{{currency}}': invoice.get('currency', 'EUR'),
            '{{payment_terms}}': str(invoice.get('payment_terms_days', 30)),
            '{{notes}}': invoice.get('notes', '') or '',
            # Tenant (sender) branding
            '{{tenant_name}}': branding.get('company_name', ''),
            '{{tenant_address}}': branding.get('company_address', ''),
            '{{tenant_postal_city}}': branding.get('company_postal_city', ''),
            '{{tenant_country}}': branding.get('company_country', ''),
            '{{tenant_vat}}': branding.get('company_vat', ''),
            '{{tenant_coc}}': branding.get('company_coc', ''),
            '{{tenant_email}}': branding.get('contact_email', ''),
            '{{tenant_iban}}': branding.get('company_iban', ''),
            '{{tenant_phone}}': branding.get('company_phone', ''),
            # Client (recipient) contact
            '{{company_name}}': contact.get('company_name', ''),
            '{{client_id}}': contact.get('client_id', ''),
            '{{contact_person}}': contact.get('contact_person', '') or '',
            '{{street_address}}': contact.get('street_address', '') or '',
            '{{postal_code}}': contact.get('postal_code', '') or '',
            '{{city}}': contact.get('city', '') or '',
            '{{country}}': contact.get('country', '') or '',
            '{{client_vat}}': contact.get('vat_number', '') or '',
            # Line items and totals
            '{{lines}}': lines_html,
            '{{vat_summary}}': vat_html,
            '{{subtotal}}': _nl_amount(invoice.get('subtotal', 0)),
            '{{vat_total}}': _nl_amount(invoice.get('vat_total', 0)),
            '{{grand_total}}': _nl_amount(invoice.get('grand_total', 0)),
        }

        html = template_html
        for key, value in replacements.items():
            html = html.replace(key, value)

        return html

    def _get_branding(self, tenant: str) -> dict:
        """Load tenant branding from zzp_branding namespace."""
        branding = {}
        if not self.parameter_service:
            return branding
        keys = ['company_name', 'company_address', 'company_postal_city',
                'company_country', 'company_vat', 'company_coc',
                'company_iban', 'company_phone', 'contact_email']
        for key in keys:
            val = self.parameter_service.get_param('zzp_branding', key, tenant=tenant)
            if val:
                branding[key] = val

        # If company_iban not set via branding, try rekeningschema
        if not branding.get('company_iban'):
            iban = self._get_invoice_iban(tenant)
            if iban:
                branding['company_iban'] = iban

        return branding

    def _get_invoice_iban(self, tenant: str) -> Optional[str]:
        """Query rekeningschema for the IBAN of the account flagged as invoice_bank_account.

        Returns the IBAN string or None if no account is flagged or has no IBAN.
        """
        if not self.db:
            return None
        try:
            rows = self.db.execute_query(
                """SELECT JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.iban')) AS iban
                   FROM rekeningschema
                   WHERE administration = %s
                     AND JSON_EXTRACT(parameters, '$.invoice_bank_account') = true
                   LIMIT 1""",
                (tenant,),
            )
            if rows and isinstance(rows, list) and len(rows) > 0:
                iban = rows[0].get('iban') if isinstance(rows[0], dict) else None
                if iban and isinstance(iban, str) and iban != 'null':
                    return iban
            return None
        except Exception as e:
            logger.warning("Could not fetch invoice IBAN from rekeningschema: %s", e)
            return None

    def _load_full_contact(self, tenant: str, contact_id) -> Optional[dict]:
        """Load full contact record for PDF rendering."""
        if not contact_id or not self.db:
            return None
        try:
            rows = self.db.execute_query(
                "SELECT * FROM contacts WHERE id = %s AND administration = %s",
                (contact_id, tenant),
            )
            return rows[0] if rows else None
        except Exception:
            return None

    def _html_to_pdf(self, html: str) -> BytesIO:
        """Convert HTML string to PDF bytes via weasyprint."""
        try:
            import weasyprint
        except ImportError:
            logger.error("weasyprint not installed — cannot generate PDF")
            raise RuntimeError(
                "PDF generation requires weasyprint. "
                "Install with: pip install weasyprint>=60.0"
            )

        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        output = BytesIO(pdf_bytes)
        output.seek(0)
        return output

    def _load_template(self, tenant: str) -> str:
        """Load HTML template: tenant-specific via TemplateService, or default."""
        if self.template_service:
            try:
                meta = self.template_service.get_template_metadata(
                    tenant, 'zzp_invoice'
                )
                if meta and meta.get('local_path'):
                    import os
                    path = meta['local_path']
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            return f.read()
            except Exception as e:
                logger.warning("Failed to load tenant template, using default: %s", e)

        return self._default_template()

    def _get_tenant_logo(self, tenant: str) -> Optional[str]:
        """Get logo as base64 data URI from tenant's branding config.

        Reads company_logo_file_id from branding parameters (same as STR invoices),
        fetches the image from Google, and returns a data URI for reliable PDF embedding.
        Returns None if no logo is configured.
        """
        logo_file_id = None

        # Try zzp_branding parameter first
        if self.parameter_service:
            logo_file_id = self.parameter_service.get_param(
                'zzp_branding', 'company_logo_file_id', tenant=tenant
            )

        if not logo_file_id:
            return None

        # Fetch logo and convert to base64 data URI (same approach as STR invoices)
        try:
            import requests as http_requests
            import base64
            logo_url = f'https://lh3.googleusercontent.com/d/{logo_file_id}=w600'
            resp = http_requests.get(logo_url, timeout=10)
            if resp.status_code == 200:
                content_type = resp.headers.get('Content-Type', 'image/png')
                b64 = base64.b64encode(resp.content).decode('utf-8')
                return f'data:{content_type};base64,{b64}'
            else:
                logger.warning("Logo fetch returned %s, using URL fallback", resp.status_code)
                return logo_url
        except Exception as e:
            logger.warning("Could not fetch logo as base64: %s, using URL fallback", e)
            return f'https://lh3.googleusercontent.com/d/{logo_file_id}=w600'

    @staticmethod
    def _default_template() -> str:
        """Return the built-in default invoice HTML template."""
        import os
        template_path = os.path.join(
            os.path.dirname(__file__), '..', 'templates', 'zzp_invoice_default.html'
        )
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()

        # Inline fallback if file doesn't exist yet
        return _INLINE_DEFAULT_TEMPLATE


_INLINE_DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  @page { size: A4; margin: 2cm; }
  body { font-family: Arial, sans-serif; font-size: 10pt; color: #333; margin: 0; }
  .logo { max-height: 70px; margin-bottom: 5px; }
  .watermark { position: fixed; top: 40%; left: 20%; font-size: 80pt;
    color: rgba(200,200,200,0.3); transform: rotate(-30deg); z-index: -1; }
  .header { display: flex; justify-content: space-between; align-items: flex-start;
    margin-bottom: 20px; }
  .header h2 { margin: 0; color: #333; font-size: 16pt; }
  .addresses { display: flex; justify-content: space-between; margin-bottom: 25px; }
  .sender, .recipient { width: 48%; }
  .sender { font-size: 8pt; color: #666; }
  .sender h3 { font-size: 10pt; font-weight: bold; color: #333; margin: 0 0 4px 0; }
  .recipient { text-align: right; }
  .recipient h3 { font-size: 11pt; font-weight: bold; color: #333; margin: 0 0 4px 0; }
  .recipient .label { font-size: 8pt; color: #999; margin-bottom: 3px; }
  .sender p:empty, .recipient p:empty { display: none; margin: 0; padding: 0; }
  .sender br:only-child, .recipient br:only-child { display: none; }
  .meta-table { width: 100%; margin-bottom: 20px; }
  .meta-table td { border: none; padding: 3px 8px; font-size: 9pt; }
  .meta-table .label { color: #888; width: 120px; }
  table.lines { width: 100%; border-collapse: collapse; margin-top: 10px; }
  table.lines th { background: #f5f5f5; padding: 6px 8px; text-align: left;
    border-bottom: 2px solid #ddd; font-size: 9pt; color: #555; }
  table.lines td { padding: 5px 8px; border-bottom: 1px solid #eee; }
  .right { text-align: right; }
  table.totals { width: 50%; margin-left: auto; margin-top: 15px; }
  table.totals td { padding: 3px 8px; }
  table.totals .grand td { font-weight: bold; border-top: 2px solid #333;
    padding-top: 6px; font-size: 11pt; }
  .payment-info { margin-top: 25px; padding: 12px; background: #f8f8f8;
    border: 1px solid #e0e0e0; border-radius: 4px; font-size: 9pt; }
  .payment-info strong { font-size: 10pt; }
  .notes { margin-top: 15px; font-size: 9pt; color: #555; }
  .footer { margin-top: 30px; padding-top: 10px; border-top: 1px solid #ddd;
    font-size: 7pt; color: #999; text-align: center; }
</style></head><body>
{{copy_watermark}}
<div class="header">
  <div>{{logo}}</div>
  <div><h2>{{invoice_number}}</h2></div>
</div>
<div class="addresses">
  <div class="sender">
    {{logo}}
    <h3>{{tenant_name}}</h3>
    <p>{{tenant_address}}<br/>{{tenant_postal_city}}<br/>{{tenant_country}}</p>
    <p>BTW: {{tenant_vat}}<br/>KvK: {{tenant_coc}}<br/>IBAN: {{tenant_iban}}<br/>Tel: {{tenant_phone}}<br/>Email: {{tenant_email}}</p>
  </div>
  <div class="recipient">
    <div class="label">Factuur aan:</div>
    <h3>{{company_name}}</h3>
    <p>{{contact_person}}<br/>{{street_address}}<br/>{{postal_code}} {{city}}<br/>{{country}}</p>
    <p>BTW: {{client_vat}}</p>
  </div>
</div>
<table class="meta-table"><tr>
  <td class="label">Factuurdatum:</td><td>{{invoice_date}}</td>
  <td class="label">Vervaldatum:</td><td>{{due_date}}</td>
</tr><tr>
  <td class="label">Betalingstermijn:</td><td>{{payment_terms}} dagen</td>
  <td class="label">Valuta:</td><td>{{currency}}</td>
</tr></table>
<table class="lines">
<thead><tr>
  <th>Omschrijving</th>
  <th class="right">Aantal</th>
  <th class="right">Prijs</th>
  <th class="right">BTW</th>
  <th class="right">Totaal</th>
</tr></thead>
<tbody>{{lines}}</tbody>
</table>
<table class="totals">
<tr><td>Subtotaal</td><td class="right">&euro; {{subtotal}}</td></tr>
{{vat_summary}}
<tr class="grand"><td>Totaal</td><td class="right">&euro; {{grand_total}}</td></tr>
</table>
<div class="payment-info">
<strong>Betalingsgegevens</strong><br/>
Referentie: {{client_id}}<br/>
Factuurnummer: {{invoice_number}}
</div>
<div class="notes">{{notes}}</div>
<div class="footer">
  {{tenant_name}} &bull; {{tenant_address}}, {{tenant_postal_city}} &bull;
  BTW {{tenant_vat}} &bull; KvK {{tenant_coc}}
</div>
</body></html>"""
