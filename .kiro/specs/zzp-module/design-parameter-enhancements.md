# Parameter Enhancement Design (Reqs 16-22)

This document covers the design additions for requirements 16 through 22, which enhance the parameter system, invoice booking, PDF generation, and send flow.

> Parent document: [design.md](./design.md) Section 14

### 14.1 Parameter Table Column Filtering (Req 16)

**Goal:** Replace the namespace dropdown in `ParameterManagement.tsx` with a `FilterPanel` using `SearchFilterConfig` filters, following the generic filter framework from `frontend/src/components/filters/`.

#### Approach: Use Existing Generic Filter Framework

The project already has a reusable filter system (`GenericFilter`, `FilterPanel`, `SearchFilterConfig`) documented in `frontend/src/components/filters/README.md`. Per the steering rules in `.kiro/steering/ui-patterns.md`:

- Filter bar sits **between page header and table** — never inline in the table
- Use `FilterPanel` with `SearchFilterConfig` type for text search filters
- Consistent with all other list views in the application

#### Frontend Changes — `ParameterManagement.tsx`

**Remove:** The `nsFilter` state and the `<Select placeholder="All namespaces">` dropdown.

**Add:** `FilterPanel` with 5 search filters between the header HStack and the Table:

```typescript
import { FilterPanel } from '../../components/filters/FilterPanel';
import { SearchFilterConfig } from '../../components/filters/types';

// Filter state
const [filters, setFilters] = useState({
  namespace: '', key: '', value: '', value_type: '', scope_origin: ''
});

// Build search filter configs
const searchFilters: SearchFilterConfig[] = [
  { type: 'search', label: t('tenantAdmin.parameters.namespace'), value: filters.namespace, onChange: (v) => setFilters(prev => ({ ...prev, namespace: v })), placeholder: 'Filter...', size: 'sm' },
  { type: 'search', label: t('tenantAdmin.parameters.key'), value: filters.key, onChange: (v) => setFilters(prev => ({ ...prev, key: v })), placeholder: 'Filter...', size: 'sm' },
  { type: 'search', label: t('tenantAdmin.parameters.value'), value: filters.value, onChange: (v) => setFilters(prev => ({ ...prev, value: v })), placeholder: 'Filter...', size: 'sm' },
  { type: 'search', label: t('tenantAdmin.parameters.valueType'), value: filters.value_type, onChange: (v) => setFilters(prev => ({ ...prev, value_type: v })), placeholder: 'Filter...', size: 'sm' },
  { type: 'search', label: t('tenantAdmin.parameters.scope'), value: filters.scope_origin, onChange: (v) => setFilters(prev => ({ ...prev, scope_origin: v })), placeholder: 'Filter...', size: 'sm' },
];

// In JSX — between header and table:
<FilterPanel filters={searchFilters} layout="horizontal" size="sm" spacing={2} />
```

**Filter logic:** Client-side, case-insensitive substring matching with AND across all active filters:

```typescript
const filteredParams = allParams.filter((p) => {
  const pValue = p.is_secret
    ? "********"
    : typeof p.value === "object"
      ? JSON.stringify(p.value)
      : String(p.value ?? "");
  return (
    (!filters.namespace ||
      p.namespace.toLowerCase().includes(filters.namespace.toLowerCase())) &&
    (!filters.key || p.key.toLowerCase().includes(filters.key.toLowerCase())) &&
    (!filters.value ||
      pValue.toLowerCase().includes(filters.value.toLowerCase())) &&
    (!filters.value_type ||
      p.value_type.toLowerCase().includes(filters.value_type.toLowerCase())) &&
    (!filters.scope_origin ||
      (p.scope_origin || "")
        .toLowerCase()
        .includes(filters.scope_origin.toLowerCase()))
  );
});
```

**API change:** The `load()` function fetches all parameters (no `nsFilter` param) since filtering is now client-side.

**Data flow:**

```
User types in FilterPanel search input → filters state updates →
filteredParams recomputed → table re-renders with matching rows
```

### 14.2 ZZP Invoice Ledger Parameter (Req 17)

**Goal:** Add `zzp_invoice_ledger` to `ledger_parameters.json` so tenant admins can flag revenue accounts for ZZP invoicing.

#### Registry Change — `backend/src/config/ledger_parameters.json`

Add new entry after the existing entries:

```json
{
  "key": "zzp_invoice_ledger",
  "type": "boolean",
  "label_en": "ZZP Invoice Ledger",
  "label_nl": "ZZP Factuur Grootboek",
  "description_en": "Account available as revenue ledger for ZZP invoices",
  "description_nl": "Rekening beschikbaar als omzetrekening voor ZZP facturen",
  "module": "ZZP"
}
```

This follows the exact same structure as `bank_account` and `asset_account`. The Account Modal already renders toggles from this registry — no frontend changes needed for the toggle itself.

#### New API Endpoint

