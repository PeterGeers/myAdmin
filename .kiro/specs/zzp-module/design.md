# Design Document — ZZP Module

## 1. Architecture Overview

The ZZP module follows the established myAdmin module pattern: a Flask Blueprint with service-layer delegation, multi-tenant isolation via `@tenant_required()`, and module gating via `@module_required('ZZP')`. It registers as `'ZZP'` in `MODULE_REGISTRY` with a hard dependency on `'FIN'`.

The module introduces six new database tables and five shared helpers. All shared helpers are plain Python classes in `backend/src/services/` so future modules (Webshop, Logistics) can import them without depending on ZZP routes.

### Component Diagram

```
Frontend (React/Chakra UI)
  ├── ZZPInvoices.tsx          ← invoice CRUD, PDF preview, send
  ├── ZZPTimeTracking.tsx      ← time entry, summaries
  ├── ZZPContacts.tsx          ← contact registry
  ├── ZZPProducts.tsx          ← product/service registry
  ├── ZZPDebtors.tsx           ← receivables/payables, aging
  └── (recurring = "copy last invoice" action on ZZPInvoices)
        │
        ▼  (REST API)
Backend Flask Blueprints
  ├── zzp_routes.py            ← /api/zzp/*
  ├── contact_routes.py        ← /api/contacts/*  (shared)
  └── product_routes.py        ← /api/products/*  (shared)
        │
        ▼  (Service Layer)
  ├── ZZPInvoiceService        ← invoice lifecycle, numbering, status
  ├── ContactService           ← shared contact CRUD
  ├── ProductService           ← shared product/service CRUD
  ├── InvoiceBookingHelper     ← double-entry booking in mutaties
  ├── PaymentCheckHelper       ← match bank txns to invoices
  ├── PDFGeneratorService      ← HTML→PDF via weasyprint
  ├── InvoiceEmailService      ← send via SESEmailService
  └── TimeTrackingService      ← time entry CRUD, summaries
        │
        ▼  (Existing Services)
  ├── TransactionLogic         ← save_approved_transactions()
  ├── TaxRateService           ← VAT rate lookup by date
  ├── ParameterService         ← configurable params (namespace: zzp)
  ├── TemplateService          ← HTML template rendering
  ├── OutputService            ← Google Drive / S3 storage
  └── SESEmailService          ← AWS SES email delivery
```

### Data Flow: Invoice Lifecycle

```
Invoice:      Draft → [edit] → Send → [email + book in FIN] → Sent → [payment check] → Paid
                                                                  └→ [overdue check] → Overdue → [reminder]

Credit Note:  Original invoice → [create credit] → CN Draft → [edit] → Send CN → [email + book reversal in FIN] → CN Sent
              Original invoice status → Credited
```

Credit notes follow the same send flow as invoices: generate PDF, book reversal entries in FIN, optionally email the client. The `send_invoice` method handles both types — it checks `invoice_type` and calls `book_credit_note` instead of `book_outgoing_invoice` for credit notes.

## 2. Module Registration

### MODULE_REGISTRY Entry

```python
# In backend/src/services/module_registry.py
MODULE_REGISTRY['ZZP'] = {
    'description': 'ZZP Freelancer Administration',
    'depends_on': ['FIN'],
    'required_params': {
        'zzp.invoice_prefix': {'type': 'string', 'default': 'INV'},
        'zzp.credit_note_prefix': {'type': 'string', 'default': 'CN'},
        'zzp.default_payment_terms_days': {'type': 'number', 'default': 30},
        'zzp.default_currency': {'type': 'string', 'default': 'EUR'},
        'zzp.invoice_number_padding': {'type': 'number', 'default': 4},
        'zzp.debtor_account': {'type': 'string', 'default': '1300'},
        'zzp.creditor_account': {'type': 'string', 'default': '1600'},
        'zzp.email_subject_template': {'type': 'string', 'default': 'Factuur {invoice_number} - {company_name}'},
        'zzp.invoice_email_bcc': {'type': 'string', 'default': ''},
        'zzp.retention_years': {'type': 'number', 'default': 7},
        'zzp.time_tracking_enabled': {'type': 'boolean', 'default': True},
        'zzp.product_types': {'type': 'json', 'default': ['service', 'product', 'hours', 'subscription']},
        'zzp.contact_types': {'type': 'json', 'default': ['client', 'supplier', 'both', 'other']},
        'zzp.contact_field_config': {
            'type': 'json',
            'default': {
                'client_id':        'required',
                'contact_type':     'required',
                'company_name':     'required',
                'contact_person':   'optional',
                'street_address':   'optional',
                'postal_code':      'optional',
                'city':             'optional',
                'country':          'optional',
                'vat_number':       'optional',
                'kvk_number':       'optional',
                'phone':            'optional',
                'iban':             'optional',
                'emails':           'optional',
            }
        },
        'zzp.product_field_config': {
            'type': 'json',
            'default': {
                'product_code':       'required',
                'name':               'required',
                'product_type':       'required',
                'unit_price':         'required',
                'vat_code':           'required',
                'description':        'optional',
                'unit_of_measure':    'optional',
                'external_reference': 'optional',
            }
        },
        'zzp.invoice_field_config': {
            'type': 'json',
            'default': {
                'contact_id':          'required',
                'invoice_date':        'required',
                'payment_terms_days':  'required',
                'currency':            'optional',
                'exchange_rate':       'hidden',
                'notes':               'optional',
            }
        },
        'zzp.time_entry_field_config': {
            'type': 'json',
            'default': {
                'contact_id':    'required',
                'entry_date':    'required',
                'hours':         'required',
                'hourly_rate':   'required',
                'product_id':    'optional',
                'project_name':  'optional',
                'description':   'optional',
                'is_billable':   'optional',
            }
        },
    },
    'required_tax_rates': ['btw'],
    'required_roles': ['ZZP_Read', 'ZZP_Write'],
}
```

### Field Visibility & Validation Configuration

Each entity (contacts, products, invoices, time entries) has a `*_field_config` parameter stored in `ParameterService`. This is a JSON object mapping field names to one of three visibility levels:

| Level      | Backend behavior                 | Frontend behavior                       |
| ---------- | -------------------------------- | --------------------------------------- |
| `required` | Validation rejects empty/missing | Field shown, marked required (asterisk) |
| `optional` | Accepts empty/missing values     | Field shown, not marked required        |
| `hidden`   | Accepts empty/missing, ignores   | Field not rendered in form or table     |

Tenants override the defaults via the parameter admin UI (namespace `zzp`, key e.g. `contact_field_config`). For example, a tenant that never invoices internationally can hide `currency` and `exchange_rate`; a tenant that doesn't track KvK numbers can hide `kvk_number`.

Fields with a `NOT NULL` database constraint (`client_id`, `company_name`, `product_code`, `name`) cannot be set to `hidden` — the backend enforces a minimum set regardless of config.

#### Backend: FieldConfigMixin (`backend/src/services/field_config_mixin.py`)

Shared mixin used by `ContactService`, `ProductService`, `ZZPInvoiceService`, and `TimeTrackingService`:

```python
class FieldConfigMixin:
    """Mixin providing parameter-driven field validation."""

    # Subclasses define these
    FIELD_CONFIG_KEY: str = ''           # e.g. 'contact_field_config'
    ALWAYS_REQUIRED: list[str] = []      # DB NOT NULL fields, cannot be hidden

    def get_field_config(self, tenant: str) -> dict[str, str]:
        """Get field config for tenant, merging defaults with overrides."""
        config = self.parameter_service.get_param('zzp', self.FIELD_CONFIG_KEY, tenant=tenant)
        if not config:
            from services.module_registry import MODULE_REGISTRY
            config = MODULE_REGISTRY['ZZP']['required_params'][f'zzp.{self.FIELD_CONFIG_KEY}']['default']
        # Enforce minimum required fields
        for field in self.ALWAYS_REQUIRED:
            config[field] = 'required'
        return config

    def validate_fields(self, tenant: str, data: dict) -> None:
        """Validate data against field config. Raises ValueError on missing required fields."""
        config = self.get_field_config(tenant)
        missing = [f for f, level in config.items() if level == 'required' and not data.get(f)]
        if missing:
            raise ValueError(f"Required fields missing: {', '.join(missing)}")

    def strip_hidden_fields(self, tenant: str, data: dict) -> dict:
        """Remove hidden fields from response data."""
        config = self.get_field_config(tenant)
        hidden = {f for f, level in config.items() if level == 'hidden'}
        return {k: v for k, v in data.items() if k not in hidden}
```

