# Create New Tenant — Provisioning Spec

**Status:** Complete (Phase 7 — Initial Admin User added April 2026)
**Date:** 2026-04-23
**Related:** `backend/src/services/tenant_provisioning_service.py`, `backend/src/routes/sysadmin_tenants.py`, `backend/scripts/provision_tenant.py`, `backend/src/routes/sysadmin_provisioning.py`

---

## 1. Problem Statement

There are two ways to create a tenant, and they do different things:

| Capability             | SysAdmin UI (`sysadmin_tenants.py`) | Script (`provision_tenant.py`) | Provisioning API (`sysadmin_provisioning.py`) |
| ---------------------- | ----------------------------------- | ------------------------------ | --------------------------------------------- |
| Insert tenant record   | ✅                                  | ✅                             | ✅                                            |
| Insert tenant modules  | ✅                                  | ✅                             | ✅                                            |
| Copy chart of accounts | ✅ (from JSON template)             | ✅ (from JSON template)        | ✅ (from JSON template)                       |
| Locale support         | ✅ (nl/en)                          | ✅ (from signup)               | ✅ (from signup)                              |
| Create initial admin   | ✅ (contact_email)                  | ✅ (signup email)              | ✅ (signup email)                             |
| Update Cognito user    | ✅ (via admin user creation)        | ✅                             | ✅                                            |
| Track signup status    | ❌ (not applicable)                 | ✅                             | ✅                                            |
| Admin notification     | ❌                                  | ✅                             | ✅                                            |
| Resend invitation      | ✅ (SysAdmin button)                | ❌                             | ❌                                            |

Problems:

- SysAdmin UI skips the chart of accounts — new tenants can't do financial processing
- The script copies from a live tenant (GoodwinSolutions), which contains company-specific accounts
- No locale support — account names are Dutch only
- Duplicate logic across two code paths

---

## 2. Solution: Shared Service + JSON Templates

### 2.1 Shared Tenant Provisioning Service

Extract common logic into `backend/src/services/tenant_provisioning_service.py`:

```python
def create_and_provision_tenant(administration, display_name, contact_email,
                                 modules, created_by, locale='nl'):
    """
    Shared provisioning logic:
    1. Insert tenant record
    2. Insert tenant modules
    3. Load chart of accounts from JSON template (locale-aware)
    """
```

Both callers use this service, each adding their own specific steps around it:

```
SysAdmin UI                              provision_tenant.py
    │                                         │
    │                                         │ 1. Lookup pending_signups
    │                                         │ 2. Generate admin name
    │   ┌──────────────────────────────┐      │
    ├──►│ TenantProvisioningService    │◄─────┤
    │   │  1. Insert tenant            │      │
    │   │  2. Insert modules           │      │ 3. Update Cognito user
    │   │  3. Load chart from template │      │ 4. Mark provisioned
    │   └──────────────────────────────┘      │ 5. SNS notification
    ▼                                         ▼
```

### 2.2 JSON Chart of Accounts Templates

Replace the GoodwinSolutions copy with standalone JSON template files:

```
backend/src/templates/chart_of_accounts/
├── nl.json          # Dutch standard chart
├── en.json          # English standard chart
└── schema.md        # Template format documentation
```

### Why JSON templates instead of copying from GoodwinSolutions

| Aspect          | Before (DB copy)                   | After (JSON templates)                      |
| --------------- | ---------------------------------- | ------------------------------------------- |
| Independence    | Coupled to live tenant data        | Standalone, version-controlled              |
| Locale          | Dutch only                         | nl/en, extensible                           |
| Maintenance     | Edit a live tenant's chart         | Edit a JSON file, version-controlled in git |
| Clean data      | Contains company-specific accounts | Generic small-business chart only           |
| Reproducibility | Depends on DB state                | Deterministic from file                     |
| Testability     | Needs DB with GoodwinSolutions     | Load JSON in unit tests                     |

---

## 3. Chart of Accounts Template Design