| Method | Endpoint                            | Permission | Description                                 |
| ------ | ----------------------------------- | ---------- | ------------------------------------------- |
| GET    | `/api/zzp/accounts/invoice-ledgers` | `zzp_read` | List accounts flagged as ZZP invoice ledger |

**Route handler** in `zzp_routes.py`:

```python
@zzp_bp.route('/api/zzp/accounts/invoice-ledgers', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
def get_invoice_ledger_accounts(user_email, user_roles, tenant, user_tenants):
    try:
        rows = db.execute_query(
            """SELECT nummer, naam, parameters
               FROM rekeningschema
               WHERE administration = %s
                 AND JSON_EXTRACT(parameters, '$.zzp_invoice_ledger') = true
               ORDER BY nummer""",
            (tenant,),
        )
        accounts = [{'account_code': r['nummer'], 'account_name': r['naam']} for r in (rows or [])]

        # Fallback: if no flagged accounts, include the default revenue account
        if not accounts:
            default_acct = parameter_service.get_param('zzp', 'revenue_account', tenant=tenant) or '8001'
            fallback = db.execute_query(
                "SELECT nummer, naam FROM rekeningschema WHERE administration = %s AND nummer = %s",
                (tenant, default_acct),
            )
            if fallback:
                accounts = [{'account_code': fallback[0]['nummer'], 'account_name': fallback[0]['naam']}]

        return jsonify({'success': True, 'data': accounts})
    except Exception as e:
        logger.error("Get invoice ledger accounts error: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500
```

**Response:**

```json
{
  "success": true,
  "data": [
    { "account_code": "8001", "account_name": "Omzet dienstverlening" },
    { "account_code": "8002", "account_name": "Omzet producten" },
    { "account_code": "8010", "account_name": "Omzet consultancy" }
  ]
}
```

### 14.3 Invoice Revenue Account Selection (Req 18)

**Goal:** Allow users to select a revenue account per invoice, stored on the invoice record, used by the booking helper.

#### Database Change — `invoices` table

Add column:

```sql
ALTER TABLE invoices ADD COLUMN revenue_account VARCHAR(10) DEFAULT NULL
  AFTER exchange_rate;
```

The `revenue_account` stores the selected account code (e.g., `'8001'`, `'8010'`). `NULL` means use the tenant's default `zzp.revenue_account` parameter.

#### Frontend Changes — `InvoiceDetailModal.tsx`

Add a `<Select>` dropdown for revenue account in the invoice creation/edit form (only for draft invoices):

```typescript
// Fetch available invoice ledger accounts
const [ledgerAccounts, setLedgerAccounts] = useState<{account_code: string; account_name: string}[]>([]);

useEffect(() => {
  const fetchLedgers = async () => {
    const res = await apiClient.get('/api/zzp/accounts/invoice-ledgers');
    if (res.data.success) setLedgerAccounts(res.data.data);
  };
  fetchLedgers();
}, []);

// In the form:
<FormControl>
  <FormLabel>{t('zzp.invoices.revenueAccount')}</FormLabel>
  <Select
    value={formData.revenue_account || ''}
    onChange={e => setFormData(prev => ({ ...prev, revenue_account: e.target.value }))}
    isDisabled={invoice?.status !== 'draft'}
  >
    {ledgerAccounts.map(a => (
      <option key={a.account_code} value={a.account_code}>
        {a.account_code} - {a.account_name}
      </option>
    ))}
  </Select>
</FormControl>
```

Default selection: the first account in the list (which is the `zzp.revenue_account` fallback if no accounts are flagged).

#### TypeScript Type Update — `zzp.ts`

```typescript
export interface Invoice {
  // ... existing fields ...
  revenue_account?: string; // NEW: selected revenue ledger account code
}
```

#### Service Layer Changes — `ZZPInvoiceService`

In `create_invoice()`, store the `revenue_account` from the request data:

```python
# In create_invoice INSERT:
revenue_account = data.get('revenue_account')
# If not provided, read default from parameter
if not revenue_account:
    revenue_account = self._get_default_revenue_account(tenant)

# Add to INSERT statement
"""INSERT INTO invoices
   (..., revenue_account, ...)
   VALUES (..., %s, ...)"""
```

In `get_invoice()`, include `revenue_account` in the returned dict (already covered by `SELECT *`).

#### Booking Helper Changes — `InvoiceBookingHelper`

The `book_outgoing_invoice()` method reads `revenue_account` from the invoice dict instead of the global parameter:

```python
def book_outgoing_invoice(self, tenant, invoice, storage_result=None):
    # Use invoice-level revenue account, fall back to parameter
    revenue_acct = invoice.get('revenue_account')
    if not revenue_acct:
        revenue_acct = self._get_param(tenant, 'revenue_account')

    debtor_acct = self._get_param(tenant, 'debtor_account')
    # ... rest of booking logic uses revenue_acct ...
```