Usage in `ContactService`:

```python
class ContactService(FieldConfigMixin):
    FIELD_CONFIG_KEY = 'contact_field_config'
    ALWAYS_REQUIRED = ['client_id', 'company_name']

    def create_contact(self, tenant, data, created_by):
        self.validate_fields(tenant, data)
        # ... insert logic
```

#### Frontend: useFieldConfig hook (`frontend/src/hooks/useFieldConfig.ts`)

```typescript
type FieldLevel = "required" | "optional" | "hidden";
type FieldConfig = Record<string, FieldLevel>;

export function useFieldConfig(
  entity: "contacts" | "products" | "invoices" | "time_entries",
) {
  const [config, setConfig] = useState<FieldConfig>({});

  useEffect(() => {
    getFieldConfig(entity).then(setConfig);
  }, [entity]);

  const isVisible = (field: string) => config[field] !== "hidden";
  const isRequired = (field: string) => config[field] === "required";

  return {
    config,
    isVisible,
    isRequired,
    loading: Object.keys(config).length === 0,
  };
}
```

Usage in a form:

```tsx
const { isVisible, isRequired } = useFieldConfig("contacts");

return (
  <FormControl
    isRequired={isRequired("vat_number")}
    display={isVisible("vat_number") ? "block" : "none"}
  >
    <FormLabel>{t("zzp.contacts.vatNumber")}</FormLabel>
    <Input name="vat_number" />
  </FormControl>
);
```

Table columns also filter by `isVisible()` so hidden fields don't appear in the list view.

#### API Endpoint

| Method | Endpoint                         | Permission   | Description                    |
| ------ | -------------------------------- | ------------ | ------------------------------ |
| GET    | `/api/zzp/field-config/<entity>` | `zzp_read`   | Get field config for entity    |
| PUT    | `/api/zzp/field-config/<entity>` | `zzp_tenant` | Update field config for tenant |

`GET /api/zzp/field-config/contacts` response:

```json
{
  "success": true,
  "data": {
    "client_id": "required",
    "contact_type": "required",
    "company_name": "required",
    "contact_person": "optional",
    "street_address": "optional",
    "postal_code": "optional",
    "city": "optional",
    "country": "optional",
    "vat_number": "hidden",
    "kvk_number": "hidden",
    "phone": "optional",
    "iban": "optional",
    "emails": "optional"
  }
}
```

### Dependency Enforcement

When activating ZZP for a tenant, the activation logic checks `depends_on`:

```python
def activate_module(db, tenant, module_name):
    module_def = MODULE_REGISTRY.get(module_name)
    for dep in module_def.get('depends_on', []):
        if not has_module(db, tenant, dep):
            raise ValueError(f"Module {dep} must be active before enabling {module_name}")
    # Insert into tenant_modules ...
```

### Route Decorator Chain

All ZZP routes use:

```python
@zzp_bp.route('/api/zzp/<action>', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def action(user_email, user_roles, tenant, user_tenants):
    ...
```

### Permissions

| Permission   | Description                           |
| ------------ | ------------------------------------- |
| `zzp_read`   | View invoices, contacts, time entries |
| `zzp_crud`   | Create/edit/delete invoices, contacts |
| `zzp_export` | Export invoices, reports              |
| `zzp_tenant` | Tenant-level ZZP configuration        |

## 3. Database Schema

All new tables use `ENGINE=InnoDB`, `utf8mb4_unicode_ci`, and include `administration VARCHAR(50)` for tenant isolation with an index on `administration`.

### 3.1 contacts

Shared contact registry (Req 2). Reusable by future modules.