### 3.1 Template format

Each JSON file contains an array of account entries matching `rekeningschema` columns:

```json
[
  {
    "Account": "2001",
    "AccountLookup": null,
    "AccountName": "Tussenrekening",
    "SubParent": "200",
    "Parent": "2000",
    "VW": "N",
    "Belastingaangifte": "Tussenrekening",
    "Pattern": false,
    "parameters": { "roles": ["interim_opening_balance"] }
  },
  {
    "Account": "3099",
    "AccountLookup": null,
    "AccountName": "Eigen Vermogen",
    "SubParent": "309",
    "Parent": "3000",
    "VW": "N",
    "Belastingaangifte": "Ondernemingsvermogen",
    "Pattern": false,
    "parameters": null
  }
]
```

Note: `administration` is NOT in the template — it's set dynamically by the provisioning service when inserting for the new tenant.

### 3.2 Account ranges (generic small-business chart)

| Range     | Category (NL)           | Category (EN)         | Examples                                       |
| --------- | ----------------------- | --------------------- | ---------------------------------------------- |
| 1000-1999 | Balans                  | Assets                | Kas, Bank, Debiteuren, Crediteuren             |
| 2000-2999 | Tussenrekeningen        | Interim accounts      | Tussenrekening, BTW, Toeristenbelasting        |
| 3000-3999 | Vaste activa & Vermogen | Fixed assets & Equity | Materiële vaste activa, Eigen Vermogen         |
| 4000-4999 | Kosten                  | Expenses              | Kantoor, Huisvesting, Transport, Verzekeringen |
| 8000-8999 | Opbrengsten             | Revenue               | Omzet, Rente, Bijzondere baten en lasten       |

### 3.3 Excluded from templates (tenant-specific)

- Bank account IBANs (`AccountLookup`) — tenants add their own
- Personal names in account names
- Company-specific accounts (e.g., "JaBaKi verhuur", "Lening Peter Geers")

---

## 4. Error Handling

If loading the chart of accounts fails (e.g., template file missing):

- Do NOT roll back the tenant creation
- Log a warning
- Return success with a warning message
- Mark the tenant as needing chart setup (e.g., flag in response or tenant status)
- The chart is required for correct bookings — the admin must resolve this before the tenant starts processing transactions

Future: ~~implement transaction validation against the chart of accounts to prevent bookings to non-existent accounts.~~ ✅ Solved — account validation is now in place.

---

## 5. Idempotency (Rerun Safety)

The shared service must be safe to rerun if a previous attempt partially completed (e.g., tenant inserted but chart copy failed). Each step checks before acting:

| Step                   | Check before acting                              | On rerun (already exists)     |
| ---------------------- | ------------------------------------------------ | ----------------------------- |
| Insert tenant          | `SELECT` by administration name                  | Skip, log "already exists"    |
| Insert modules         | `SELECT` by administration + module_name         | Skip existing, insert missing |
| Copy chart of accounts | `SELECT COUNT(*)` from rekeningschema for tenant | Skip if rows > 0, log count   |

### Shared service behavior

```python
def create_and_provision_tenant(administration, ..., locale='nl'):
    results = {'tenant': 'created', 'modules': [], 'chart': 'created'}

    # Step 1: Insert tenant (skip if exists)
    existing = db.execute_query(
        "SELECT administration FROM tenants WHERE administration = %s", (administration,), fetch=True)
    if existing:
        logger.info(f"Tenant {administration} already exists — skipping insert")
        results['tenant'] = 'skipped'
    else:
        # insert tenant record

    # Step 2: Insert modules (skip existing, insert missing)
    for module in modules:
        existing_mod = db.execute_query(
            "SELECT id FROM tenant_modules WHERE administration = %s AND module_name = %s",
            (administration, module), fetch=True)
        if existing_mod:
            logger.info(f"Module {module} already exists — skipping")
            results['modules'].append({'name': module, 'status': 'skipped'})
        else:
            # insert module
            results['modules'].append({'name': module, 'status': 'created'})

    # Step 3: Copy chart (skip if tenant already has rows)
    count_result = db.execute_query(
        "SELECT COUNT(*) as cnt FROM rekeningschema WHERE administration = %s",
        (administration,), fetch=True)
    count = count_result[0]['cnt'] if count_result else 0
    if count > 0:
        logger.info(f"Chart already exists ({count} rows) — skipping")
        results['chart'] = 'skipped'
    else:
        # load from JSON template and insert

    return results
```