The same applies to `book_credit_note()` — it reads `revenue_account` from the original invoice:

```python
def book_credit_note(self, tenant, credit_note, original_invoice, storage_result=None):
    # Use original invoice's revenue account
    revenue_acct = original_invoice.get('revenue_account')
    if not revenue_acct:
        revenue_acct = self._get_param(tenant, 'revenue_account')
    # ... reversal entries use revenue_acct ...
```

### 14.4 Parameter-Driven Booking Accounts (Req 19)

**Goal:** Remove all hardcoded fallback account codes from `InvoiceBookingHelper._get_param()`. Add `zzp_debtor_account` and `zzp_creditor_account` to the ledger parameter registry.

#### Registry Changes — `ledger_parameters.json`

Add two new entries:

```json
{
  "key": "zzp_debtor_account",
  "type": "boolean",
  "label_en": "ZZP Debtor Account",
  "label_nl": "ZZP Debiteurenrekening",
  "description_en": "Account used as debtor ledger for ZZP invoices",
  "description_nl": "Rekening gebruikt als debiteurenrekening voor ZZP facturen",
  "module": "ZZP"
},
{
  "key": "zzp_creditor_account",
  "type": "boolean",
  "label_en": "ZZP Creditor Account",
  "label_nl": "ZZP Crediteurenrekening",
  "description_en": "Account used as creditor ledger for ZZP invoices",
  "description_nl": "Rekening gebruikt als crediteurenrekening voor ZZP facturen",
  "module": "ZZP"
}
```

These flags mark accounts in `rekeningschema.parameters` as eligible for selection as debtor/creditor accounts, following the same pattern as `bank_account` and `asset_account`.

#### Booking Helper Changes — `InvoiceBookingHelper._get_param()`

**Before (current):**

```python
def _get_param(self, tenant: str, key: str, default: str) -> str:
    if self.parameter_service:
        val = self.parameter_service.get_param('zzp', key, tenant=tenant)
        if val:
            return str(val)
    return default  # ← hardcoded fallback
```

**After (no fallback, descriptive error):**

```python
# Required parameters that must be configured per tenant
REQUIRED_BOOKING_PARAMS = {
    'debtor_account': 'zzp.debtor_account',
    'creditor_account': 'zzp.creditor_account',
    'revenue_account': 'zzp.revenue_account',
}

def _get_param(self, tenant: str, key: str) -> str:
    """Get a required booking parameter. Raises if not configured."""
    if self.parameter_service:
        val = self.parameter_service.get_param('zzp', key, tenant=tenant)
        if val:
            return str(val)
    param_name = self.REQUIRED_BOOKING_PARAMS.get(key, f'zzp.{key}')
    raise ValueError(
        f"Required booking parameter '{param_name}' is not configured for tenant '{tenant}'. "
        f"Please set this parameter in Tenant Administration → Parameters."
    )
```

**Callers updated** — remove all default arguments:

```python
# Before:
debtor_acct = self._get_param(tenant, 'debtor_account', '1300')
revenue_acct = self._get_param(tenant, 'revenue_account', '8001')
creditor_acct = self._get_param(tenant, 'creditor_account', '1600')

# After:
debtor_acct = self._get_param(tenant, 'debtor_account')
revenue_acct = self._get_param(tenant, 'revenue_account')
creditor_acct = self._get_param(tenant, 'creditor_account')
```

The `_get_vat_ledger_account()` method continues to read from `TaxRateService` — no change needed there since VAT accounts are already parameter-driven via the `tax_rates` table.

#### Parameter Validation on Save

When a tenant admin sets `zzp.debtor_account` or `zzp.creditor_account`, the ZZP routes validate that the account code exists in the tenant's chart of accounts with the corresponding flag:

```python
def _validate_booking_account(self, tenant, key, account_code):
    """Validate that the account exists and has the corresponding ledger flag."""
    flag_map = {
        'debtor_account': 'zzp_debtor_account',
        'creditor_account': 'zzp_creditor_account',
        'revenue_account': 'zzp_invoice_ledger',
    }
    flag = flag_map.get(key)
    if not flag:
        return  # No validation for unknown keys

    rows = self.db.execute_query(
        """SELECT nummer FROM rekeningschema
           WHERE administration = %s AND nummer = %s
             AND JSON_EXTRACT(parameters, %s) = true""",
        (tenant, account_code, f'$.{flag}'),
    )
    if not rows:
        raise ValueError(
            f"Account {account_code} is not flagged as '{flag}' in the chart of accounts. "
            f"Enable the '{flag}' toggle on this account first."
        )
```

### 14.5 Invoice PDF Header Details (Req 20)

**Goal:** Create a `zzp_branding` namespace in `parameter_schema.py`, rename existing `branding` to `str_branding`, update PDF generator to read from `zzp_branding`, and register `zzp_invoice` as a template type.

#### Parameter Schema Changes — `parameter_schema.py`

