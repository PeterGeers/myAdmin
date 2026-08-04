"""
Shared constants for tenant admin template routes.

Extracted to avoid circular imports between tenant_admin_templates.py
and tenant_admin_template_ai_routes.py.
"""

# Canonical list of valid template types used across all template endpoints.
VALID_TEMPLATE_TYPES = [
    "str_invoice_nl",
    "str_invoice_en",
    "btw_aangifte",
    "aangifte_ib",
    "toeristenbelasting",
    "financial_report",
    "zzp_invoice",
]

# Mapping from VALID_TEMPLATE_TYPES keys to TemplateService._LOCAL_DEFAULTS keys.
TEMPLATE_TYPE_TO_LOCAL_KEY = {
    "str_invoice_nl": "str_invoice_nl",
    "str_invoice_en": "str_invoice_en",
    "btw_aangifte": "btw_aangifte_html",
    "aangifte_ib": "aangifte_ib_html_report",
    "toeristenbelasting": "toeristenbelasting_html",
    "financial_report": "financial_report_xlsx",
    "zzp_invoice": "zzp_invoice",
}