### Return value

The service returns a results dict so the caller knows what was created vs skipped:

```json
{
  "tenant": "created",
  "modules": [
    { "name": "FIN", "status": "created" },
    { "name": "STR", "status": "skipped" },
    { "name": "TENADMIN", "status": "created" }
  ],
  "chart": "created"
}
```

### provision_tenant.py rerun handling

The script also needs rerun safety for its own steps:

| Step                     | Check                                 | On rerun                                  |
| ------------------------ | ------------------------------------- | ----------------------------------------- |
| Cognito `custom:tenants` | Already checks if tenant is in list   | Safe — skips if present                   |
| Mark provisioned         | Overwrites `provisioned_at` timestamp | Safe — idempotent                         |
| SNS notification         | No check                              | Sends duplicate notification (acceptable) |

The script's existing check `if signup['status'] == 'provisioned': exit` should be changed to a `--force` flag that allows rerunning for partial failures.

---

## 6. Templates for New Tenants

### 6.1 Email templates (user invitations) — no action needed

Email templates for user invitations are already handled correctly:

- Default templates live in `backend/templates/email/` (nl + en versions)
- `EmailTemplateService.render_template()` tries Google Drive first (tenant-specific), then falls back to local defaults
- New tenants automatically use the default templates — no provisioning step required
- Tenant admins can customize by uploading their own version to Google Drive (overrides the default)

Files: `user_invitation.html` (en), `user_invitation_nl.html` (nl), plus `.txt` versions.

### 6.2 Report templates — local defaults with tenant-specific override

Same pattern as email templates: local defaults in the backend, tenant-specific versions in Google Drive override them.

```
Template resolution order:
1. Tenant's Google Drive (tenant_template_config → file_id) — customized
2. Local default in backend/templates/reports/           — fallback
```

1. Store default report templates locally in `backend/templates/reports/` (version-controlled)
2. Extend `TemplateService` to fall back to local defaults when no Google Drive template exists
3. On tenant provisioning, optionally copy defaults to tenant's Google Drive (so they can customize)
4. If no Google Drive copy exists, the local default is used automatically
5. Tenant admins can upload customized versions to Google Drive at any time

All report templates are per-tenant customizable, with local defaults as fallback:

| Template type             | Customizable | Default fallback | Notes                     |
| ------------------------- | ------------ | ---------------- | ------------------------- |
| `aangifte_ib_html_report` | ✅           | ✅ local file    | Layout, branding          |
| `btw_aangifte_html`       | ✅           | ✅ local file    | Layout, branding          |
| `toeristenbelasting_html` | ✅           | ✅ local file    | Layout, branding          |
| `str_invoice`             | ✅           | ✅ local file    | Branding, invoice layout  |
| `financial_report_xlsx`   | ✅           | ✅ local file    | Column layout, formatting |

---

## 7. Implementation Tasks

### Phase 1: Shared Provisioning Service

- [x] Create `backend/src/services/tenant_provisioning_service.py`
  - `create_and_provision_tenant(administration, display_name, contact_email, modules, created_by, locale='nl')`
  - Idempotent: check-before-act for each step (section 5)
  - Returns results dict with created/skipped status per step
- [x] Update `backend/src/routes/sysadmin_tenants.py` — call shared service instead of inline DB logic
- [x] Update `backend/scripts/provision_tenant.py` — call shared service for steps 3-5
- [x] Add `--force` flag to `provision_tenant.py` to allow rerun after partial failure
- [x] Add unit tests for `tenant_provisioning_service.py` (including idempotency tests)