**Rename** existing `branding` key to `str_branding` with `module: 'STR'`:

```python
'str_branding': {
    'label': 'STR Branding',
    'label_nl': 'STR Huisstijl',
    'module': 'STR',
    'params': {
        # ... same keys as current branding ...
    },
},
```

**Add** new `zzp_branding` namespace with `module: 'ZZP'`:

```python
'zzp_branding': {
    'label': 'ZZP Branding',
    'label_nl': 'ZZP Huisstijl',
    'module': 'ZZP',
    'params': {
        'company_logo_file_id': {
            'label': 'Company Logo (Google Drive File ID)',
            'label_nl': 'Bedrijfslogo (Google Drive Bestands-ID)',
            'type': 'string',
            'description': 'Google Drive file ID for company logo',
        },
        'company_name': {
            'label': 'Company Name',
            'label_nl': 'Bedrijfsnaam',
            'type': 'string',
            'description': 'Legal company name for ZZP invoices',
        },
        'company_address': {
            'label': 'Company Address',
            'label_nl': 'Bedrijfsadres',
            'type': 'string',
        },
        'company_postal_city': {
            'label': 'Postal Code & City',
            'label_nl': 'Postcode & Plaats',
            'type': 'string',
        },
        'company_country': {
            'label': 'Country',
            'label_nl': 'Land',
            'type': 'string',
        },
        'company_vat': {
            'label': 'VAT Number',
            'label_nl': 'BTW-nummer',
            'type': 'string',
        },
        'company_coc': {
            'label': 'Chamber of Commerce Number',
            'label_nl': 'KvK-nummer',
            'type': 'string',
        },
        'company_iban': {
            'label': 'Bank Account (IBAN)',
            'label_nl': 'Bankrekening (IBAN)',
            'type': 'string',
            'description': 'IBAN shown on invoices for payment',
        },
        'company_phone': {
            'label': 'Phone Number',
            'label_nl': 'Telefoonnummer',
            'type': 'string',
        },
        'contact_email': {
            'label': 'Contact Email',
            'label_nl': 'Contact E-mail',
            'type': 'string',
        },
    },
},
```

New keys compared to the old `branding`: `company_iban` and `company_phone` — needed for professional invoice headers.

#### PDF Generator Changes — `pdf_generator_service.py`

**`_get_branding()`** reads from `zzp_branding` instead of `branding`:

```python
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
    return branding
```

**`_get_tenant_logo()`** reads from `zzp_branding` instead of `branding`:

```python
def _get_tenant_logo(self, tenant: str) -> Optional[str]:
    logo_file_id = None
    if self.parameter_service:
        logo_file_id = self.parameter_service.get_param(
            'zzp_branding', 'company_logo_file_id', tenant=tenant
        )
    # ... rest unchanged ...
```

**`_render_html()`** adds new template placeholders for the additional branding fields and ensures missing fields are omitted (empty string, not placeholder text):

```python
# Additional replacements in _render_html():
'{{tenant_iban}}': branding.get('company_iban', ''),
'{{tenant_phone}}': branding.get('company_phone', ''),
```

#### STR Invoice Generator Update

Any STR code that currently reads from `branding` namespace must be updated to read from `str_branding`. Search for `get_param('branding',` and replace with `get_param('str_branding',`.

#### Template Registration

Register `zzp_invoice` as a template type in Template Management so tenants can customize the layout:

```python
# In template_service.py or template registration
TEMPLATE_TYPES = {
    # ... existing types ...
    'zzp_invoice': {
        'label': 'ZZP Invoice Template',
        'label_nl': 'ZZP Factuur Sjabloon',
        'default_file': 'zzp_invoice_default.html',
        'module': 'ZZP',
    },
}
```

#### Updated Default Template — `zzp_invoice_default.html`

The default template is updated to include full sender/recipient header layout:

```html
<!-- Sender (tenant) details -->
<div class="sender">
  {{logo}}
  <h3>{{tenant_name}}</h3>
  <p>
    {{tenant_address}}<br />
    {{tenant_postal_city}}<br />
    {{tenant_country}}
  </p>
  <p>
    BTW: {{tenant_vat}}<br />
    KvK: {{tenant_coc}}<br />
    IBAN: {{tenant_iban}}<br />
    Tel: {{tenant_phone}}<br />
    Email: {{tenant_email}}
  </p>
</div>

<!-- Recipient (client) details -->
<div class="recipient">
  <h3>{{company_name}}</h3>
  <p>
    {{contact_person}}<br />
    {{street_address}}<br />
    {{postal_code}} {{city}}<br />
    {{country}}
  </p>
  <p>BTW: {{client_vat}}</p>
</div>
```

Empty placeholders are rendered as empty strings — the template uses CSS to collapse empty `<p>` and `<br/>` elements so no blank lines appear when fields are not configured.

### 14.6 Locale-Aware Invoice Formatting (Req 21)

