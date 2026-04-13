# Parameter-Driven Configuration — Analysis & Directions

## Current State

In the current approach many items are hardcoded:

- Making it parameter driven would make the system more flexible and tenant friendly
- Parameters by tenant and parameters by tenant role

---

## What would be a solid approach anno 2026?

The modern approach is a **layered configuration hierarchy** with database-backed parameters, resolved at runtime per tenant and role. The pattern is well-established in SaaS platforms:

```
System Defaults → Tenant Overrides → Role Overrides → User Preferences
```

Each layer only stores what it explicitly overrides. Resolution walks the chain and returns the first match.

### Recommended Architecture: Feature Flags + Typed Parameters

1. **Unified Parameter Store** — A single `parameters` table (or extend the existing `tenant_config`) with:
   - `scope` (system / tenant / role / user)
   - `scope_id` (null for system, tenant name, role name, user email)
   - `namespace` (e.g. `storage`, `ledger`, `ui`, `processing`)
   - `key` (e.g. `invoice_storage_provider`, `default_download_folder`)
   - `value` (JSON — supports strings, numbers, booleans, objects)
   - `value_type` (string, number, boolean, json) for validation
   - `is_secret` (boolean — triggers encryption via CredentialService)

2. **Parameter Resolution Service** — A Python service that resolves parameters with inheritance:

   ```python
   def get_param(namespace, key, tenant, role=None, user=None) -> Any:
       # Check user → role → tenant → system defaults
       # Return first match with caching
   ```

3. **Admin UI** — Extend the existing Tenant Admin config page to show parameters grouped by namespace, with override indicators showing which level a value comes from.

4. **Caching** — In-memory cache with TTL (already have `QueryCache` pattern in `duplicate_query_optimizer.py`). Invalidate on write.

### Best Practices in 2026

The industry has converged on several clear patterns for multi-tenant configuration management:

**1. Database-driven over environment variables**
Environment variables are deployment-level — they require server restarts and engineer intervention to change. The 2026 consensus is to store runtime configuration in the database, exposing it via API endpoints so stakeholders can update settings without touching servers. This is exactly what [Cowrywise documented](https://engineering.cowrywise.com/article/optimising-configuration-management-a-case-study-on-database-driven-solutions) in their migration from env vars to a database-backed singleton config model. Content was rephrased for compliance with licensing restrictions.

**2. Tiered/layered configuration hierarchy**
The dominant pattern across SaaS platforms is a [4-tier configuration hierarchy](https://antler.digital/blog/5-strategies-for-tenant-configuration-in-saas): global defaults → tier/plan settings → tenant overrides → user preferences. Resolution walks from most specific to least specific, returning the first match. This is the approach recommended by both AWS and industry practitioners. Content was rephrased for compliance with licensing restrictions.

**3. Tagged storage pattern (AWS, June 2025)**
AWS published a [reference architecture](https://aws.amazon.com/blogs/architecture/build-a-multi-tenant-configuration-system-with-tagged-storage-patterns/) for multi-tenant configuration using key prefixes to route config requests to the appropriate storage backend. The core idea: use the Strategy pattern so different config types can use different storage (e.g. DynamoDB for high-frequency access, Parameter Store for hierarchical config). For our scale, MySQL with JSON columns is the right single backend — but the Strategy pattern for storage providers is directly applicable to our invoice storage abstraction. Content was rephrased for compliance with licensing restrictions.

**4. Event-driven cache invalidation over TTL**
Rather than relying on cache TTL (which forces a tradeoff between staleness and performance), the modern approach uses event-driven invalidation: write to the parameter store, emit an event, subscribers invalidate their cache immediately. For our scale, a simple in-process cache with write-through invalidation is sufficient — no need for Redis or EventBridge.

**5. Dynamic feature flagging per tenant**
Feature flags are now considered a subset of tenant configuration, not a separate system. The recommendation is to keep them in the same parameter store with a `features` namespace, rather than introducing a separate service like LaunchDarkly. This keeps the operational footprint small.

**What this means for myAdmin:**

- We already have the right foundation (`tenant_config` table, `CredentialService`, `rekeningschema.parameters` JSON column)
- The gap is a proper resolution service with layered inheritance and caching
- No need for external services — database-backed with in-process cache fits our scale perfectly
- The Strategy pattern for storage providers aligns with both the AWS reference architecture and our invoice storage abstraction needs

---

## Where in the code could we already benefit?

### 1. Hardcoded Tenant Names

- `duplicate_detection_routes.py` line 250: `'Administration': 'GoodwinSolutions2024'` — hardcoded default administration
- `toeristenbelasting_processor.py` line 48: `administration = raw_data.get('administration', 'GoodwinSolutions')` — hardcoded fallback

### 2. Hardcoded File Paths

- `xlsx_export.py` line 30: `self.default_output_base_path = r'C:\Users\peter\OneDrive\Admin\reports'` — local Windows path
- `str_processor.py` line 13: `self.download_folder = "C:\\Users\\peter\\Downloads"` — local download folder

### 3. Hardcoded Google Drive Folder IDs

- `google_drive_service.py` line 166: `os.getenv('FACTUREN_FOLDER_ID', '0B9OBNkcEDqv...')` — fallback folder ID baked into code

### 4. Hardcoded Vendor Folder Mappings

- `config.py`: `self.vendor_folders` dictionary with hardcoded vendor-to-folder mappings — should be tenant-configurable

### 5. Storage Provider Selection

- Currently only Google Drive is supported as invoice storage. The provider choice should be a tenant parameter.

### 6. Report Output Paths

- `xlsx_export.py`: Output paths differ between Docker and local dev but are hardcoded in both cases. Should be a system/tenant parameter.

### Quick Wins (low effort, high value):

- Replace hardcoded tenant fallbacks with `get_tenant_config()` lookups (already exists in `tenant_context.py`)
- Move Google Drive folder IDs to `tenant_config` table (already have the CRUD routes)
- Move file paths to system-level parameters

---

## How does the Ledger account parameters fit?

You already have a strong foundation here. The `rekeningschema` table has a `parameters` JSON column that's actively used:

### Current Usage

- **Year-end config** (`year_end_config.py`): Stores `purpose` (equity_result, pl_closing) in `parameters`
- **VAT netting** (`year_end_config.py`): Stores `vat_netting` and `vat_primary` flags in `parameters`
- **Chart of accounts provisioning** (`tenant_provisioning_service.py`): Loads from JSON templates per locale, includes `parameters` field

### How it fits in the parameter-driven approach

The `rekeningschema.parameters` JSON column is essentially **account-level parameters** — it's already parameter-driven at the account level. The natural extension is:

1. **Account-level parameters** (already working) — `rekeningschema.parameters` JSON column
   - Purpose assignments, VAT netting, custom flags per account
2. **Tenant-level ledger parameters** (new) — in the unified parameter store
   - `ledger.default_debet_account` — default debet for unmatched transactions
   - `ledger.default_credit_account` — default credit for unmatched transactions
   - `ledger.fiscal_year_start_month` — not all tenants use Jan-Dec
   - `ledger.currency` — default currency
   - `ledger.auto_assign_patterns` — enable/disable pattern-based auto-assignment

3. **Keep both layers** — account-level params in `rekeningschema.parameters`, tenant-level ledger config in the parameter store. They serve different purposes and the current JSON approach in `rekeningschema` is clean.

---

## How can we parameterize the storage of Invoices?

### Current Implementation

- Tenant-specific Google Drive storage via `GoogleDriveService`
- Credentials stored encrypted in `tenant_credentials` table via `CredentialService`
- OAuth flow per tenant via `google_drive_oauth_routes.py`
- Folder ID from env var with hardcoded fallback

### Storage Abstraction Pattern (Strategy Pattern)

```python
class StorageProvider(ABC):
    @abstractmethod
    def upload(self, file_data, path, metadata) -> str:  # returns URL/reference
    @abstractmethod
    def download(self, reference) -> bytes:
    @abstractmethod
    def delete(self, reference) -> bool:
    @abstractmethod
    def list_files(self, path) -> List[dict]:

class GoogleDriveStorage(StorageProvider): ...   # wraps existing GoogleDriveService
class S3TenantStorage(StorageProvider): ...      # tenant-specific S3 bucket
class S3SharedStorage(StorageProvider): ...      # shared bucket with tenant prefixes
```

A factory resolves the provider from tenant config:

```python
def get_storage_provider(tenant: str) -> StorageProvider:
    provider_type = get_param('storage', 'invoice_provider', tenant)
    # 'google_drive' | 's3_tenant' | 's3_shared'
    # instantiate and return the right provider
```

### Option Comparison

| Aspect           | Google Drive (current)      | Tenant S3 Buckets          | Shared S3 + Prefixes                     |
| ---------------- | --------------------------- | -------------------------- | ---------------------------------------- |
| Isolation        | Full (separate Drive)       | Full (separate bucket)     | Logical (prefix-based)                   |
| Cost             | Free tier per tenant        | Higher (bucket per tenant) | Lowest (shared + Intelligent Tiering)    |
| Setup complexity | High (OAuth per tenant)     | Medium (IAM per tenant)    | Low (one bucket, IAM policies)           |
| Scalability      | Limited by Drive API quotas | Good                       | Best                                     |
| Migration effort | N/A (current)               | Medium                     | Medium                                   |
| Compliance       | Depends on Google           | Full AWS control           | Full AWS control                         |
| Backup/lifecycle | Manual                      | S3 lifecycle rules         | S3 lifecycle rules + Intelligent Tiering |

### Recommended Direction

**Short term**: Keep Google Drive as default, but abstract behind `StorageProvider` interface. Move folder IDs from env vars to `tenant_config`.

**Medium term**: Add S3 shared storage with Intelligent Tiering as the recommended option for new tenants:

- Bucket: `myadmin-invoices-{environment}` (e.g. `myadmin-invoices-prod`)
- Key pattern: `{tenant}/{referenceNumber}/{uuid}_{filename}`
- IAM policy scoped to tenant prefix
- S3 Intelligent Tiering handles hot/warm/cold automatically
- Lifecycle rule: move to Glacier Deep Archive after 7 years (Dutch fiscal retention)
- S3 stores `LastModified` timestamp automatically on every object — no need for date in key path

**Long term**: Migrate existing tenants from Google Drive to S3 shared storage when ready, with a migration script that preserves references in `mutaties`.

### Tenant Config Parameters for Storage

```
storage.invoice_provider = "google_drive" | "s3_shared" | "s3_tenant"
storage.google_drive_folder_id = "0B9OBNkcEDqv..."
storage.s3_bucket = "myadmin-invoices-prod"
storage.s3_region = "eu-west-1"
storage.retention_years = 7
```

Credentials:

```
google_drive_oauth → per tenant (stored in tenant_credentials)
google_drive_token → per tenant (stored in tenant_credentials)

S3 shared → no per-tenant credentials. myAdmin's own AWS account/bucket.
             Backend uses IAM role or env-level access key.
             Tenant isolation via key prefix ({tenant}/...).

S3 tenant → per-tenant credentials needed. Bucket lives in the tenant's
             own AWS account. Requires cross-account access via either:
             - IAM role ARN (tenant grants assume-role to myAdmin) → preferred
             - Access key pair (tenant creates IAM user for myAdmin) → fallback
             Stored encrypted in tenant_credentials, same as Google Drive.
```

---

## How do modules (FIN, STR, future) fit in this model?

### Current Module Implementation

Modules today are simple on/off flags in the `tenant_modules` table:

- `tenant_modules` stores `(administration, module_name, is_active)`
- Hardcoded validation: `if module_name not in ['FIN', 'STR']` in `tenant_module_routes.py`
- Module check: `has_fin_module()` duplicated in both `tenant_admin_routes.py` and `chart_of_accounts_routes.py`
- Provisioning defaults to `['FIN', 'STR', 'TENADMIN']` in `sysadmin_provisioning.py`
- Role-to-module mapping is hardcoded: `Finance_*` → FIN, `STR_*` → STR in `get_user_module_roles()`

### The Problem

Module-specific configuration is scattered and hardcoded:

- **STR tax rates**: `vat_rate: 21.0`, `tourist_tax_rate: 6.9` hardcoded per platform in `str_processor.py` with date-based switching (pre/post 2024)
- **STR property config**: `aantal_kamers: 3`, `aantal_slaapplaatsen: 8` hardcoded in `toeristenbelasting_generator.py`
- **STR download folder**: `C:\Users\peter\Downloads` hardcoded in `str_processor.py`
- **FIN module check**: `has_fin_module()` function duplicated across files
- **Module list**: Adding a new module requires code changes in validation, provisioning, and role mapping

### How Modules Fit in the Parameter Store

Modules become a **namespace** in the parameter hierarchy. Each module owns its own parameter namespace:

```
Scope        Namespace          Key                        Value
─────────────────────────────────────────────────────────────────────
system       modules            available_modules          ["FIN", "STR", "TENADMIN"]
system       fin                default_currency           "EUR"
tenant       str                aantal_kamers              3
tenant       str                aantal_slaapplaatsen       8
tenant       str                download_folder            "/app/downloads"
tenant       fin                fiscal_year_start_month    1
tenant       fin                default_debet_account      "1300"
```

Note: VAT rates and tourist tax rates live in the `tax_rates` table (Shape 2+3), not here.

### Module Registry Pattern

Instead of hardcoding module names in validation logic, introduce a module registry. The registry lives **in code** (not in the database) — it's a developer artifact that defines the contract between a module and the parameter system. Adding a new module is always a development effort (routes, services, templates), so the registry entry is part of that same code change. The runtime data (which tenants have which modules enabled, parameter values) lives in the database.

```python
# System-level parameter: modules.available_modules
# Each module self-registers its required parameters with defaults

MODULE_REGISTRY = {
    'FIN': {
        'description': 'Financial Administration',
        'required_params': {
            'fin.default_currency': {'type': 'string', 'default': 'EUR'},
            'fin.fiscal_year_start_month': {'type': 'number', 'default': 1},
            'fin.default_debet_account': {'type': 'string', 'default': None},
            'fin.default_credit_account': {'type': 'string', 'default': None},
            'fin.locale': {'type': 'string', 'default': 'nl'},
        },
        'required_roles': ['Finance_Read', 'Finance_Write'],
    },
    'STR': {
        'description': 'Short-Term Rental Management',
        'required_params': {
            'str.aantal_kamers': {'type': 'number', 'default': None},
            'str.aantal_slaapplaatsen': {'type': 'number', 'default': None},
            'str.platforms': {'type': 'json', 'default': ['airbnb', 'booking']},
        },
        'required_tax_rates': ['tourist_tax', 'btw_accommodation'],
        'required_roles': ['STR_Read', 'STR_Write'],
    },
    'TENADMIN': {
        'description': 'Tenant Administration',
        'required_params': {},
        'required_roles': ['Tenant_Admin'],
        'always_active': True,
    }
}
```

### Adding a Future Module

With this pattern, adding a new module (e.g. `TAX` for tax declarations, or `CRM`) becomes:

1. Add entry to `MODULE_REGISTRY` with its parameter definitions and defaults
2. Create the module's routes/services (they read params via `get_param('tax', 'key', tenant)`)
3. No changes needed in validation, provisioning, or role mapping — the registry drives it all

### Module Access Check (Unified)

Replace the duplicated `has_fin_module()` with a generic check:

```python
def has_module(tenant: str, module_name: str) -> bool:
    """Check if tenant has a specific module enabled"""
    # Could also be cached via the parameter resolution service
    result = db.execute_query(
        "SELECT is_active FROM tenant_modules WHERE administration = %s AND module_name = %s",
        [tenant, module_name]
    )
    return result and result[0].get('is_active', False)

# Decorator for routes
def module_required(module_name: str):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            tenant = get_current_tenant(request)
            if not has_module(tenant, module_name):
                return jsonify({'error': f'{module_name} module not enabled'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# Usage:
@chart_of_accounts_bp.route('/api/tenant-admin/chart-of-accounts')
@cognito_required(required_roles=['Tenant_Admin'])
@module_required('FIN')
def list_accounts(user_email, user_roles):
    ...
```

### Module Provisioning

When a tenant enables a module, the system:

1. Sets `is_active = True` in `tenant_modules`
2. Seeds the module's required parameters with system defaults (from `MODULE_REGISTRY`)
3. Tenant admin can then override any parameter via the Admin UI

When a tenant disables a module:

1. Sets `is_active = False` — parameters are preserved (not deleted) for potential re-enablement

### Summary: Module Architecture

```
┌─────────────────────────────────────────────────┐
│                MODULE_REGISTRY                   │
│  Defines: params, defaults, roles per module     │
├─────────────────────────────────────────────────┤
│                                                  │
│  tenant_modules     → on/off per tenant          │
│  parameter_store    → module.key = value          │
│  @module_required   → route-level access check    │
│  get_param()        → runtime config resolution   │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## Time-Versioned Tax Rates (VAT codes, Tourist Tax, etc.)

### The Problem

Tax rates are not simple scalar values. They have two dimensions the current model ignores:

1. **Multiple codes per tax type** — NL has 3 BTW tariffs: Zero (0%), Low (9%), High (21%). Other EU countries have similar structures with different percentages.
2. **Rates change over time** — The STR VAT rate changed from 9% to 21% in 2026. Tourist tax went from 6.02% to 6.9%. These changes are currently handled with hardcoded date checks in `str_processor.py` and `str_channel_routes.py`.

Current hardcoded patterns:

- `str_processor.py`: `if checkin_date >= '2026-01-01': vat_rate = 21.0 else: vat_rate = 9.0`
- `str_channel_routes.py`: `if transaction_date >= rate_change_date: vat_account = '2020' else: vat_account = '2021'`
- `btw_processor.py`: Hardcoded account numbers `2010`, `2020`, `2021` for VAT accounts

### Solution: Tax Rate Table with Effective Dates

Tax rates don't belong in the flat parameter store — they need their own table with time-based versioning:

```sql
CREATE TABLE tax_rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    tax_type VARCHAR(30) NOT NULL,        -- 'btw', 'tourist_tax', 'income_tax'
    tax_code VARCHAR(20) NOT NULL,         -- 'zero', 'low', 'high' (for BTW)
                                           -- 'standard' (for tourist tax)
    rate DECIMAL(6,3) NOT NULL,            -- 0.000, 9.000, 21.000
    ledger_account VARCHAR(10),            -- '2010', '2021', '2020'
    effective_from DATE NOT NULL,           -- when this rate starts
    effective_to DATE DEFAULT '9999-12-31', -- when this rate ends (open-ended by default)
    country_code VARCHAR(2) DEFAULT 'NL',
    description VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),

    UNIQUE KEY uq_tax_rate (administration, tax_type, tax_code, effective_from),
    INDEX idx_lookup (administration, tax_type, effective_from, effective_to)
);
```

### Seed Data (NL defaults)

```sql
-- BTW rates (current NL)
INSERT INTO tax_rates (administration, tax_type, tax_code, rate, ledger_account, effective_from, description) VALUES
('_system_', 'btw', 'zero', 0.000, '2010', '2000-01-01', 'BTW 0% - Vrijgesteld'),
('_system_', 'btw', 'low',  9.000, '2021', '2000-01-01', 'BTW Laag tarief'),
('_system_', 'btw', 'high', 21.000, '2020', '2000-01-01', 'BTW Hoog tarief');

-- Tourist tax — NOT a system default, must be configured per tenant (municipality-specific)
-- Example: Haarlemmermeer tenant
INSERT INTO tax_rates (administration, tax_type, tax_code, rate, ledger_account, effective_from, effective_to, description) VALUES
('GoodwinSolutions', 'tourist_tax', 'standard', 6.020, NULL, '2000-01-01', '2025-12-31', 'Toeristenbelasting Haarlemmermeer oud tarief'),
('GoodwinSolutions', 'tourist_tax', 'standard', 6.900, NULL, '2026-01-01', '9999-12-31', 'Toeristenbelasting Haarlemmermeer nieuw tarief');

-- STR-specific: VAT on accommodation changed from low to high in 2026
INSERT INTO tax_rates (administration, tax_type, tax_code, rate, ledger_account, effective_from, effective_to, description) VALUES
('_system_', 'btw_accommodation', 'standard', 9.000, '2021', '2000-01-01', '2025-12-31', 'BTW verblijf laag tarief'),
('_system_', 'btw_accommodation', 'standard', 21.000, '2020', '2026-01-01', '9999-12-31', 'BTW verblijf hoog tarief');
```

### Resolution Service

```python
def get_tax_rate(administration: str, tax_type: str, tax_code: str,
                 reference_date: date) -> dict:
    """
    Get the applicable tax rate for a given date.

    Checks tenant-specific rates first, falls back to system defaults.

    Returns:
        {'rate': 21.0, 'ledger_account': '2020', 'description': 'BTW Hoog tarief'}
    """
    # Try tenant-specific first
    result = db.execute_query("""
        SELECT rate, ledger_account, description
        FROM tax_rates
        WHERE administration = %s AND tax_type = %s AND tax_code = %s
        AND effective_from <= %s AND effective_to >= %s
        ORDER BY effective_from DESC LIMIT 1
    """, [administration, tax_type, tax_code, reference_date, reference_date])

    if not result:
        # Fall back to system defaults
        result = db.execute_query("""
            SELECT rate, ledger_account, description
            FROM tax_rates
            WHERE administration = '_system_' AND tax_type = %s AND tax_code = %s
            AND effective_from <= %s AND effective_to >= %s
            ORDER BY effective_from DESC LIMIT 1
        """, [tax_type, tax_code, reference_date, reference_date])

    return result[0] if result else None


def get_all_vat_codes(administration: str, reference_date: date) -> list:
    """Get all active VAT codes for a tenant on a given date."""
    # Returns: [{'code': 'zero', 'rate': 0.0, 'account': '2010'}, ...]
```

### How This Replaces Current Hardcoding

| Current code                                                                 | Becomes                                                               |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `str_processor.py`: `if date >= '2026-01-01': vat_rate = 21.0`               | `get_tax_rate(tenant, 'btw_accommodation', 'standard', checkin_date)` |
| `str_channel_routes.py`: `if date >= rate_change_date: vat_account = '2020'` | `rate = get_tax_rate(...)` → `rate['ledger_account']`                 |
| `btw_processor.py`: hardcoded `['2010', '2020', '2021']`                     | `get_all_vat_codes(tenant, date)` → extract accounts                  |
| `toeristenbelasting_generator.py`: hardcoded tourist tax calc                | `get_tax_rate(tenant, 'tourist_tax', 'standard', date)`               |

### Tenant Overrides

A tenant in Belgium would override the system defaults:

```sql
INSERT INTO tax_rates (administration, tax_type, tax_code, rate, ledger_account, effective_from, description) VALUES
('BelgianTenant', 'btw', 'zero', 0.000, '2010', '2000-01-01', 'BTW 0%'),
('BelgianTenant', 'btw', 'low',  6.000, '2021', '2000-01-01', 'BTW 6%'),
('BelgianTenant', 'btw', 'mid', 12.000, '2022', '2000-01-01', 'BTW 12%'),
('BelgianTenant', 'btw', 'high', 21.000, '2020', '2000-01-01', 'BTW 21%');
```

Belgium has 4 VAT codes instead of 3 — the model handles this naturally because it's row-based, not column-based.

### Relationship to the Parameter Store

Tax rates are a **specialized extension** of the parameter store, not stored in it:

- **Parameter store**: flat key-value pairs with scope inheritance (good for settings, toggles, paths)
- **Tax rate table**: structured data with time dimension and multiple codes (needs its own table)
- **Both follow the same inheritance**: tenant overrides → system defaults
- **Both are managed via Admin UI**: tax rates get their own management screen

```
Parameter Store (flat)          Tax Rate Table (structured + temporal)
─────────────────────           ──────────────────────────────────────
fin.locale = "nl"               btw / zero  / 0%   / 2010 / _system_
fin.currency = "EUR"            btw / low   / 9%   / 2021 / _system_
str.platforms = [...]           btw / high  / 21%  / 2020 / _system_
storage.provider = "gdrive"     tourist_tax / 6.9% / tenant-specific
```

### Real-World Scenario: NL STR VAT Change 2026-01-01

The Dutch government moved STR accommodation from BTW low (9%) to BTW high (21%) effective 2026-01-01. The tourist tax rate also changed from 6.02% to 6.9% around the same time.

**What happened in the current codebase (without parameter-driven config):**

- `str_processor.py`: `get_tax_rates()` method duplicated twice (lines 22-60 and 132-160), both with `if checkin_dt >= date(2026, 1, 1)` branching
- `str_channel_routes.py`: Separate `rate_change_date = date(2026, 1, 1)` check with hardcoded account mapping
- Every future rate change requires finding and updating all these locations, testing, deploying

**What would happen with the `tax_rates` table:**

A SysAdmin or Tenant_Admin inserts two rows via the Admin UI (or a migration script):

```sql
-- Close the old accommodation rate
UPDATE tax_rates SET effective_to = '2025-12-31'
WHERE tax_type = 'btw_accommodation' AND tax_code = 'standard'
AND effective_from = '2000-01-01';

-- Add the new rate
INSERT INTO tax_rates
  (administration, tax_type, tax_code, rate, ledger_account, effective_from, description)
VALUES
  ('_system_', 'btw_accommodation', 'standard', 21.000, '2020', '2026-01-01',
   'BTW verblijf hoog tarief per 2026');
```

Zero code changes. Zero deployments. The `get_tax_rate()` function resolves the correct rate based on the transaction/checkin date automatically.

**Impact on existing processors:**

| File                              | Current                                       | After                                                                        |
| --------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------------- |
| `str_processor.py` (2 methods)    | 60+ lines of date branching, duplicated       | `rate = get_tax_rate(tenant, 'btw_accommodation', 'standard', checkin_date)` |
| `str_channel_routes.py`           | Hardcoded `rate_change_date`, account mapping | `rate = get_tax_rate(...)` → `rate['ledger_account']`                        |
| `btw_processor.py`                | Hardcoded `['2010', '2020', '2021']`          | `get_all_vat_codes(tenant, date)` → extract accounts                         |
| `toeristenbelasting_generator.py` | Hardcoded tourist tax calculation             | `get_tax_rate(tenant, 'tourist_tax', 'standard', date)`                      |

**Future rate changes** (e.g. government changes tourist tax again in 2028): insert a row, done. No developer needed.

**Historical accuracy**: Processing a 2024 booking still gets 9% because the query filters on `effective_from <= checkin_date AND effective_to >= checkin_date`. Retroactive corrections are also possible by adjusting date ranges.

---

## Tourist Tax: Municipality-Level Calculation Methods

### The Problem

Tourist tax (toeristenbelasting) is fundamentally different from BTW:

- **BTW** is national, uniform calculation method (percentage of price), 3 fixed codes
- **Tourist tax** is defined per municipality (gemeente), with different calculation methods:
  - **Percentage of revenue** minus VAT (current Haarlemmermeer approach: `(vat_exclusive / 106.9) * 6.9`)
  - **Fixed amount per guest per night** (e.g. Amsterdam: €12.50 per person per night in 2026)
  - **Percentage of room price** (some municipalities)
  - **Tiered** (different rates for different accommodation types)
- Rates and methods change over time, decided at municipal level

### Current Hardcoding

The current code assumes one calculation method everywhere:

- `str_processor.py`: `amount_tourist_tax = (vat_exclusive_amount / tourist_base) * tourist_tax_rate` — percentage-only formula
- `toeristenbelasting_generator.py`: `tourist_tax = (total_8003 / 106.2) * 6.2` — hardcoded percentage with hardcoded rate
- No concept of "per guest per night" or any other method

If a tenant operates in Amsterdam (fixed per night) instead of Haarlemmermeer (percentage), the current code produces wrong numbers.

### Solution: Extended Tax Rate Table with Calculation Method

The `tax_rates` table needs a `calc_method` and `calc_params` column for tourist tax:

```sql
ALTER TABLE tax_rates ADD COLUMN calc_method VARCHAR(30) DEFAULT 'percentage';
ALTER TABLE tax_rates ADD COLUMN calc_params JSON DEFAULT NULL;
```

Where `calc_method` is one of:

- `percentage` — rate is a % of the base amount (current behavior)
- `fixed_per_guest_night` — rate is a fixed € amount per guest per night
- `fixed_per_night` — rate is a fixed € amount per night (regardless of guests)
- `percentage_of_room_price` — rate is a % of room price only (excluding services)

And `calc_params` holds method-specific configuration:

```sql
-- Haarlemmermeer: 6.9% of revenue excl. VAT (current approach)
INSERT INTO tax_rates (administration, tax_type, tax_code, rate, calc_method, calc_params,
    effective_from, description)
VALUES ('GoodwinSolutions', 'tourist_tax', 'standard', 6.900, 'percentage',
    '{"base": "revenue_excl_vat"}',
    '2026-01-01', 'Toeristenbelasting Haarlemmermeer 2026');

-- Amsterdam: €12.50 per person per night (hypothetical tenant)
INSERT INTO tax_rates (administration, tax_type, tax_code, rate, calc_method, calc_params,
    effective_from, description)
VALUES ('AmsterdamTenant', 'tourist_tax', 'standard', 12.500, 'fixed_per_guest_night',
    '{"includes_children": false, "min_age": 16}',
    '2026-01-01', 'Toeristenbelasting Amsterdam 2026');

-- Rotterdam: 6.5% of room price
INSERT INTO tax_rates (administration, tax_type, tax_code, rate, calc_method, calc_params,
    effective_from, description)
VALUES ('RotterdamTenant', 'tourist_tax', 'standard', 6.500, 'percentage_of_room_price',
    '{"base": "room_price_excl_vat"}',
    '2026-01-01', 'Toeristenbelasting Rotterdam 2026');
```

### Tourist Tax Calculation Service

Instead of inline formulas scattered across processors, a dedicated calculation service:

```python
def calculate_tourist_tax(
    tenant: str,
    reference_date: date,
    gross_amount: float,
    vat_amount: float,
    nights: int = 1,
    guests: int = 1,
    room_price: float = None
) -> dict:
    """
    Calculate tourist tax using the municipality-specific method.

    Returns:
        {'amount': 45.50, 'method': 'percentage', 'rate': 6.9,
         'description': 'Toeristenbelasting Haarlemmermeer 2026'}
    """
    tax_config = get_tax_rate(tenant, 'tourist_tax', 'standard', reference_date)

    if not tax_config:
        return {'amount': 0, 'method': 'none', 'rate': 0}

    method = tax_config.get('calc_method', 'percentage')
    rate = float(tax_config['rate'])

    if method == 'percentage':
        # Current Haarlemmermeer approach
        base_amount = gross_amount - vat_amount
        tourist_base = 100 + rate
        amount = (base_amount / tourist_base) * rate

    elif method == 'fixed_per_guest_night':
        # Amsterdam-style: €X per guest per night
        amount = rate * guests * nights

    elif method == 'fixed_per_night':
        # Fixed per night regardless of guests
        amount = rate * nights

    elif method == 'percentage_of_room_price':
        # Percentage of room price only
        base = room_price if room_price else (gross_amount - vat_amount)
        amount = base * (rate / 100)

    else:
        amount = 0

    return {
        'amount': round(amount, 2),
        'method': method,
        'rate': rate,
        'description': tax_config.get('description', '')
    }
```

### Impact on Current Code

| Current                                                                        | After                                                             |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| `str_processor.py`: inline `(vat_exclusive / tourist_base) * tourist_tax_rate` | `calculate_tourist_tax(tenant, date, gross, vat, nights, guests)` |
| `toeristenbelasting_generator.py`: `(total_8003 / 106.2) * 6.2`                | `calculate_tourist_tax(tenant, date, total_8003, vat_amount)`     |
| Adding Amsterdam tenant: impossible without code change                        | Insert a row with `calc_method = 'fixed_per_guest_night'`         |

### Booking Data Requirements

The `calculate_tourist_tax()` function needs `nights` and `guests` — data that's already available in the booking records (`bnb` table has `nights` field, guest count comes from the platform data). The current percentage method doesn't need these, but the fixed-per-night methods do. This means the STR processor needs to pass these values through, which is a one-time wiring change.

---

## Synthesis: Three Parameter Shapes, One Architecture

After this analysis, the pattern is clear. Every "parameter" in the system falls into one of three shapes:

### Shape 1: Flat Parameters (key-value with scope inheritance)

Simple settings where a single value applies at a given scope level.

**Examples**: `storage.provider = "google_drive"`, `fin.locale = "nl"`, `str.aantal_kamers = 3`, `ui.theme = "dark"`

**Table**: `parameters` (or extended `tenant_config`)

```
scope | scope_id | namespace | key | value (JSON) | value_type
```

**Resolution**: user → role → tenant → system default (first match wins)

**Caching**: in-process dict with write-through invalidation

### Shape 2: Time-Versioned Rates (structured + temporal)

Values that have multiple codes and change on specific dates. The rate alone isn't enough — you also need the linked ledger account and effective date range.

**Examples**: BTW codes (zero/low/high), income tax brackets

**Table**: `tax_rates`

```
administration | tax_type | tax_code | rate | ledger_account | effective_from | effective_to
```

**Resolution**: tenant-specific first → `_system_` default, filtered by `effective_from <= date AND effective_to >= date`

### Shape 3: Calculated Rates (structured + temporal + method)

Like Shape 2, but the rate alone isn't enough — you also need a calculation method and method-specific parameters. The same "tax" can be computed completely differently depending on the municipality or context.

**Examples**: Tourist tax (percentage vs fixed per guest per night vs fixed per night)

**Table**: Same `tax_rates` table, extended with:

```
+ calc_method | calc_params (JSON)
```

**Resolution**: Same as Shape 2, but the calculation service dispatches to the right formula based on `calc_method`.

### How They Relate

```
┌──────────────────────────────────────────────────────────────────┐
│                    Parameter Architecture                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Shape 1: parameters table          Shape 2+3: tax_rates table   │
│  ┌─────────────────────┐            ┌──────────────────────────┐ │
│  │ Flat key-value       │            │ Multi-code, temporal     │ │
│  │ Scope inheritance    │            │ Tenant → system fallback │ │
│  │ All modules use it   │            │ + calc_method dispatch   │ │
│  └─────────────────────┘            └──────────────────────────┘ │
│           │                                    │                  │
│           ▼                                    ▼                  │
│  ParameterService.get_param()      TaxRateService.get_tax_rate() │
│                                    TaxRateService.calculate()     │
│           │                                    │                  │
│           └──────────┬─────────────────────────┘                  │
│                      ▼                                            │
│              Module Registry                                      │
│     (defines which params each module needs)                      │
│                      │                                            │
│                      ▼                                            │
│              Admin UI                                             │
│     (parameters by namespace + tax rate management)               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Implementation: Two Tables, Three Services

| Component              | Purpose                                                   | Table                                             |
| ---------------------- | --------------------------------------------------------- | ------------------------------------------------- |
| `ParameterService`     | Flat key-value with scope inheritance, caching            | `parameters`                                      |
| `TaxRateService`       | Time-versioned rates with tenant fallback                 | `tax_rates`                                       |
| `TouristTaxCalculator` | Dispatches to calc method (percentage, fixed/night, etc.) | `tax_rates` (reads `calc_method` + `calc_params`) |
| `ModuleRegistry`       | Defines params per module, seeds defaults on activation   | References both tables                            |

### What Does NOT Need a New Table

- **Account-level parameters** → stay in `rekeningschema.parameters` JSON column (already working)
- **Credentials** → stay in `tenant_credentials` via `CredentialService` (already working)
- **Module on/off** → stays in `tenant_modules` (already working)

### Decision: Extend `tenant_config` or New `parameters` Table?

**New `parameters` table** is the better choice:

- `tenant_config` has no `scope` concept (it's tenant-only, no system defaults or role overrides)
- `tenant_config` has no `namespace` (flat list of keys)
- `tenant_config` has no `value_type` validation
- Migrating `tenant_config` would break existing CRUD routes and admin UI
- Keep `tenant_config` for backward compatibility, new code uses `parameters`

### Migration Path

1. Create `parameters` and `tax_rates` tables
2. Build `ParameterService` and `TaxRateService`
3. Seed system defaults and NL tax rates
4. Gradually replace hardcoded values with service calls (quick wins first)
5. Eventually migrate relevant `tenant_config` entries to `parameters` table
6. `tenant_config` becomes a thin wrapper or is deprecated

## Summary: Recommended Next Steps

1. **Create `parameters` table** — with scope/namespace/key/value/value_type structure
2. **Create `tax_rates` table** — with tax_type/tax_code/rate/ledger_account/effective dates/calc_method/calc_params
3. **Build `ParameterService`** — scope inheritance chain with in-process caching
4. **Build `TaxRateService` + `TouristTaxCalculator`** — time-versioned rate lookup + municipality-aware calculation dispatch
5. **Build `ModuleRegistry`** — defines params per module, unified `@module_required` decorator
6. **Seed defaults** — NL BTW codes as system defaults, system-level settings. Tourist tax rates are municipality-specific and must be configured per tenant (not seeded as system defaults)
7. **Quick wins** — replace the 6 hardcoded areas with `ParameterService.get_param()` calls
8. **Refactor STR tax logic** — replace duplicated date-branching in `str_processor.py` and `str_channel_routes.py` with `TaxRateService` calls
9. **Storage abstraction** — `StorageProvider` interface, wrap Google Drive, add S3 shared option
10. **Admin UI** — parameter management by namespace + tax rate management screen with effective date timeline

Ready to formalize this into a spec when you want to move forward.