### Phase 2: Chart of Accounts JSON Templates

- [x] Create `backend/src/templates/chart_of_accounts/nl.json` — extract clean generic accounts from GoodwinSolutions
- [x] Create `backend/src/templates/chart_of_accounts/en.json` — translated version
- [x] Create `backend/src/templates/chart_of_accounts/schema.md` — document the format
- [x] Add unit tests for template loading and chart insertion
- [x] Add unit test for locale fallback (unknown locale → `nl`)

### Phase 3: Locale Integration

- [x] Add `locale` dropdown (nl/en) to SysAdmin UI create tenant form
- [x] Update `provision_tenant.py` to pass `pending_signups.locale` to the shared service

### Phase 4: Report Template Defaults

- [x] Create `backend/templates/reports/` with default versions of all 5 template types
- [x] Extend `TemplateService` to fall back to local defaults when no Google Drive template exists
- [ ] Add `provision_report_templates(administration)` to `TenantProvisioningService` (optional: copy defaults to Google Drive)
- [x] Add idempotency: skip if `tenant_template_config` rows already exist for tenant
- [x] Test: new tenant can generate all report types using local defaults (no Google Drive setup needed)
- [x] Test: tenant with customized Google Drive template uses that instead of default

### Phase 5: End-to-End Testing

- [x] Test SysAdmin UI — create tenant, verify chart of accounts is populated (manual browser test)
- [x] Test SysAdmin UI — create tenant, verify report generation works with default templates (manual browser test)
- [x] Test `provision_tenant.py --dry-run` still works (dry_run exits before shared service call — unchanged)
- [x] Test `provision_tenant.py --force` reruns partial provisioning correctly (covered by `TestIdempotency`)
- [x] Test error case: missing chart template file → tenant created with warning (covered by `test_tenant_still_created_when_chart_fails`)

### Phase 6: Re-Provision Existing Tenants

SysAdmin needs a way to re-provision an existing tenant to fill in missing pieces (e.g., chart of accounts was not loaded on first creation, or new modules need adding). This is separate from editing tenant details.

**Why not reuse the create endpoint:**

- Create returns 400 if tenant exists
- Making create idempotent risks silently ignoring changes to tenant details (display_name, contact_email) — the admin expects those to be updated via the edit form

**Approach:** Dedicated re-provision endpoint that only runs the idempotent gap-filling steps:

- Add missing modules (skip existing)
- Load chart of accounts from template if no rows exist (skip if rows > 0)
- Does NOT touch the tenant record itself (use PUT endpoint for that)

**Implementation tasks:**

- [x] Create `POST /api/sysadmin/tenants/<administration>/reprovision` endpoint
  - Accepts optional `locale` and `modules` in request body
  - Calls `TenantProvisioningService` with existing tenant data
  - Returns provisioning results dict (created/skipped per step)
  - Authorization: SysAdmin role required
- [x] Add "Re-provision" button to SysAdmin UI tenant detail/edit view
  - Shows provisioning results after completion (what was created vs skipped)
  - Only visible for existing tenants
- [x] Add unit tests for the re-provision endpoint
- [x] Test: re-provision tenant with missing chart → chart loaded from template
- [x] Test: re-provision fully provisioned tenant → all steps skipped

### Phase 7: Initial Admin User Creation (Bugfix — April 2026)

**Problem:** All 3 provisioning entry points created tenant infrastructure but never created an initial admin user. New tenants had 0 users and no way to log in.

**Solution:** Added `create_initial_admin_user()` to `TenantProvisioningService` and wired it into all entry points.

**Spec:** `.kiro/specs/Common/onboarding/onboarding-initial-admin-user/` (bugfix.md, design.md, tasks.md)