```sql
CREATE TABLE contacts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    client_id VARCHAR(20) NOT NULL COMMENT 'Short unique ref per tenant, e.g. ACME, KPN',
    contact_type VARCHAR(20) NOT NULL DEFAULT 'client' COMMENT 'From zzp.contact_types parameter set',
    company_name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255) DEFAULT NULL,
    street_address VARCHAR(255) DEFAULT NULL,
    postal_code VARCHAR(20) DEFAULT NULL,
    city VARCHAR(100) DEFAULT NULL,
    country VARCHAR(100) DEFAULT 'NL',
    vat_number VARCHAR(50) DEFAULT NULL,
    kvk_number VARCHAR(20) DEFAULT NULL COMMENT 'Chamber of Commerce',
    phone VARCHAR(50) DEFAULT NULL,
    iban VARCHAR(50) DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    UNIQUE KEY uq_tenant_client_id (administration, client_id),
    INDEX idx_administration (administration),
    INDEX idx_client_id (client_id),
    INDEX idx_contact_type (contact_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.2 contact_emails

Multiple emails per contact with type indicator (Req 2.4).

```sql
CREATE TABLE contact_emails (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contact_id INT NOT NULL,
    email VARCHAR(255) NOT NULL,
    email_type ENUM('general', 'invoice', 'other') DEFAULT 'general',
    is_primary BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
    INDEX idx_contact_id (contact_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.3 products

Shared product/service registry (Req 3).

```sql
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    product_code VARCHAR(30) NOT NULL COMMENT 'Short unique ref per tenant, e.g. DEV-HR, CONSULT',
    external_reference VARCHAR(100) DEFAULT NULL COMMENT 'Link to external system (e.g. supplier SKU, accounting code)',
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT NULL,
    product_type VARCHAR(50) NOT NULL COMMENT 'From zzp.product_types parameter set',
    unit_price DECIMAL(12,2) DEFAULT 0.00,
    vat_code VARCHAR(20) NOT NULL COMMENT 'Ref to tax_rates.tax_code (high/low/zero)',
    unit_of_measure VARCHAR(50) DEFAULT 'uur' COMMENT 'uur, stuk, maand, etc.',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    INDEX idx_administration (administration),
    INDEX idx_product_type (product_type),
    UNIQUE KEY uq_tenant_product_code (administration, product_code),
    INDEX idx_external_reference (external_reference)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.4 invoices

Core invoice header (Req 4, 5, 10, 13, 14).

```sql
CREATE TABLE invoices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    invoice_number VARCHAR(30) NOT NULL COMMENT 'e.g. INV-2026-0001 or CN-2026-0001',
    invoice_type ENUM('invoice', 'credit_note') DEFAULT 'invoice',
    contact_id INT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    payment_terms_days INT DEFAULT 30,
    currency VARCHAR(3) DEFAULT 'EUR',
    exchange_rate DECIMAL(12,6) DEFAULT 1.000000,
    status ENUM('draft', 'sent', 'paid', 'overdue', 'cancelled', 'credited') DEFAULT 'draft',
    subtotal DECIMAL(12,2) DEFAULT 0.00,
    vat_total DECIMAL(12,2) DEFAULT 0.00,
    grand_total DECIMAL(12,2) DEFAULT 0.00,
    notes TEXT DEFAULT NULL,
    original_invoice_id INT DEFAULT NULL COMMENT 'For credit notes: link to original',
    sent_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    UNIQUE KEY uq_tenant_invoice_number (administration, invoice_number),
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (original_invoice_id) REFERENCES invoices(id),
    INDEX idx_administration (administration),
    INDEX idx_status (status),
    INDEX idx_contact_id (contact_id),
    INDEX idx_due_date (due_date),
    INDEX idx_invoice_date (invoice_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Note — no duplication with `mutaties`:** The following data is stored exclusively on the `mutaties` entry created by `InvoiceBookingHelper`, not on the `invoices` row:

- PDF storage URL → `mutaties.Ref3` (consistent with existing invoice upload pattern where Ref3 = document URL)
- PDF filename → `mutaties.Ref4` (consistent with existing pattern where Ref4 = filename)
- Invoice number → `mutaties.Ref2` (available field — other modules use Ref2 for context-specific references: sequence numbers in banking, period in BTW, year in assets)
- Payment date → derived from the matched bank transaction date when `PaymentCheckHelper` flips the invoice status to `paid`

To retrieve the PDF for an invoice, the service queries:

```sql
SELECT Ref3, Ref4 FROM mutaties
WHERE administration = %s AND Ref2 = %s AND ReferenceNumber = %s
LIMIT 1
```

Where `Ref2` = invoice number (e.g. `INV-2026-0001`) and `ReferenceNumber` = contact's `client_id` (e.g. `ACME`). The combination uniquely identifies the invoice's main booking entry.

### 3.5 invoice_lines

Line items per invoice (Req 4.2).

```sql
CREATE TABLE invoice_lines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_id INT NOT NULL,
    product_id INT DEFAULT NULL,
    description VARCHAR(512) NOT NULL,
    quantity DECIMAL(10,4) DEFAULT 1.0000,
    unit_price DECIMAL(12,2) NOT NULL,
    vat_code VARCHAR(20) NOT NULL,
    vat_rate DECIMAL(5,2) NOT NULL COMMENT 'Snapshot of rate at invoice date',
    vat_amount DECIMAL(12,2) NOT NULL,
    line_total DECIMAL(12,2) NOT NULL COMMENT 'quantity * unit_price (excl VAT)',
    sort_order INT DEFAULT 0,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id),
    INDEX idx_invoice_id (invoice_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.6 vw_invoice_vat_summary (view)

VAT breakdown per rate per invoice as a database view (Req 4.5). Derived directly from `invoice_lines` — no separate table, no sync issues.

```sql
CREATE OR REPLACE VIEW vw_invoice_vat_summary AS
SELECT
    invoice_id,
    vat_code,
    vat_rate,
    ROUND(SUM(line_total), 2) AS base_amount,
    ROUND(SUM(vat_amount), 2) AS vat_amount
FROM invoice_lines
GROUP BY invoice_id, vat_code, vat_rate;
```

Usage: `SELECT * FROM vw_invoice_vat_summary WHERE invoice_id = %s`

This view is used by:

- `ZZPInvoiceService` — builds the `vat_summary` array in API responses
- `InvoiceBookingHelper` — creates one `mutaties` entry per VAT rate bucket
- `PDFGeneratorService` — renders the VAT breakdown on the invoice PDF

### 3.7 invoice_number_sequences

Tenant+year sequence counter with row-level locking (Req 5.4).

```sql
CREATE TABLE invoice_number_sequences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    prefix VARCHAR(10) NOT NULL COMMENT 'INV or CN',
    year INT NOT NULL,
    last_sequence INT DEFAULT 0,
    UNIQUE KEY uq_tenant_prefix_year (administration, prefix, year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.8 time_entries

Time tracking records (Req 11).

**Design principles:**

- Time tracking is a **standalone optional feature** — invoices can always be created directly without any time entries. It is never a prerequisite for invoicing.
- Enabled/disabled per tenant via parameter `zzp.time_tracking_enabled` (default: `true`). When disabled, the time tracking nav item, page, and API endpoints are hidden/return 404.
- **Mobile-first UX**: the time entry form must be usable on any device (phone, tablet, desktop). This means: large touch targets, minimal required fields, quick-add flow (contact + hours + date in one tap), and responsive layout. The summary views use simple card layouts on mobile rather than wide tables.

```sql
CREATE TABLE time_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    contact_id INT NOT NULL,
    product_id INT DEFAULT NULL,
    project_name VARCHAR(255) DEFAULT NULL,
    entry_date DATE NOT NULL,
    hours DECIMAL(6,2) NOT NULL,
    hourly_rate DECIMAL(10,2) NOT NULL,
    description TEXT DEFAULT NULL,
    is_billable BOOLEAN DEFAULT TRUE,
    is_billed BOOLEAN DEFAULT FALSE,
    invoice_id INT DEFAULT NULL COMMENT 'Set when billed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT NULL,
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    INDEX idx_administration (administration),
    INDEX idx_contact_id (contact_id),
    INDEX idx_entry_date (entry_date),
    INDEX idx_is_billed (is_billed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 3.9 Recurring Invoices — No Table Needed

Recurring invoicing is implemented as a **"copy last invoice" action**, not a scheduling engine. No `recurring_invoice_configs` table required.

**Flow:**

1. User selects a contact and clicks the copy-last-invoice action
2. System queries the most recent invoice for that contact: `SELECT * FROM invoices WHERE contact_id = %s AND administration = %s ORDER BY invoice_date DESC LIMIT 1`
3. System copies the invoice header and all `invoice_lines` into a new draft, auto-advancing the invoice date and period
4. User sees the pre-filled draft — only changes what's different (typically: hours/quantity, date, maybe a line description)
5. User submits → normal invoice creation flow

This minimizes work for the two main use cases:

- **Fixed recurring** (hosting, subscriptions): nothing to change, just confirm and send
- **Variable hours**: update the quantity field on the hours line, submit

No scheduling, no config, no background jobs. The intelligence is in the copy logic and smart defaults.

## 4. API Contracts

### 4.1 Contact Registry — `/api/contacts`

Shared blueprint `contact_bp` in `backend/src/routes/contact_routes.py`.

| Method | Endpoint              | Permission | Description                    |
| ------ | --------------------- | ---------- | ------------------------------ |
| GET    | `/api/contacts`       | `zzp_read` | List contacts (filter by type) |
| GET    | `/api/contacts/<id>`  | `zzp_read` | Get single contact             |
| POST   | `/api/contacts`       | `zzp_crud` | Create contact                 |
| PUT    | `/api/contacts/<id>`  | `zzp_crud` | Update contact                 |
| DELETE | `/api/contacts/<id>`  | `zzp_crud` | Soft-delete contact            |
| GET    | `/api/contacts/types` | `zzp_read` | Get contact types from params  |

`GET /api/contacts` supports query params: `?contact_type=client&include_inactive=false`

#### POST /api/contacts — Request

```json
{
  "client_id": "ACME",
  "contact_type": "client",
  "company_name": "Acme Corp B.V.",
  "contact_person": "Jan de Vries",
  "street_address": "Keizersgracht 100",
  "postal_code": "1015 AA",
  "city": "Amsterdam",
  "country": "NL",
  "vat_number": "NL123456789B01",
  "kvk_number": "12345678",
  "phone": "+31612345678",
  "iban": "NL91ABNA0417164300",
  "emails": [
    { "email": "info@acme.nl", "email_type": "general", "is_primary": true },
    { "email": "facturen@acme.nl", "email_type": "invoice" }
  ]
}
```

#### Response (all endpoints)

```json
{
  "success": true,
  "data": {
    "id": 1,
    "client_id": "ACME",
    "contact_type": "client",
    "company_name": "Acme Corp B.V.",
    "...": "..."
  }
}
```

### 4.2 Product Registry — `/api/products`

Shared blueprint `product_bp` in `backend/src/routes/product_routes.py`.

| Method | Endpoint              | Permission | Description                   |
| ------ | --------------------- | ---------- | ----------------------------- |
| GET    | `/api/products`       | `zzp_read` | List products for tenant      |
| GET    | `/api/products/<id>`  | `zzp_read` | Get single product            |
| POST   | `/api/products`       | `zzp_crud` | Create product                |
| PUT    | `/api/products/<id>`  | `zzp_crud` | Update product                |
| DELETE | `/api/products/<id>`  | `zzp_crud` | Soft-delete product           |
| GET    | `/api/products/types` | `zzp_read` | Get product types from params |

#### POST /api/products — Request

```json
{
  "product_code": "DEV-HR",
  "external_reference": "EXT-SW-001",
  "name": "Software Development",
  "description": "Custom software development services",
  "product_type": "service",
  "unit_price": 95.0,
  "vat_code": "high",
  "unit_of_measure": "uur"
}
```

### 4.3 Invoice Management — `/api/zzp/invoices`

Blueprint `zzp_bp` in `backend/src/routes/zzp_routes.py`.

| Method | Endpoint                        | Permission | Description                      |
| ------ | ------------------------------- | ---------- | -------------------------------- |
| GET    | `/api/zzp/invoices`             | `zzp_read` | List invoices (filterable)       |
| GET    | `/api/zzp/invoices/<id>`        | `zzp_read` | Get invoice with lines           |
| POST   | `/api/zzp/invoices`             | `zzp_crud` | Create draft invoice             |
| PUT    | `/api/zzp/invoices/<id>`        | `zzp_crud` | Update draft invoice             |
| POST   | `/api/zzp/invoices/<id>/send`   | `zzp_crud` | Generate PDF, email, book in FIN |
| POST   | `/api/zzp/invoices/<id>/credit` | `zzp_crud` | Create credit note               |
| GET    | `/api/zzp/invoices/<id>/pdf`    | `zzp_read` | Download/regenerate PDF          |

#### POST /api/zzp/invoices — Request

```json
{
  "contact_id": 1,
  "invoice_date": "2026-04-15",
  "payment_terms_days": 30,
  "currency": "EUR",
  "notes": "Werkzaamheden april 2026",
  "lines": [
    {
      "product_id": 1,
      "description": "Software Development - april 2026",
      "quantity": 160.0,
      "unit_price": 95.0,
      "vat_code": "high"
    }
  ]
}
```

#### Response — GET /api/zzp/invoices/<id>

```json
{
  "success": true,
  "data": {
    "id": 1,
    "invoice_number": "INV-2026-0001",
    "invoice_type": "invoice",
    "contact": {
      "id": 1,
      "client_id": "ACME",
      "company_name": "Acme Corp B.V."
    },
    "invoice_date": "2026-04-15",
    "due_date": "2026-05-15",
    "status": "draft",
    "currency": "EUR",
    "lines": [
      {
        "id": 1,
        "description": "Software Development - april 2026",
        "quantity": 160.0,
        "unit_price": 95.0,
        "vat_code": "high",
        "vat_rate": 21.0,
        "vat_amount": 3192.0,
        "line_total": 15200.0
      }
    ],
    "subtotal": 15200.0,
    "vat_summary": [
      {
        "vat_code": "high",
        "vat_rate": 21.0,
        "base_amount": 15200.0,
        "vat_amount": 3192.0
      }
    ],
    "vat_total": 3192.0,
    "grand_total": 18392.0
  }
}
```

#### POST /api/zzp/invoices/<id>/send — Request

```json
{
  "output_destination": "gdrive",
  "send_email": true
}
```

### 4.4 Time Tracking — `/api/zzp/time-entries`

| Method | Endpoint                                 | Permission | Description                       |
| ------ | ---------------------------------------- | ---------- | --------------------------------- |
| GET    | `/api/zzp/time-entries`                  | `zzp_read` | List time entries (filterable)    |
| POST   | `/api/zzp/time-entries`                  | `zzp_crud` | Create time entry                 |
| PUT    | `/api/zzp/time-entries/<id>`             | `zzp_crud` | Update time entry                 |
| DELETE | `/api/zzp/time-entries/<id>`             | `zzp_crud` | Delete time entry                 |
| GET    | `/api/zzp/time-entries/summary`          | `zzp_read` | Summary by contact/project/period |
| POST   | `/api/zzp/time-entries/import-timesheet` | `zzp_crud` | Import from PDF/Excel (Phase 2)   |

#### POST /api/zzp/time-entries — Request

```json
{
  "contact_id": 1,
  "product_id": 1,
  "project_name": "Project Alpha",
  "entry_date": "2026-04-15",
  "hours": 8.0,
  "hourly_rate": 95.0,
  "description": "Backend API development",
  "is_billable": true
}
```

### 4.5 Debtor/Creditor Management — `/api/zzp/debtors`

| Method | Endpoint                              | Permission | Description                  |
| ------ | ------------------------------------- | ---------- | ---------------------------- |
| GET    | `/api/zzp/debtors/receivables`        | `zzp_read` | Accounts receivable overview |
| GET    | `/api/zzp/debtors/payables`           | `zzp_read` | Accounts payable overview    |
| GET    | `/api/zzp/debtors/aging`              | `zzp_read` | Aging analysis               |
| POST   | `/api/zzp/debtors/send-reminder/<id>` | `zzp_crud` | Send payment reminder        |

#### Response — GET /api/zzp/debtors/aging

```json
{
  "success": true,
  "data": {
    "total_outstanding": 25000.0,
    "buckets": {
      "current": 10000.0,
      "1_30_days": 8000.0,
      "31_60_days": 5000.0,
      "61_90_days": 2000.0,
      "90_plus_days": 0.0
    },
    "by_contact": [
      {
        "contact": {
          "id": 1,
          "client_id": "ACME",
          "company_name": "Acme Corp B.V."
        },
        "total": 15000.0,
        "invoices": [
          {
            "invoice_number": "INV-2026-0001",
            "grand_total": 15000.0,
            "due_date": "2026-05-15",
            "days_overdue": 0,
            "bucket": "current"
          }
        ]
      }
    ]
  }
}
```

### 4.6 Recurring Invoices — Copy Last Invoice

No separate recurring endpoints. The copy action is part of the invoice API:

| Method | Endpoint                                   | Permission | Description                                      |
| ------ | ------------------------------------------ | ---------- | ------------------------------------------------ |
| POST   | `/api/zzp/invoices/copy-last/<contact_id>` | `zzp_crud` | Create draft by copying last invoice for contact |

#### POST /api/zzp/invoices/copy-last/1 — Response

Returns a new draft invoice pre-filled from the contact's most recent invoice, with auto-advanced date:

```json
{
  "success": true,
  "data": {
    "id": 42,
    "invoice_number": "INV-2026-0005",
    "status": "draft",
    "contact": {
      "id": 1,
      "client_id": "ACME",
      "company_name": "Acme Corp B.V."
    },
    "invoice_date": "2026-05-15",
    "due_date": "2026-06-14",
    "copied_from_invoice_id": 38,
    "lines": [
      {
        "description": "Software Development - april 2026",
        "quantity": 160.0,
        "unit_price": 95.0,
        "vat_code": "high"
      }
    ],
    "notes": "User edits quantity/dates, then saves or sends"
  }
}
```

The user edits the draft (update hours, change date/description) and then saves or sends via the normal invoice flow.

### 4.7 Payment Check — `/api/zzp/payment-check`

| Method | Endpoint                        | Permission | Description          |
| ------ | ------------------------------- | ---------- | -------------------- |
| POST   | `/api/zzp/payment-check/run`    | `zzp_crud` | Run payment matching |
| GET    | `/api/zzp/payment-check/status` | `zzp_read` | Get last run results |

## 5. Service Layer Design

### 5.1 ContactService (`backend/src/services/contact_service.py`)

Shared service, no ZZP dependency. Uses `DatabaseManager` with tenant isolation.

```python
class ContactService:
    def __init__(self, db: DatabaseManager, parameter_service: ParameterService):
        self.db = db
        self.parameter_service = parameter_service

    def list_contacts(self, tenant: str, contact_type: str = None, include_inactive=False) -> list[dict]
    def get_contact(self, tenant: str, contact_id: int) -> dict | None
    def get_contact_by_client_id(self, tenant: str, client_id: str) -> dict | None
    def create_contact(self, tenant: str, data: dict, created_by: str) -> dict
    def update_contact(self, tenant: str, contact_id: int, data: dict) -> dict
    def soft_delete_contact(self, tenant: str, contact_id: int) -> bool
    def get_invoice_email(self, tenant: str, contact_id: int) -> str | None
    def get_contact_types(self, tenant: str) -> list[str]
    def _validate_contact_type(self, tenant: str, contact_type: str) -> None
    def _check_contact_in_use(self, contact_id: int) -> bool
```

Key behaviors:

- `create_contact` validates `client_id` uniqueness within tenant and `contact_type` against the parameter set
- `_validate_contact_type` reads `zzp.contact_types` from `ParameterService` and checks membership (default: `client`, `supplier`, `both`, `other`)
- `get_contact_types` returns the configurable list from `ParameterService` (namespace `zzp`, key `contact_types`)
- `list_contacts` accepts optional `contact_type` filter — used by debtors view (filter `client`/`both`) and creditors view (filter `supplier`/`both`)
- `soft_delete_contact` checks `_check_contact_in_use` (queries `invoices` table) before setting `is_active=False`
- `get_invoice_email` returns the email with `email_type='invoice'`, falling back to `is_primary=True`

### 5.2 ProductService (`backend/src/services/product_service.py`)

Shared service. Validates `vat_code` against `TaxRateService` and `product_type` against `ParameterService`.

```python
class ProductService:
    def __init__(self, db: DatabaseManager, tax_rate_service: TaxRateService, parameter_service: ParameterService):
        self.db = db
        self.tax_rate_service = tax_rate_service
        self.parameter_service = parameter_service

    def list_products(self, tenant: str, include_inactive=False) -> list[dict]
    def get_product(self, tenant: str, product_id: int) -> dict | None
    def get_product_by_code(self, tenant: str, product_code: str) -> dict | None
    def create_product(self, tenant: str, data: dict, created_by: str) -> dict
    def update_product(self, tenant: str, product_id: int, data: dict) -> dict
    def soft_delete_product(self, tenant: str, product_id: int) -> bool
    def get_product_types(self, tenant: str) -> list[str]
    def _validate_vat_code(self, tenant: str, vat_code: str) -> None
    def _validate_product_type(self, tenant: str, product_type: str) -> None
```

Key behaviors:

- `create_product` validates `product_code` uniqueness within tenant, `vat_code`, and `product_type`
- `product_code` is a short human-readable identifier (e.g. `DEV-HR`, `CONSULT`, `HOST-M`) unique per tenant — used on invoice lines and for quick lookup
- `external_reference` is an optional free-text field for linking to external systems (supplier SKU, accounting software code, ERP article number)
- `_validate_vat_code` calls `tax_rate_service.get_tax_rate(tenant, 'btw', vat_code, date.today())` — only `high`, `low`, `zero` accepted
- `_validate_product_type` reads `zzp.product_types` from `parameter_service` and checks membership
- `get_product_types` returns the configurable list from `ParameterService` (namespace `zzp`, key `product_types`)

### 5.3 ZZPInvoiceService (`backend/src/services/zzp_invoice_service.py`)

Core invoice lifecycle management.

```python
class ZZPInvoiceService:
    def __init__(self, db: DatabaseManager, tax_rate_service: TaxRateService,
                 parameter_service: ParameterService, booking_helper: InvoiceBookingHelper,
                 pdf_generator: PDFGeneratorService, email_service: InvoiceEmailService):
        ...

    # CRUD
    def create_invoice(self, tenant: str, data: dict, created_by: str) -> dict
    def update_invoice(self, tenant: str, invoice_id: int, data: dict) -> dict
    def get_invoice(self, tenant: str, invoice_id: int) -> dict
    def list_invoices(self, tenant: str, filters: dict) -> list[dict]

    # Lifecycle
    def send_invoice(self, tenant: str, invoice_id: int, options: dict) -> dict
    def create_credit_note(self, tenant: str, original_invoice_id: int) -> dict
    def mark_paid(self, tenant: str, invoice_id: int, paid_at: datetime) -> dict
    def mark_overdue(self, tenant: str) -> int  # batch: update all past-due 'sent' invoices

    # Copy last invoice (recurring)
    def copy_last_invoice(self, tenant: str, contact_id: int) -> dict

    # Numbering
    def _generate_invoice_number(self, tenant: str, prefix: str, year: int) -> str

    # Calculations
    def _calculate_line(self, tenant: str, line: dict, invoice_date: date) -> dict
    def _calculate_totals(self, invoice_id: int, lines: list[dict]) -> dict

    # Time entries (optional convenience — invoices never require time entries)
    def create_invoice_from_time_entries(self, tenant: str, contact_id: int,
                                          entry_ids: list[int], data: dict) -> dict
```

#### Copy Last Invoice (Req 13)

```python
def copy_last_invoice(self, tenant, contact_id):
    """Create a new draft by copying the most recent invoice for a contact."""
    last = self.db.execute_query(
        """SELECT * FROM invoices
           WHERE administration = %s AND contact_id = %s
           ORDER BY invoice_date DESC LIMIT 1""",
        (tenant, contact_id), fetch=True
    )
    if not last:
        raise ValueError("No previous invoice found for this contact")

    last_invoice = last[0]
    last_lines = self.db.execute_query(
        "SELECT * FROM invoice_lines WHERE invoice_id = %s ORDER BY sort_order",
        (last_invoice['id'],), fetch=True
    )

    # Auto-advance date based on gap between last two invoices (or default +1 month)
    new_date = self._advance_date(tenant, contact_id, last_invoice['invoice_date'])

    # Create new draft with copied data
    new_invoice = self.create_invoice(tenant, {
        'contact_id': contact_id,
        'invoice_date': new_date.isoformat(),
        'payment_terms_days': last_invoice['payment_terms_days'],
        'currency': last_invoice['currency'],
        'notes': last_invoice.get('notes'),
        'lines': [
            {
                'product_id': line.get('product_id'),
                'description': line['description'],
                'quantity': line['quantity'],
                'unit_price': float(line['unit_price']),
                'vat_code': line['vat_code'],
                'sort_order': line.get('sort_order', 0),
            }
            for line in last_lines
        ]
    }, created_by='copy')

    new_invoice['copied_from_invoice_id'] = last_invoice['id']
    return new_invoice
```

Uses `SELECT ... FOR UPDATE` row-level locking to prevent concurrent duplicates:

```python
def _generate_invoice_number(self, tenant, prefix, year):
    """Generate next invoice number with database-level locking."""
    conn = self.db.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("START TRANSACTION")
        cursor.execute("""
            SELECT last_sequence FROM invoice_number_sequences
            WHERE administration = %s AND prefix = %s AND year = %s
            FOR UPDATE
        """, (tenant, prefix, year))
        row = cursor.fetchone()

        if row:
            next_seq = row['last_sequence'] + 1
            cursor.execute("""
                UPDATE invoice_number_sequences SET last_sequence = %s
                WHERE administration = %s AND prefix = %s AND year = %s
            """, (next_seq, tenant, prefix, year))
        else:
            next_seq = 1
            cursor.execute("""
                INSERT INTO invoice_number_sequences (administration, prefix, year, last_sequence)
                VALUES (%s, %s, %s, %s)
            """, (tenant, prefix, year, next_seq))

        conn.commit()
        padding = self.parameter_service.get_param('zzp', 'invoice_number_padding', tenant=tenant) or 4
        return f"{prefix}-{year}-{str(next_seq).zfill(padding)}"
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
```

#### Line Calculation (Req 4.3–4.5)

```python
def _calculate_line(self, tenant, line, invoice_date):
    rate_info = self.tax_rate_service.get_tax_rate(tenant, 'btw', line['vat_code'], invoice_date)
    vat_rate = rate_info['rate'] if rate_info else 0.0
    line_total = round(line['quantity'] * line['unit_price'], 2)
    vat_amount = round(line_total * vat_rate / 100, 2)
    return {**line, 'vat_rate': vat_rate, 'line_total': line_total, 'vat_amount': vat_amount}
```

#### VAT Summary & Totals Calculation (Req 4.5)

VAT summary is read from the `vw_invoice_vat_summary` view (derived from `invoice_lines`). The service only needs to update the invoice header totals.

```python
def _calculate_totals(self, invoice_id, lines):
    """Calculate invoice totals from lines. VAT summary comes from the view."""
    subtotal = round(sum(l['line_total'] for l in lines), 2)
    vat_total = round(sum(l['vat_amount'] for l in lines), 2)
    grand_total = round(subtotal + vat_total, 2)

    # Update invoice header totals
    self.db.execute_query(
        "UPDATE invoices SET subtotal=%s, vat_total=%s, grand_total=%s WHERE id=%s",
        (subtotal, vat_total, grand_total, invoice_id),
        fetch=False, commit=True
    )

    # Read VAT summary from view (always in sync with lines)
    vat_summary = self.db.execute_query(
        "SELECT vat_code, vat_rate, base_amount, vat_amount FROM vw_invoice_vat_summary WHERE invoice_id = %s",
        (invoice_id,), fetch=True
    )

    return {
        'subtotal': subtotal,
        'vat_total': vat_total,
        'grand_total': grand_total,
        'vat_summary': vat_summary
    }
```

#### Send Invoice Flow (Req 6, 8, 9)

```python
def send_invoice(self, tenant, invoice_id, options):
    """Send invoice or credit note — same flow for both types."""
    invoice = self.get_invoice(tenant, invoice_id)
    assert invoice['status'] == 'draft'
    is_credit_note = invoice['invoice_type'] == 'credit_note'

    # 1. Generate PDF
    pdf_bytes = self.pdf_generator.generate_invoice_pdf(tenant, invoice)

    # 2. Store PDF via OutputService (returns url + filename)
    storage_result = self._store_pdf(tenant, invoice, pdf_bytes, options.get('output_destination', 'gdrive'))

    # 3. Book in FIN (double-entry) — credit notes create reversal entries
    if is_credit_note:
        original = self.get_invoice(tenant, invoice['original_invoice_id'])
        self.booking_helper.book_credit_note(tenant, invoice, original, storage_result)
        # Update original invoice status to 'credited'
        self._update_status(tenant, invoice['original_invoice_id'], 'credited')
    else:
        self.booking_helper.book_outgoing_invoice(tenant, invoice, storage_result)

    # 4. Send email (optional)
    if options.get('send_email', True):
        self.email_service.send_invoice_email(tenant, invoice, [
            {'filename': f"{invoice['invoice_number']}.pdf", 'content': pdf_bytes.getvalue(), 'content_type': 'application/pdf'}
        ])

    # 5. Update invoice/credit note status to 'sent'
    self._update_status(tenant, invoice_id, 'sent', sent_at=datetime.utcnow())

    return {'success': True, 'invoice_number': invoice['invoice_number']}
```

### 5.4 InvoiceBookingHelper (`backend/src/services/invoice_booking_helper.py`)

Shared helper that creates `mutaties` entries using double-entry bookkeeping. Follows the `TransactionLogic.save_approved_transactions()` pattern.

```python
class InvoiceBookingHelper:
    def __init__(self, db: DatabaseManager, transaction_logic: TransactionLogic,
                 parameter_service: ParameterService):
        self.db = db
        self.transaction_logic = transaction_logic
        self.parameter_service = parameter_service

    def book_outgoing_invoice(self, tenant: str, invoice: dict, storage_result: dict = None) -> list[dict]
    def book_incoming_invoice(self, tenant: str, invoice: dict, storage_result: dict = None) -> list[dict]
    def book_credit_note(self, tenant: str, credit_note: dict, original_invoice: dict, storage_result: dict = None) -> list[dict]
```

#### Outgoing Invoice Booking (Req 6.3)

For an invoice with contact `ACME`, invoice number `INV-2026-0001`, two lines: €15,200 at 21% VAT (€3,192) and €500 at 9% VAT (€45):

| #   | TransactionDescription     | Amount   | Debet | Credit | ReferenceNumber | Ref2          | Ref3      | Ref4       |
| --- | -------------------------- | -------- | ----- | ------ | --------------- | ------------- | --------- | ---------- |
| 1   | Factuur INV-2026-0001 ACME | 18837.00 | 1300  | 8001   | ACME            | INV-2026-0001 | {pdf_url} | {filename} |
| 2   | BTW Hoog 21% INV-2026-0001 | 3192.00  | 2010  | 2021   | ACME            | INV-2026-0001 |           |            |
| 3   | BTW Laag 9% INV-2026-0001  | 45.00    | 2010  | 2020   | ACME            | INV-2026-0001 |           |            |

The booking helper reads `vw_invoice_vat_summary` and creates one `mutaties` entry per VAT rate bucket. The Credit account on BTW lines is **not hardcoded** — it comes from `TaxRateService.get_tax_rate(tenant, 'btw', vat_code, invoice_date)` which returns the `ledger_account` per rate (e.g. `2021` for high, `2020` for low in GoodwinSolutions). This is tenant-specific and driven by the `tax_rates` table.

Mapping to `mutaties` columns:

- `TransactionNumber`: auto-generated by `TransactionLogic`
- `TransactionDate`: invoice date
- `Debet`/`Credit`: from tenant's `rekeningschema` — debtor account (param `zzp.debtor_account`, default `1300`) and revenue account (from product's chart mapping)
- `Debet`/`Credit` on BTW lines: Debet = `2010` (Betaalde BTW), Credit = `ledger_account` from `TaxRateService` per VAT code (e.g. `2021` for high, `2020` for low) — tenant-specific, driven by `tax_rates` table
- `ReferenceNumber`: contact's `client_id` (for bank payment matching)
- `Ref2`: invoice number (for traceability)
- `Ref3`: PDF storage URL
- `Ref4`: PDF filename
- `Administration`: tenant

Zero-amount lines (e.g., zero-rate VAT) are skipped per existing `save_approved_transactions()` behavior (Req 6.10).

#### Incoming Invoice Booking (Req 6.4)

| #   | TransactionDescription     | Amount    | Debet          | Credit | ReferenceNumber | Ref2             |
| --- | -------------------------- | --------- | -------------- | ------ | --------------- | ---------------- |
| 1   | Inkoopfactuur {number}     | amount    | {expense_acct} | 1600   | {client_id}     | {invoice_number} |
| 2   | BTW Voorbelasting {number} | total_vat | 2010           | 1600   | {client_id}     | {invoice_number} |

Incoming invoices book a single VAT line for the total VAT amount against the Betaalde BTW account (`2010`, or tenant-specific via `TaxRateService.ledger_account`). No split per rate — the rate detail lives on `invoice_lines`. Zero VAT is skipped.

### 5.5 PaymentCheckHelper (`backend/src/services/payment_check_helper.py`)

Matches bank transactions against open invoices (Req 7). Leverages the existing `ReferenceNumber` field which contains the contact's `client_id`.

```python
class PaymentCheckHelper:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def run_payment_check(self, tenant: str) -> dict
    def _find_matching_invoices(self, tenant: str, bank_txn: dict) -> list[dict]
    def _match_amount(self, bank_amount: float, invoice_total: float, tolerance: float = 0.01) -> str
```

Algorithm:

1. Query `mutaties` for recent bank transactions (credit = bank account, `administration = tenant`)
2. For each bank transaction, extract `ReferenceNumber` (= `client_id`)
3. Query `invoices` where `contact.client_id` matches and `status IN ('sent', 'overdue')`
4. Compare `TransactionAmount` with `invoice.grand_total`:
   - Exact match (within €0.01): update invoice status to `'paid'`, set `paid_at`
   - Partial match: record partial payment, keep status as `'sent'`
5. Return summary of matched/unmatched

### 5.6 PDFGeneratorService (`backend/src/services/pdf_generator_service.py`)

HTML-to-PDF conversion using `weasyprint` (Req 8). Extends the existing `TemplateService._generate_pdf()` placeholder.

```python
class PDFGeneratorService:
    def __init__(self, db: DatabaseManager, template_service: TemplateService,
                 parameter_service: ParameterService):
        self.db = db
        self.template_service = template_service
        self.parameter_service = parameter_service

    def generate_invoice_pdf(self, tenant: str, invoice: dict) -> BytesIO
    def generate_copy_invoice_pdf(self, tenant: str, invoice: dict) -> BytesIO
    def _render_html(self, tenant: str, invoice: dict, is_copy: bool = False) -> str
    def _get_tenant_logo(self, tenant: str) -> str | None
```

Implementation approach:

1. Load HTML template via `TemplateService.get_template_metadata(tenant, 'zzp_invoice')` with fallback to a default template in `backend/src/templates/zzp_invoice_default.html`
2. Render HTML with invoice data using `TemplateService.apply_field_mappings()`
3. Inject tenant logo (from parameter `zzp.company_logo_url` or tenant config)
4. Convert to PDF using `weasyprint.HTML(string=html).write_pdf()`
5. Return `BytesIO` object

New dependency: `weasyprint` added to `requirements.txt`.

### 5.7 InvoiceEmailService (`backend/src/services/invoice_email_service.py`)

Sends invoice emails with PDF attachment via `SESEmailService` (Req 9).

```python
class InvoiceEmailService:
    def __init__(self, parameter_service: ParameterService):
        self.parameter_service = parameter_service

    def send_invoice_email(self, tenant: str, invoice: dict, attachments: list[tuple]) -> dict
    def send_reminder_email(self, tenant: str, invoice: dict) -> dict
    def _build_email_body(self, tenant: str, invoice: dict, template_type: str) -> tuple[str, str]
```

#### Email Tracking & Delivery

Three layers of tracking, all leveraging existing infrastructure:

1. **`email_log` table** (existing) — `SESEmailService` already calls `EmailLogService.log_sent()` / `log_failed()` on every send. This records: recipient, email_type (`invoice`, `reminder`), subject, SES message ID, administration, timestamp, sent_by, and status. The ZZP module uses `email_type='invoice'` and `email_type='reminder'`.

2. **BCC copy to tenant** — configurable via parameter `zzp.invoice_email_bcc` (default: empty). When set to the tenant's own email address, every invoice/reminder email includes a BCC copy so the user has a complete record in their own mailbox with the exact content and attachments the client received.

3. **SES delivery notifications** (existing) — the `SES_CONFIGURATION_SET` env var enables delivery/bounce/complaint tracking via AWS SNS. The existing `aws_notifications.py` handles these events.

#### Email Content Storage

The email body (HTML) is not stored separately — it can always be regenerated from the invoice data + template. The PDF attachment is stored via `OutputService` (referenced in `mutaties.Ref3`). The `email_log` table stores the subject and SES message ID for audit.

#### SES Extension for Attachments

The existing `SESEmailService.send_email()` uses `ses.send_email()` which does not support attachments. For invoice emails with PDF attachments, we extend `SESEmailService` with `send_email_with_attachments()`:

```python
# Extension to SESEmailService
def send_email_with_attachments(self, to_email, subject, html_body,
                                 attachments: list[dict],
                                 bcc: list[str] = None, **kwargs) -> dict:
    """
    Send email with file attachments via SES send_raw_email.
    attachments: [{'filename': str, 'content': bytes, 'content_type': str}]
    bcc: optional list of BCC addresses (e.g. tenant's own email)
    """
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = f'myAdmin <{self.sender}>'
    msg['To'] = to_email
    if bcc:
        msg['Bcc'] = ', '.join(bcc)

    body = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(body)

    for att in attachments:
        part = MIMEApplication(att['content'])
        part.add_header('Content-Disposition', 'attachment', filename=att['filename'])
        msg.attach(part)

    destinations = [to_email] + (bcc or [])
    response = self.client.send_raw_email(
        Source=msg['From'],
        Destinations=destinations,
        RawMessage={'Data': msg.as_string()}
    )
    return {'success': True, 'message_id': response.get('MessageId')}
```

The `InvoiceEmailService` reads `zzp.invoice_email_bcc` from `ParameterService` and passes it as the `bcc` parameter.

### 5.8 TimeTrackingService (`backend/src/services/time_tracking_service.py`)

```python
class TimeTrackingService:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def create_entry(self, tenant: str, data: dict, created_by: str) -> dict
    def update_entry(self, tenant: str, entry_id: int, data: dict) -> dict
    def delete_entry(self, tenant: str, entry_id: int) -> bool
    def list_entries(self, tenant: str, filters: dict) -> list[dict]
    def get_unbilled_entries(self, tenant: str, contact_id: int) -> list[dict]
    def mark_as_billed(self, tenant: str, entry_ids: list[int], invoice_id: int) -> int
    def get_summary(self, tenant: str, group_by: str, period: str) -> list[dict]
    def import_timesheet(self, tenant: str, file_bytes: bytes, contact_id: int,
                          file_type: str) -> list[dict]  # Phase 2
```

Summary grouping options: `contact`, `project`, `period` (week/month/quarter/year).

## 6. Frontend Design

### 6.1 Navigation & Routing

The ZZP module adds a new navigation section visible only when the tenant has the ZZP module enabled. Routes are protected by `ProtectedRoute` with `requiredPermission="zzp_read"`.

```
/zzp/invoices          → ZZPInvoices.tsx
/zzp/invoices/:id      → ZZPInvoiceDetail.tsx
/zzp/time-tracking     → ZZPTimeTracking.tsx
/zzp/contacts          → ZZPContacts.tsx
/zzp/products          → ZZPProducts.tsx
/zzp/debtors           → ZZPDebtors.tsx
```

### 6.2 Page Components

All pages follow the established BankingProcessor pattern: Chakra UI `Table` with sortable headers, hover rows, row-click opens `Modal` for CRUD. Primary actions (Add, Export) in page header.

#### ZZPInvoices.tsx

- Table: invoice number, contact, date, due date, status (Badge), grand total
- Row click → `InvoiceDetailModal` (read-only for sent/paid, editable for draft)
- Header actions: `t('zzp.invoices.newInvoice')`, `t('zzp.invoices.export')`, filter by status/contact/date range
- Status badges: draft=gray, sent=blue, paid=green, overdue=red, credited=purple

#### ZZPContacts.tsx

- Table: client_id, company_name, contact_type (Badge: client=blue, supplier=orange, both=green, other=gray), contact_person, city, phone
- Row click → `ContactModal` with email sub-table
- Header actions: `t('zzp.contacts.newContact')`, filter dropdown by contact_type

#### ZZPProducts.tsx

- Table: product_code, name, type (Badge), unit_price, vat_code, unit_of_measure, external_reference, active
- Row click → `ProductModal`
- Header actions: `t('zzp.products.newProduct')`

#### ZZPTimeTracking.tsx

Only rendered when `zzp.time_tracking_enabled` = `true` for the tenant. Nav item hidden otherwise.

- **Mobile-first design**: responsive card layout on small screens, table on desktop
- Quick-add flow: contact dropdown + hours + date as primary fields, everything else expandable
- Table (desktop): date, contact, project, hours, rate, total, billable, billed
- Cards (mobile): date + contact as header, hours + total as body, swipe actions for edit/delete
- Row/card click → `TimeEntryModal`
- Header actions: `t('zzp.timeTracking.newEntry')`, `t('zzp.timeTracking.invoiceSelected')`
- Summary tabs: per contact, per project, per period (Recharts bar chart)
- Invoicing from time entries is a convenience shortcut — users can always create invoices directly without time entries

#### ZZPDebtors.tsx

- Two tabs: "Debiteuren" (receivables — contacts with `contact_type` = `client` or `both`) and "Crediteuren" (payables — contacts with `contact_type` = `supplier` or `both`)
- Aging analysis visualization (stacked bar chart via Recharts)
- Row click → shows related invoices
- Action: `t('zzp.debtors.sendReminder')` button per overdue invoice

#### Recurring Invoice UX (no separate page)

The `t('zzp.invoices.copyLast')` action lives on the ZZPInvoices page as a button per contact row, or as a repeat action in the invoice list. No separate page needed:

1. User clicks `t('zzp.invoices.copyLast')` on a contact → calls `POST /api/zzp/invoices/copy-last/<contact_id>`
2. New draft opens in `InvoiceDetailModal` with pre-filled lines from the last invoice
3. User adjusts hours/quantity, dates, or descriptions as needed
4. User saves or sends → normal flow

### 6.3 Shared Components

```
frontend/src/components/zzp/
  ├── InvoiceDetailModal.tsx    ← invoice view/edit with line items
  ├── InvoiceLineEditor.tsx     ← editable line items table
  ├── ContactModal.tsx          ← contact CRUD form
  ├── ProductModal.tsx          ← product CRUD form
  ├── TimeEntryModal.tsx        ← time entry form
  ├── InvoiceStatusBadge.tsx    ← status badge component
  └── AgingChart.tsx            ← aging analysis Recharts component
```

### 6.4 Service Layer

```
frontend/src/services/
  ├── zzpInvoiceService.ts      ← invoice API calls
  ├── contactService.ts         ← contact API calls (shared)
  ├── productService.ts         ← product API calls (shared)
  ├── timeTrackingService.ts    ← time entry API calls
  └── debtorService.ts          ← debtor/creditor API calls
```

Each service follows the existing pattern using `apiClient` with auth headers:

```typescript
export const getInvoices = async (
  filters?: InvoiceFilters,
): Promise<Invoice[]> => {
  const params = new URLSearchParams(filters as any);
  const response = await apiClient.get(`/api/zzp/invoices?${params}`);
  return response.data.data;
};
```

### 6.5 TypeScript Types

```
frontend/src/types/
  └── zzp.ts
```

```typescript
export type ContactType = "client" | "supplier" | "both" | "other";

export interface Contact {
  id: number;
  client_id: string;
  contact_type: ContactType;
  company_name: string;
  contact_person?: string;
  street_address?: string;
  postal_code?: string;
  city?: string;
  country?: string;
  vat_number?: string;
  kvk_number?: string;
  phone?: string;
  iban?: string;
  emails: ContactEmail[];
  is_active: boolean;
}

export interface ContactEmail {
  id: number;
  email: string;
  email_type: "general" | "invoice" | "other";
  is_primary: boolean;
}

export interface Product {
  id: number;
  product_code: string;
  external_reference?: string;
  name: string;
  description?: string;
  product_type: string;
  unit_price: number;
  vat_code: string;
  unit_of_measure: string;
  is_active: boolean;
}

export type InvoiceStatus =
  | "draft"
  | "sent"
  | "paid"
  | "overdue"
  | "cancelled"
  | "credited";
export type InvoiceType = "invoice" | "credit_note";

export interface Invoice {
  id: number;
  invoice_number: string;
  invoice_type: InvoiceType;
  contact: Contact;
  invoice_date: string;
  due_date: string;
  payment_terms_days: number;
  currency: string;
  exchange_rate: number;
  status: InvoiceStatus;
  lines: InvoiceLine[];
  subtotal: number;
  vat_summary: VatSummaryLine[];
  vat_total: number;
  grand_total: number;
  notes?: string;
  original_invoice_id?: number;
}

export interface InvoiceLine {
  id?: number;
  product_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  vat_code: string;
  vat_rate: number;
  vat_amount: number;
  line_total: number;
}

export interface VatSummaryLine {
  vat_code: string;
  vat_rate: number;
  base_amount: number;
  vat_amount: number;
}

export interface TimeEntry {
  id: number;
  contact_id: number;
  contact?: Contact;
  product_id?: number;
  project_name?: string;
  entry_date: string;
  hours: number;
  hourly_rate: number;
  description?: string;
  is_billable: boolean;
  is_billed: boolean;
  invoice_id?: number;
}
```

### 6.6 i18n

Translation keys under namespace `zzp`:

```
zzp.invoices.title
zzp.invoices.newInvoice
zzp.invoices.export
zzp.invoices.copyLast
zzp.invoices.status.draft / sent / paid / overdue / cancelled / credited
zzp.contacts.title
zzp.contacts.newContact
zzp.contacts.type.client / supplier / both / other
zzp.products.title
zzp.products.newProduct
zzp.timeTracking.title
zzp.timeTracking.newEntry
zzp.timeTracking.invoiceSelected
zzp.debtors.title
zzp.debtors.receivables / payables
zzp.debtors.aging
zzp.debtors.sendReminder
```

All UI labels use `t()` with these keys — no hardcoded strings in any language. Following conventions in `.kiro/steering/ui-patterns.md`.

## 7. Security

### 7.1 Authentication & Authorization

- All routes require `@cognito_required()` → JWT validation via AWS Cognito
- Tenant isolation via `@tenant_required()` → injects `tenant` from token
- Module gating via `@module_required('ZZP')` → checks `tenant_modules` table
- Permission granularity: `zzp_read`, `zzp_crud`, `zzp_export`, `zzp_tenant`

### 7.2 Data Isolation

- Every database query includes `WHERE administration = %s` with the tenant from decorator context
- Never trust client-provided tenant identifiers
- Contact and product services are shared but always scoped to the requesting tenant

### 7.3 Input Validation

- All SQL uses parameterized queries (`%s` placeholders)
- Invoice amounts validated server-side (recalculated from line items, never trusted from client)
- File uploads validated by extension and MIME type
- `client_id` sanitized: alphanumeric + hyphen/underscore, max 20 chars

### 7.4 Financial Integrity

- Invoice number generation uses `SELECT ... FOR UPDATE` to prevent race conditions
- Sent invoices are immutable (financial fields locked after status change)
- Credit notes create reversal entries, never modify original bookings
- All `mutaties` entries created via `TransactionLogic.save_approved_transactions()` for consistency

### 7.5 Email Security

- Emails sent via AWS SES with verified sender domain
- Email templates rendered server-side, no user-injectable HTML
- Attachment size limits enforced (max 10MB per email per SES limits)

## 8. Performance

### 8.1 Database Indexes

All new tables include indexes on:

- `administration` — tenant isolation queries
- `status`, `due_date`, `invoice_date` — filtering and aging queries
- `contact_id` — join queries
- `is_billed`, `entry_date` — time entry filtering

### 8.2 Query Optimization

- Invoice list queries use pagination (`LIMIT/OFFSET`) with default page size 50
- Aging analysis uses a single query with `CASE WHEN DATEDIFF(CURDATE(), due_date)` buckets
- Payment check runs as a batch operation, not per-transaction

### 8.3 Caching

- `TaxRateService` already caches rate lookups in-process
- `ParameterService` caches parameter values with write-through invalidation
- Invoice PDF generation is on-demand, stored result cached via `storage_url`

### 8.4 Connection Pooling

Uses existing `DatabaseManager` with scalability manager (20-connection pool) or legacy pool fallback.

## 9. Key Technical Decisions

| Decision                 | Choice                     | Rationale                                                                                                                                         |
| ------------------------ | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| PDF library              | weasyprint                 | Full CSS support, logo rendering, A4 layout. Existing `_generate_pdf` placeholder in TemplateService.                                             |
| Email attachments        | `send_raw_email` extension | Existing `send_email` uses simple SES API without attachment support. MIME multipart needed.                                                      |
| Invoice numbering        | DB row-level locking       | `SELECT ... FOR UPDATE` prevents concurrent duplicate numbers. Simpler than application-level locks.                                              |
| Product types            | Parameter-driven           | Stored in `ParameterService` (namespace `zzp`, key `product_types`). New types added without schema changes.                                      |
| Contact types            | Parameter-driven           | Stored in `ParameterService` (namespace `zzp`, key `contact_types`). Default: client, supplier, both, other. Extensible without schema changes.   |
| Field visibility         | Parameter-driven (3-tier)  | Per-entity field config: `required`/`optional`/`hidden`. Tenant overrides via ParameterService. Backend mixin + frontend hook. No schema changes. |
| Contact/Product services | Shared (not ZZP-specific)  | Future modules (Webshop, Logistics) will reuse these. Separate blueprints, no ZZP import dependency.                                              |
| Recurring invoices       | Copy last invoice action   | No config table, no scheduler. User selects contact, system copies last invoice as draft. Minimizes work, not storage.                            |
| Multi-currency           | Exchange rate snapshot     | Rate stored at invoice creation time. Conversion to default currency for FIN booking. No live rate API (manual entry).                            |

## 10. Dependencies & New Packages

### Backend

| Package    | Version | Purpose                                           |
| ---------- | ------- | ------------------------------------------------- |
| weasyprint | >=60.0  | HTML-to-PDF conversion with CSS and image support |

All other dependencies are already in `requirements.txt`.

### Frontend

No new packages required. Uses existing Chakra UI, Recharts, Formik/Yup.

## 11. Migration Plan

### SQL Migration Script: `backend/sql/phase_zzp_tables.sql`

Creates all tables in order respecting foreign key dependencies:

1. `contacts`
2. `contact_emails`
3. `products`
4. `invoices`
5. `invoice_lines`
6. `vw_invoice_vat_summary` (view)
7. `invoice_number_sequences`
8. `time_entries`

### Module Activation

After running the migration, activate ZZP for a tenant:

```sql
INSERT INTO tenant_modules (administration, module_name, is_active, created_by)
VALUES ('InterimManagement', 'ZZP', TRUE, 'system')
ON DUPLICATE KEY UPDATE is_active = TRUE;
```

Then seed default parameters:

```python
parameter_service.seed_module_params('InterimManagement', 'ZZP')
```

## 12. File Structure

```
backend/src/
  ├── routes/
  │   ├── zzp_routes.py              ← ZZP invoice, time, debtor, recurring routes
  │   ├── contact_routes.py          ← Shared contact CRUD routes
  │   └── product_routes.py          ← Shared product CRUD routes
  ├── services/
  │   ├── zzp_invoice_service.py     ← Invoice lifecycle, numbering, calculations
  │   ├── contact_service.py         ← Shared contact CRUD
  │   ├── product_service.py         ← Shared product CRUD
  │   ├── field_config_mixin.py      ← Shared field visibility/validation mixin
  │   ├── invoice_booking_helper.py  ← Double-entry booking in mutaties
  │   ├── payment_check_helper.py    ← Bank payment matching
  │   ├── pdf_generator_service.py   ← HTML→PDF via weasyprint
  │   ├── invoice_email_service.py   ← Invoice email with attachments
  │   └── time_tracking_service.py   ← Time entry CRUD and summaries
  ├── templates/
  │   └── zzp_invoice_default.html   ← Default invoice HTML template
  └── sql/
      └── phase_zzp_tables.sql       ← Database migration

frontend/src/
  ├── pages/
  │   ├── ZZPInvoices.tsx
  │   ├── ZZPInvoiceDetail.tsx
  │   ├── ZZPTimeTracking.tsx
  │   ├── ZZPContacts.tsx
  │   ├── ZZPProducts.tsx
  │   └── ZZPDebtors.tsx
  ├── components/zzp/
  │   ├── InvoiceDetailModal.tsx
  │   ├── InvoiceLineEditor.tsx
  │   ├── ContactModal.tsx
  │   ├── ProductModal.tsx
  │   ├── TimeEntryModal.tsx
  │   ├── InvoiceStatusBadge.tsx
  │   └── AgingChart.tsx
  ├── hooks/
  │   └── useFieldConfig.ts          ← shared field visibility/required hook
  ├── services/
  │   ├── zzpInvoiceService.ts
  │   ├── contactService.ts
  │   ├── productService.ts
  │   ├── timeTrackingService.ts
  │   ├── debtorService.ts
  │   └── fieldConfigService.ts      ← field config API calls
  └── types/
      └── zzp.ts
```

## 13. Cross-References

- Module registry pattern: `backend/src/services/module_registry.py`
- Parameter system: `backend/src/services/parameter_service.py`
- Tax rate lookups: `backend/src/services/tax_rate_service.py`
- Transaction writing: `backend/src/transaction_logic.py` → `save_approved_transactions()`
- Template rendering: `backend/src/services/template_service.py`
- Output/storage: `backend/src/services/output_service.py`
- Email delivery: `backend/src/services/ses_email_service.py`
- Tenant modules SQL: `backend/sql/phase5_tenant_modules.sql`
- UI patterns (tables, modals, action buttons, filters, i18n): `.kiro/steering/ui-patterns.md`
- testing standards: .kiro\steering\testing-standards.md