**Goal:** Format dates, currency, and numbers on invoice PDFs based on the client's country from Contact_Registry.

#### Approach: `babel` Library

Use Python's `babel` library (already widely used, well-maintained) for locale-aware formatting. It provides `format_date()`, `format_currency()`, and `format_decimal()` with proper locale support.

**New dependency:** `babel>=2.14.0` added to `requirements.txt`.

#### Country-to-Locale Mapping

```python
# In pdf_generator_service.py

# Map ISO 3166-1 country codes/names to Babel locale identifiers
COUNTRY_LOCALE_MAP = {
    'NL': 'nl_NL', 'Nederland': 'nl_NL', 'Netherlands': 'nl_NL',
    'DE': 'de_DE', 'Duitsland': 'de_DE', 'Germany': 'de_DE',
    'US': 'en_US', 'Verenigde Staten': 'en_US', 'United States': 'en_US',
    'GB': 'en_GB', 'Verenigd Koninkrijk': 'en_GB', 'United Kingdom': 'en_GB',
    'FR': 'fr_FR', 'Frankrijk': 'fr_FR', 'France': 'fr_FR',
    'BE': 'nl_BE', 'Belgie': 'nl_BE', 'Belgium': 'nl_BE',
    # Extend as needed
}
DEFAULT_LOCALE = 'nl_NL'

def _resolve_locale(self, contact: dict) -> str:
    """Resolve Babel locale from contact's country. Default: nl_NL."""
    country = (contact.get('country') or '').strip()
    if not country:
        return self.DEFAULT_LOCALE
    # Try exact match, then uppercase, then title case
    return (self.COUNTRY_LOCALE_MAP.get(country)
            or self.COUNTRY_LOCALE_MAP.get(country.upper())
            or self.COUNTRY_LOCALE_MAP.get(country.title())
            or self.DEFAULT_LOCALE)
```

#### Formatting Functions

Replace the current hardcoded `_nl_amount()`, `_nl_qty()`, `_nl_date()` with locale-aware versions:

```python
from babel.numbers import format_currency, format_decimal
from babel.dates import format_date as babel_format_date
from datetime import date as date_type

def _format_amount(self, val, currency_code: str, locale: str) -> str:
    """Format currency amount using locale conventions with invoice currency symbol."""
    n = float(val or 0)
    return format_currency(n, currency_code, locale=locale)

def _format_qty(self, val, locale: str) -> str:
    """Format quantity: integer if whole, otherwise 2 decimals."""
    n = float(val or 0)
    if n == int(n):
        return str(int(n))
    return format_decimal(n, format='#,##0.##', locale=locale)

def _format_date(self, val, locale: str) -> str:
    """Format date according to locale conventions."""
    s = str(val or '')
    try:
        if isinstance(val, date_type):
            d = val
        elif len(s) >= 10 and s[4] == '-':
            d = date_type.fromisoformat(s[:10])
        else:
            return s
        return babel_format_date(d, format='short', locale=locale)
    except Exception:
        return s
```

#### Integration in `_render_html()`

```python
def _render_html(self, tenant, invoice, is_copy=False):
    # ... existing setup ...
    contact = invoice.get('contact', {})
    locale = self._resolve_locale(contact)
    currency = invoice.get('currency', 'EUR')

    # Use locale-aware formatters
    def fmt_amount(val):
        return self._format_amount(val, currency, locale)

    def fmt_qty(val):
        return self._format_qty(val, locale)

    def fmt_date(val):
        return self._format_date(val, locale)

    # Build lines HTML with locale formatting
    lines_html = ''
    for line in lines:
        lines_html += (
            f'<tr>'
            f'<td>{line.get("description", "")}</td>'
            f'<td class="right">{fmt_qty(line.get("quantity", 0))}</td>'
            f'<td class="right">{fmt_amount(line.get("unit_price", 0))}</td>'
            f'<td class="right">{float(line.get("vat_rate", 0)):.0f}%</td>'
            f'<td class="right">{fmt_amount(line.get("line_total", 0))}</td>'
            f'</tr>'
        )

    # Replacements use locale-aware formatting
    replacements = {
        # ... existing keys ...
        '{{invoice_date}}': fmt_date(invoice.get('invoice_date', '')),
        '{{due_date}}': fmt_date(invoice.get('due_date', '')),
        '{{subtotal}}': fmt_amount(invoice.get('subtotal', 0)),
        '{{vat_total}}': fmt_amount(invoice.get('vat_total', 0)),
        '{{grand_total}}': fmt_amount(invoice.get('grand_total', 0)),
    }
```

#### Formatting Examples by Locale

| Locale | Date       | Currency   | Quantity |
| ------ | ---------- | ---------- | -------- |
| nl_NL  | 15-05-2026 | € 1.250,00 | 160      |
| en_US  | 5/15/26    | €1,250.00  | 160      |
| en_GB  | 15/05/2026 | €1,250.00  | 160      |
| de_DE  | 15.05.26   | 1.250,00 € | 160      |
| fr_FR  | 15/05/2026 | 1 250,00 € | 160      |