- [x] Add `create_initial_admin_user()` method to `TenantProvisioningService`
  - Handles new Cognito users (create + set permanent password → CONFIRMED)
  - Handles existing Cognito users (add tenant to `custom:tenants`)
  - Idempotent: skips if `user_tenant_roles` row already exists
  - Failures are warnings, not hard errors
- [x] Add optional `initial_admin_email` parameter to `create_and_provision_tenant()`
- [x] Update `sysadmin_tenants.py` — extract `initial_admin_email` from request, pass to service
- [x] Update `provision_tenant.py` — pass signup email as `initial_admin_email`
- [x] Update `sysadmin_provisioning.py` — pass signup email as `initial_admin_email`
- [x] Add SysAdmin resend invitation endpoint (`POST /<administration>/resend-invitation`)
  - Generates new temp password, updates Cognito, ensures `user_tenant_roles` exists
  - Blocks resend for deleted tenants
  - Ensures `custom:tenants` is updated for existing Cognito users
- [x] Add "Resend Invitation" button to SysAdmin Tenant Management modal (disabled for deleted tenants)
- [x] Add `resendInvitation()` to `sysadminService.ts`
- [x] Frontend: send `initial_admin_email` (= `contact_email`) in create tenant request
- [x] Frontend: add ZZP module to tenant creation module selection
- [x] Property-based tests: bug condition exploration, preservation, unit tests (60 tests total)
- [x] Fix Cognito user listing pagination — fetch all pages, not just first 60
- [x] Create `tenant_added` HTML email templates (NL/EN) for existing users added to a tenant
- [x] Update invitation email templates — remove false "7 days valid" claim, recommend password change

**Additional fixes discovered during testing:**

- Cognito `list_users` pagination bug: only first 60 users returned → all users now fetched
- Resend invitation didn't update `custom:tenants` for existing users → fixed
- `CreateTenantRequest` interface missing `initial_admin_email` → added
- `tenant_added` email was plain text fallback → proper HTML templates created

### Phase 8: Parameters for New Tenants (TODO)

New tenants need two types of parameters configured before they can fully operate:

**1. Generic parameters** (`parameters` table, scope=tenant)
Tenant-level configuration stored in the `parameters` table via `ParameterService`. These are flat key-value pairs with namespace grouping and scope inheritance (user → role → tenant → system).

Currently seeded by `seed_tenant_parameters.py` for existing tenants, but NOT automatically run during provisioning. New tenants are missing:

- `storage.report_output_path` — where reports are written
- `storage.google_drive_folder_id` — Google Drive invoices folder

**Action needed:** Call `seed_tenant()` from `create_and_provision_tenant()` after Step 3 (chart of accounts), or integrate parameter seeding into the provisioning flow.

**2. Ledger-specific parameters** (`rekeningschema.parameters` JSON column)
Per-account flags stored as JSON in the `parameters` column of the `rekeningschema` table. Defined in `backend/src/config/ledger_parameters.json`. These mark accounts with special roles:

| Parameter                                                    | Module | Purpose                                  |
| ------------------------------------------------------------ | ------ | ---------------------------------------- |
| `bank_account` + `iban`                                      | FIN    | Identifies bank accounts and their IBANs |
| `asset_account`                                              | FIN    | Marks depreciable asset accounts         |
| `roles` (interim_opening_balance, equity_result, pl_closing) | FIN    | Year-end closure account roles           |
| `vat_netting` + `vat_primary`                                | FIN    | VAT netting group configuration          |
| `zzp_invoice_ledger`                                         | ZZP    | Bank account shown on ZZP invoices       |
| `zzp_revenue_ledger`                                         | ZZP    | Revenue account for ZZP invoice booking  |
| `zzp_debtor_account` / `zzp_creditor_account`                | ZZP    | Debtor/creditor accounts for ZZP         |

These are loaded from the chart of accounts JSON templates (the `parameters` field in each account entry). The chart template already includes `roles` for key accounts (e.g., `interim_opening_balance` on account 2001). However, bank-specific parameters (`bank_account`, `iban`) and ZZP booking accounts must be configured by the Tenant Admin after provisioning, since they are tenant-specific.

