# Create New Tenant — Provisioning Spec

**Status:** Ready for Implementation
**Date:** 2026-03-25
**Related:** `backend/scripts/provision_tenant.py`, `backend/src/routes/sysadmin_tenants.py`

---

## 1. Problem Statement

There are two ways to create a tenant, and they do different things:

| Capability             | SysAdmin UI (`sysadmin_tenants.py`) | Script (`provision_tenant.py`) |
| ---------------------- | ----------------------------------- | ------------------------------ |
| Insert tenant record   | ✅                                  | ✅                             |
| Insert tenant modules  | ✅                                  | ✅                             |
| Copy chart of accounts | ❌                                  | ✅ (from GoodwinSolutions)     |
| Locale support         | ❌                                  | ❌                             |
| Update Cognito user    | ❌                                  | ✅                             |
| Track signup status    | ❌ (not applicable)                 | ✅                             |
| Admin notification     | ❌                                  | ✅                             |

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

## 3. Template Design

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

Future: implement transaction validation against the chart of accounts to prevent bookings to non-existent accounts.

---

## 5. Idempotency (Rerun Safety)

The shared service must be safe to rerun if a previous attempt partially completed (e.g., tenant inserted but chart copy failed). Each step checks before acting:

| Step                   | Check before acting                              | On rerun (already exists)     |
| ---------------------- | ------------------------------------------------ | ----------------------------- |
| Insert tenant          | `SELECT` by administration name                  | Skip, log "already exists"    |
| Insert modules         | `SELECT` by administration + module_name         | Skip existing, insert missing |
| Copy chart of accounts | `SELECT COUNT(*)` from rekeningschema for tenant | Skip if rows > 0, log count   |

### Behavior

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

The SysAdmin UI and `provision_tenant.py` can use this to show the admin exactly what happened.

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

### 6.2 Report templates — needs provisioning

Beyond the chart of accounts, new tenants also need report templates to generate reports and tax forms. These are stored in `tenant_template_config` and the actual template files live in the tenant's Google Drive.

### What templates exist

| Template type             | Purpose                     | Format |
| ------------------------- | --------------------------- | ------ |
| `aangifte_ib_html_report` | Income tax report (viewing) | HTML   |
| `btw_aangifte_html`       | VAT report (viewing)        | HTML   |
| `financial_report_xlsx`   | Financial report export     | XLSX   |
| `str_invoice`             | STR invoice generation      | HTML   |
| `toeristenbelasting_html` | Tourist tax report          | HTML   |

### Current state

- Templates are only set up for existing tenants (GoodwinSolutions, PeterPrive) via manual scripts
- New tenants created via SysAdmin UI or `provision_tenant.py` get **no templates**
- Without templates, report generation fails silently or returns errors

### Proposed approach: Default templates in Google Drive

1. Store default template files in a shared "system" Google Drive folder (not tenant-specific)
2. On tenant provisioning, copy the default templates to the new tenant's Google Drive Templates folder
3. Insert `tenant_template_config` rows pointing to the copied files
4. Tenant admins can later replace templates with their own customized versions

### Alternative: Shared system templates (no copy)

Instead of copying, all tenants reference the same default template files:

- Simpler — no Google Drive copy step needed
- Less flexible — tenant can't customize without affecting all tenants
- Suitable for official tax form templates (which are not customizable anyway)

### Decision needed

- Which templates should be copied per-tenant (customizable)?
- Which templates should be shared system-wide (fixed)?

Likely split:

- Shared (fixed): `btw_aangifte_html`, `toeristenbelasting_html`, `aangifte_ib_html_report` — standard Dutch tax formats
- Per-tenant (customizable):`btw_aangifte_html`, `toeristenbelasting_html`, `aangifte_ib_html_report`, `str_invoice`, `financial_report_xlsx` — branding/layout varies

### Implementation tasks (Phase 6: Report Templates)

- [ ] Identify which template files are "default" and store in a system Google Drive folder
- [ ] Decide shared vs per-tenant for each template type
- [ ] Add `provision_report_templates(administration)` to `TenantProvisioningService`
- [ ] For per-tenant templates: copy files to tenant's Google Drive, insert `tenant_template_config` rows
- [ ] For shared templates: insert `tenant_template_config` rows pointing to system files
- [ ] Add idempotency: skip if `tenant_template_config` rows already exist for tenant
- [ ] Test: new tenant can generate all report types after provisioning

---

## 7. Implementation Tasks

### Phase 1: Shared Service

- [ ] Create `backend/src/services/tenant_provisioning_service.py`
  - `create_and_provision_tenant(administration, display_name, contact_email, modules, created_by, locale='nl')`
  - Handles: insert tenant, insert modules, load chart from template
- [ ] Update `backend/src/routes/sysadmin_tenants.py` — call shared service instead of inline DB logic
- [ ] Update `backend/scripts/provision_tenant.py` — call shared service for steps 3-5
- [ ] Add unit tests for `tenant_provisioning_service.py`

### Phase 2: JSON Templates

- [ ] Create `backend/src/templates/chart_of_accounts/nl.json` — extract clean generic accounts from GoodwinSolutions
- [ ] Create `backend/src/templates/chart_of_accounts/en.json` — translated version
- [ ] Create `backend/src/templates/chart_of_accounts/schema.md` — document the format
- [ ] Add unit tests for template loading and chart insertion

### Phase 3: Locale Integration

- [ ] Add `locale` dropdown (nl/en) to SysAdmin UI create tenant form
- [ ] Update `provision_tenant.py` to pass `pending_signups.locale` to the shared service
- [ ] Verify `account_translations` table integration (table already exists in DB)

### Phase 4: Testing & Validation

- [ ] Test SysAdmin UI — create tenant, verify chart of accounts is populated
- [ ] Test `provision_tenant.py --dry-run` still works
- [ ] Test locale fallback (unknown locale falls back to `nl`)
- [ ] Test error case: missing template file → tenant created with warning

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
python scripts/provision_tenant.py user@example.com --test-mode
```

---

## 9. Automated Provisioning

Currently provisioning is manual (SysAdmin UI or CLI script). This phase adds an API endpoint and automation.

### 9.1 Provisioning API Endpoint

New endpoint: `POST /api/admin/provision`

- Callable from the SysAdmin dashboard (replaces CLI script for promo signups)
- Accepts `email`, `administration_name`, `modules`, `locale`
- Calls the shared `TenantProvisioningService` (Phase 1) for tenant + modules + chart
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

### Implementation tasks (Phase 5: Automation)

- [ ] Create `POST /api/admin/provision` endpoint in a new blueprint
- [ ] Add SysAdmin dashboard UI for provisioning verified signups (list pending, one-click provision)
- [ ] Add `plan`, `plan_expires_at` columns to `tenants` table
- [ ] Add plan check middleware to backend
- [ ] Create welcome email template (nl/en) in SES email service
- [ ] Implement auto-provisioning trigger (background job or Lambda)
- [ ] Add unit + API tests for provisioning endpoint
- [ ] Update `RAILWAY_ENV_VARS.md` with any new env vars
