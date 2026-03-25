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

## 5. Implementation Tasks

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

## 6. Reference: Current provision_tenant.py Steps

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

## 7. Automated Provisioning

Currently provisioning is manual (SysAdmin UI or CLI script). This phase adds an API endpoint and automation.

### 7.1 Provisioning API Endpoint

New endpoint: `POST /api/admin/provision`

- Callable from the SysAdmin dashboard (replaces CLI script for promo signups)
- Accepts `email`, `administration_name`, `modules`, `locale`
- Calls the shared `TenantProvisioningService` (Phase 1) for tenant + modules + chart
- Handles signup-specific steps: Cognito update, mark provisioned, SNS notification
- Authorization: SysAdmin role required

### 7.2 Auto-Provisioning After Email Verification

- Trigger provisioning automatically when `pending_signups.status` changes to `verified`
- Options: background job polling the DB, or Cognito post-confirmation Lambda
- Uses the same shared service + provisioning API internally
- Removes the need for manual admin intervention for standard signups

### 7.3 Trial Plan Management

- Add `plan` and `plan_expires_at` columns to `tenants` table
- Default: `trial` plan with 2-month expiry from provisioning date
- Backend middleware checks plan status on each request
- Expired trials: read-only access, prompt to upgrade

### 7.4 Automated Welcome Email

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