Note: The currency symbol always comes from the invoice's `currency` field (ISO 4217), not the locale. A Dutch client billed in USD sees `$ 1.250,00` (NL number format, USD symbol).

### 14.7 Storage URL and Filename in Mutaties Ref3/Ref4 — Strict Send Flow (Req 22)

**Goal:** Enforce strict send flow ordering (store → book → email), make storage failure a hard stop, email failure a soft failure, and add pre-flight health check.

#### Revised Send Flow — `ZZPInvoiceService.send_invoice()`

```python
def send_invoice(self, tenant, invoice_id, options, output_service=None):
    """Send invoice or credit note with strict ordering guarantees.

    Flow: health check → generate PDF → store PDF → book mutaties → send email
    Storage failure = hard stop (invoice stays draft, no mutaties created)
    Email failure = soft failure (invoice booked as sent, user resends manually)
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

    # 2. Store PDF — HARD STOP on failure
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

    # 5. Send email — SOFT FAILURE (invoice already booked)
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
                email_warning = f"Invoice booked successfully, but email failed: {email_result.get('error')}. Please resend manually."
                logger.error("Email failed for %s: %s", invoice['invoice_number'], email_result.get('error'))
        except Exception as e:
            email_warning = f"Invoice booked successfully, but email failed: {e}. Please resend manually."
            logger.error("Email exception for %s: %s", invoice['invoice_number'], e)

    result = {'success': True, 'invoice_number': invoice['invoice_number']}
    if email_warning:
        result['warning'] = email_warning
    return result
```

#### Key Differences from Current Implementation

| Aspect               | Before                                 | After                                          |
| -------------------- | -------------------------------------- | ---------------------------------------------- |
| Storage failure      | Logs warning, continues with empty URL | Hard stop — returns error, invoice stays draft |
| Email failure        | Returns `success: False`               | Returns `success: True` with `warning` field   |
| Status update timing | After email                            | After booking, before email                    |
| Health check         | None                                   | Pre-flight `check_health()` before flow starts |
| Storage result       | Optional (empty URL allowed)           | Required (no URL = abort)                      |

#### OutputService.check_health()

A lightweight connectivity test added to `OutputService`:

```python
def check_health(self, tenant: str = None) -> dict:
    """Lightweight storage connectivity check.

    Tests that the configured storage provider is reachable.
    Does NOT write any data — just verifies connectivity.
    """
    provider = 'google_drive'  # default
    if self.parameter_service and tenant:
        provider = self.parameter_service.get_param(
            'storage', 'invoice_provider', tenant=tenant
        ) or 'google_drive'

    try:
        if provider == 'google_drive':
            # Verify Google Drive API is reachable
            folder_id = self.parameter_service.get_param(
                'storage', 'google_drive_invoices_folder_id', tenant=tenant
            )
            if not folder_id:
                return {'healthy': False, 'reason': 'Google Drive invoices folder not configured'}
            # Light API call: get folder metadata
            self.drive_service.files().get(fileId=folder_id, fields='id').execute()
            return {'healthy': True}

        elif provider in ('s3_shared', 's3_tenant'):
            bucket = self.parameter_service.get_param(
                'storage', f'{provider}_bucket', tenant=tenant
            )
            if not bucket:
                return {'healthy': False, 'reason': f'{provider} bucket not configured'}
            # Light API call: head bucket
            self.s3_client.head_bucket(Bucket=bucket)
            return {'healthy': True}

        return {'healthy': False, 'reason': f'Unknown provider: {provider}'}

    except Exception as e:
        return {'healthy': False, 'reason': str(e)}
```

#### Ref3/Ref4 Data Flow

The storage result is already passed to `InvoiceBookingHelper` via the `storage_result` parameter. The `_build_entry()` method maps:

- `storage_result['url']` → `Ref3` (storage URL)
- `storage_result['filename']` → `Ref4` (e.g., `INV-2026-0003.pdf`)

This is already implemented in the current `InvoiceBookingHelper` — the change is that `storage_result` is now guaranteed to have a valid URL (because storage failure aborts the flow).

#### Frontend Handling of Soft Email Failure

The frontend checks for the `warning` field in the send response:

```typescript
const result = await sendInvoice(invoiceId, options);
if (result.success) {
  if (result.warning) {
    toast({
      title: t("zzp.invoices.sentWithWarning"),
      description: result.warning,
      status: "warning",
      duration: 10000,
      isClosable: true,
    });
  } else {
    toast({ title: t("zzp.invoices.sent"), status: "success", duration: 3000 });
  }
  reload();
} else {
  toast({
    title: t("zzp.invoices.sendFailed"),
    description: result.error,
    status: "error",
    duration: 8000,
  });
}
```