**Current state:** Chart template parameters are loaded correctly during provisioning. Tenant-level parameters (`parameters` table) are NOT seeded automatically for new tenants.

- [ ] Integrate `seed_tenant()` into `create_and_provision_tenant()` as Step 5
- [ ] Add parameter seeding to the re-provision endpoint as well
- [ ] Document which parameters the Tenant Admin must configure manually after provisioning (bank IBANs, ZZP accounts)

---

## 8. Reference: Current provision_tenant.py Steps

| Step | Task                         | Target             | Shared service?                       |
| ---- | ---------------------------- | ------------------ | ------------------------------------- |
| 1    | Look up pending signup       | `myadmin_promo` DB | No — signup-specific                  |
| 2    | Generate administration name | `finance` DB       | No — SysAdmin UI has form input       |
| 3    | Insert tenant                | `finance` DB       | ✅ Yes                                |
| 4    | Insert tenant modules        | `finance` DB       | ✅ Yes                                |
| 5    | Copy chart of accounts       | `finance` DB       | ✅ Yes (from JSON template)           |
| 6    | Update Cognito user          | AWS Cognito        | No — handled when creating first user |
| 7    | Mark provisioned             | `myadmin_promo` DB | No — signup-specific                  |
| 8    | Send admin notification      | AWS SNS            | No — SysAdmin already knows           |

**CLI usage:**

```bash
python scripts/provision_tenant.py user@example.com
python scripts/provision_tenant.py user@example.com --name "CompanyName" --modules "FIN,STR,TENADMIN"
python scripts/provision_tenant.py user@example.com --dry-run
python scripts/provision_tenant.py user@example.com --force
python scripts/provision_tenant.py user@example.com --test-mode
```

---

## 9. Future: Automated Provisioning

Currently provisioning is manual (SysAdmin UI or CLI script). This phase adds an API endpoint and automation.

### 9.1 Provisioning API Endpoint

New endpoint: `POST /api/admin/provision`

- Callable from the SysAdmin dashboard (replaces CLI script for promo signups)
- Accepts `email`, `administration_name`, `modules`, `locale`
- Calls the shared `TenantProvisioningService` for tenant + modules + chart
- Handles signup-specific steps: Cognito update, mark provisioned, SNS notification
- Authorization: SysAdmin role required

### 9.2 Auto-Provisioning After Email Verification

- Trigger provisioning automatically when `pending_signups.status` changes to `verified`
- Options: background job polling the DB, or Cognito post-confirmation Lambda
- Uses the same shared service + provisioning API internally
- Removes the need for manual admin intervention for standard signups

### 9.3 Trial Plan Management

- Add `plan` and `plan_expires_at` columns to `tenants` table
- Default: `trial` plan with 2-month expiry from provisioning date
- Backend middleware checks plan status on each request
- Expired trials: read-only access, prompt to upgrade

### 9.4 Automated Welcome Email

- Send via SES (already set up) to the new tenant's contact email
- Include: login URL, getting started guide, user manual link
- Triggered after successful provisioning (both manual and auto)
- Locale-aware template (nl/en)

### Implementation tasks (Future)

- [x] Create `POST /api/sysadmin/provisioning/provision` endpoint in a new blueprint
- [x] Add `GET /api/sysadmin/provisioning/pending` to list verified signups
- [x] Add `plan`, `plan_expires_at` columns to `tenants` table (migration SQL)
- [x] Add plan check middleware to backend (blocks expired trials on data endpoints)
- [x] Create welcome email template (nl/en) in provisioning endpoint
- [x] Add SysAdmin dashboard UI for provisioning verified signups (list pending, one-click provision)
- [ ] Implement auto-provisioning trigger (background job or Lambda)
- [x] Add unit + API tests for provisioning endpoint
- [x] Update `RAILWAY_ENV_VARS.md` with any new env vars (none needed — all vars already configured)
- [x] Run migration SQL on Railway database