### 14.8 Correctness Properties (Reqs 16–22)

_A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

#### Property 1: Column filter AND logic

_For any_ set of parameters and any combination of column filter values, every row displayed in the filtered table SHALL match ALL active filters using case-insensitive substring matching. A row is displayed if and only if, for each filter with a non-empty value, the corresponding column value contains the filter string (case-insensitive).

**Validates: Requirements 16.3**

#### Property 2: Booking entries use invoice-level revenue account

_For any_ outgoing invoice with a `revenue_account` value set, all mutaties entries created by `book_outgoing_invoice()` SHALL use that invoice's `revenue_account` as the credit account (main entry) and debit account (VAT entries), not the global `zzp.revenue_account` parameter. For any credit note, the reversal entries SHALL use the `revenue_account` from the original invoice.

**Validates: Requirements 18.4, 18.5, 18.6**

#### Property 3: Missing required booking parameters raise descriptive errors

_For any_ tenant where one or more of the required booking parameters (`zzp.debtor_account`, `zzp.creditor_account`, `zzp.revenue_account`) is not configured, calling `_get_param()` for that parameter SHALL raise a `ValueError` with a message that names the missing parameter. No hardcoded default value SHALL be returned.

**Validates: Requirements 19.2, 19.3, 19.5**

#### Property 4: Locale-aware formatting matches client country

_For any_ client country and any numeric value (date, currency amount, or decimal quantity), the formatted output from the PDF generator SHALL match the formatting conventions of the locale derived from that country. If the country is not mapped or is empty, the formatting SHALL match the Dutch (nl_NL) locale.

**Validates: Requirements 21.1, 21.2, 21.3, 21.4**

#### Property 5: Currency symbol from invoice currency code

_For any_ invoice with a specified currency code (ISO 4217) and any client locale, the currency symbol in the formatted amount SHALL correspond to the invoice's currency code, not the locale's default currency.

**Validates: Requirements 21.5**

#### Property 6: Storage result flows to Ref3/Ref4 on mutaties

_For any_ invoice or credit note that is successfully sent, all corresponding mutaties entries SHALL have `Ref3` set to the storage URL and `Ref4` set to the PDF filename from the storage result.

**Validates: Requirements 22.2, 22.3, 22.4**

#### Property 7: Storage failure aborts send flow

_For any_ invoice where the OutputService fails to store the PDF (raises exception or returns no URL), the send operation SHALL return `success: False`, the invoice status SHALL remain `'draft'`, and zero mutaties entries SHALL be created for that invoice.

**Validates: Requirements 22.5**

#### Property 8: Email failure is soft failure

_For any_ invoice where storage and booking succeed but email sending fails, the invoice status SHALL be `'sent'`, the mutaties entries SHALL exist with correct Ref3/Ref4, and the response SHALL include a `warning` field describing the email failure.

**Validates: Requirements 22.6**

### 14.9 Error Handling (Reqs 16–22)

| Scenario                                                                | Behavior                                              | User Message                                                                                                                                           |
| ----------------------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Missing `zzp.debtor_account` parameter                                  | `_get_param()` raises `ValueError`                    | "Required booking parameter 'zzp.debtor_account' is not configured for tenant '...'. Please set this parameter in Tenant Administration → Parameters." |
| Missing `zzp.creditor_account` parameter                                | Same as above                                         | Same pattern with creditor_account                                                                                                                     |
| Missing `zzp.revenue_account` parameter (and no invoice-level override) | Same as above                                         | Same pattern with revenue_account                                                                                                                      |
| Account code not flagged in chart of accounts                           | Validation raises `ValueError`                        | "Account 1300 is not flagged as 'zzp_debtor_account' in the chart of accounts. Enable the toggle first."                                               |
| No accounts flagged with `zzp_invoice_ledger`                           | API returns fallback to `zzp.revenue_account` default | Dropdown shows single default account                                                                                                                  |
| Storage health check fails                                              | Send aborted, invoice stays draft                     | "Storage unavailable: {reason}. Invoice not sent."                                                                                                     |
| PDF storage fails                                                       | Send aborted, invoice stays draft, no mutaties        | "Storage unavailable — invoice not sent: {error}"                                                                                                      |
| Storage returns no URL                                                  | Send aborted                                          | "Storage failed — no URL returned. Invoice not sent."                                                                                                  |
| Email send fails after booking                                          | Invoice status = sent, warning returned               | "Invoice booked successfully, but email failed: {error}. Please resend manually."                                                                      |
| Unknown client country for locale                                       | Falls back to nl_NL                                   | No error — uses Dutch formatting                                                                                                                       |
| `babel` not installed                                                   | Import error at PDF generation                        | "Locale formatting requires babel. Install with: pip install babel>=2.14.0"                                                                            |
| `zzp_branding` not configured                                           | Empty strings in template                             | Missing fields omitted from PDF header (no empty placeholders)                                                                                         |

### 14.10 Testing Strategy (Reqs 16–22)

#### Unit Tests

| Test                                                                              | Type        | Validates |
| --------------------------------------------------------------------------------- | ----------- | --------- |
| Column filter renders Input elements in second Thead row                          | Example     | Req 16.1  |
| Debounce delays filter application by 150ms                                       | Example     | Req 16.2  |
| Namespace dropdown is removed                                                     | Example     | Req 16.4  |
| `ledger_parameters.json` contains `zzp_invoice_ledger` entry                      | Smoke       | Req 17.1  |
| `ledger_parameters.json` contains `zzp_debtor_account` and `zzp_creditor_account` | Smoke       | Req 19.1  |
| Account Modal renders `zzp_invoice_ledger` toggle                                 | Example     | Req 17.2  |
| Invoice ledger API returns flagged accounts                                       | Integration | Req 17.3  |
| Invoice ledger API falls back when no accounts flagged                            | Edge case   | Req 17.4  |
| Revenue account dropdown populated from API                                       | Example     | Req 18.1  |
| New invoice defaults to `zzp.revenue_account`                                     | Example     | Req 18.2  |
| Revenue account stored on invoice record                                          | Example     | Req 18.3  |
| `parameter_schema.py` contains `zzp_branding` namespace                           | Smoke       | Req 20.1  |
| `branding` renamed to `str_branding` with module STR                              | Smoke       | Req 20.2  |
| PDF generator reads from `zzp_branding`                                           | Example     | Req 20.3  |
| Missing `zzp_branding` omits fields (no empty placeholders)                       | Edge case   | Req 20.5  |
| `zzp_invoice` registered as template type                                         | Smoke       | Req 20.7  |
| Default locale is nl_NL when country not set                                      | Edge case   | Req 21.4  |
| Send flow executes in strict order                                                | Example     | Req 22.1  |
| `check_health()` called before send flow                                          | Example     | Req 22.7  |

#### Property-Based Tests (Hypothesis, min 100 iterations each)

| Test                                    | Property   | Library                 |
| --------------------------------------- | ---------- | ----------------------- |
| Column filter AND logic                 | Property 1 | Hypothesis + fast-check |
| Booking uses invoice revenue_account    | Property 2 | Hypothesis              |
| Missing params raise descriptive errors | Property 3 | Hypothesis              |
| Locale formatting matches country       | Property 4 | Hypothesis              |
| Currency symbol from invoice currency   | Property 5 | Hypothesis              |
| Storage result in Ref3/Ref4             | Property 6 | Hypothesis              |
| Storage failure aborts send             | Property 7 | Hypothesis              |
| Email failure is soft                   | Property 8 | Hypothesis              |

**Configuration:** Each property test runs minimum 100 iterations via `@settings(max_examples=100)`.

**Tag format:** Each test is tagged with a comment:

```python
# Feature: zzp-module, Property 2: Booking entries use invoice-level revenue account
```

#### Integration Tests

| Test                                                              | Validates     |
| ----------------------------------------------------------------- | ------------- |
| Full send flow: store → book → email with real OutputService mock | Req 22.1–22.4 |
| VAT accounts from TaxRateService in booking entries               | Req 19.4      |
| Account validation on parameter save                              | Req 19.6      |
| End-to-end invoice creation with revenue account selection        | Req 18.1–18.4 |

### 14.11 Migration Notes

#### Database Migration

```sql
-- Add revenue_account column to invoices table
ALTER TABLE invoices ADD COLUMN revenue_account VARCHAR(10) DEFAULT NULL
  AFTER exchange_rate;
```

#### Data Migration for Branding Parameters

Existing tenants with `branding.*` parameters need migration to `zzp_branding.*` and `str_branding.*`:

```sql
-- Copy branding params to zzp_branding for tenants with ZZP module
INSERT INTO parameters (scope, administration, namespace, `key`, value, value_type, is_secret, created_by)
SELECT p.scope, p.administration, 'zzp_branding', p.`key`, p.value, p.value_type, p.is_secret, 'migration'
FROM parameters p
JOIN tenant_modules tm ON p.administration = tm.administration AND tm.module_name = 'ZZP' AND tm.is_active = TRUE
WHERE p.namespace = 'branding';

-- Copy branding params to str_branding for tenants with STR module
INSERT INTO parameters (scope, administration, namespace, `key`, value, value_type, is_secret, created_by)
SELECT p.scope, p.administration, 'str_branding', p.`key`, p.value, p.value_type, p.is_secret, 'migration'
FROM parameters p
JOIN tenant_modules tm ON p.administration = tm.administration AND tm.module_name = 'STR' AND tm.is_active = TRUE
WHERE p.namespace = 'branding';

-- After verification, remove old branding params
-- DELETE FROM parameters WHERE namespace = 'branding';
```

#### New Dependency

Add to `backend/requirements.txt`:

```
babel>=2.14.0
```
