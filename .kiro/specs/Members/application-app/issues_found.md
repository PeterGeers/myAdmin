# After PR 119

Issues found during manual TEST verification (task 10.6). All fixes below are on
the Flask + React planes only — NO SAM changes. All uncommitted at time of writing.

---

## [FIXED] Tenant-admin "Afzenderadressen" (sender addresses) — HTML instead of JSON

**Symptom**
- "Failed to load sender addresses — Unexpected token '<', "<!DOCTYPE "... is not valid JSON" (GET)
- "Could not add sender address — Failed to execute 'json' on 'Response': Unexpected end of JSON input" (POST)

**Root cause**
`frontend/src/services/memberSenderIdentityService.ts` called `/members/sender-identities`
through the Flask client (`apiService`), which prepends the Flask base but NOT `/api`.
Flask serves the route at `/api/members/sender-identities`, so the request missed and
returned an HTML 404 page → `.json()` failed. The service docstring wrongly claimed the
routes were on the SAM Members Lambda; verified the SAM handler implements NO
sender-identity route — this surface correctly lives on Flask (SES verification state is
MySQL authoring data in `email_verifications`, keyed by `administration`).

**Fix (Option A — single active sender per tenant)**
- `frontend/src/services/memberSenderIdentityService.ts` — `BASE` → `/api/members/sender-identities`;
  wrap the single Flask GET identity into a 0/1-element `identities[]`; map `last_checked`→`lastChecked`;
  corrected docstrings.
- `backend/src/routes/members_sender_identity_routes.py` — added `POST /api/members/sender-identities/resend`
  (delegates to `EmailVerificationService.resend_verification`, 60s cooldown already present).
- Tests: `memberSenderIdentityService.test.ts` (updated to Flask contract) + 4 new resend
  tests in `tests/integration/test_members_sender_identity_routes.py`.
- Verified: backend 13 passed; frontend service 4 passed; `MemberSenderIdentitiesTab` 6 passed.

---

## [FIXED] "Advanced parameters" tab not shown for h-dcn tenant admin

**Symptom**
The Advanced (Geavanceerd) parameters tab was invisible when logged in as the h-dcn
tenant administrator (a non-SysAdmin user id).

**Root cause**
`frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx` gated the Advanced tab/panel
on `isSysAdmin`. It only appeared "correctly" for the operator because they are a SysAdmin.
Reaching the dashboard already REQUIRES `Tenant_Admin` for the current tenant, and the
backend `/api/tenant-admin/parameters` already scopes by tenant + active modules and masks
secrets for non-SysAdmin — so the SysAdmin gate was the sole defect.

**Fix**
- `TenantAdminDashboard.tsx` — removed the `isSysAdmin` gate on the Advanced `<Tab>` + `<TabPanel>`;
  removed the now-unused `isSysAdmin` var.
- `AdvancedTab.tsx` — docstring updated (tenant-admin access, not SysAdmin-only).
- Backend verified safe: tenant admins can only read/edit/delete their OWN tenant's params;
  system scope is SysAdmin-only (403); cross-tenant is 404; secrets masked.

---

## [FIXED] members.* mail params had no authoring door (orphaned)

**Symptom**
Three h-dcn `members` parameter rows (`mail_enabled` id 734, `mail_domain` id 735,
`mail_certified` id 736) were editable by NO UI surface: excluded from the raw Advanced
editor AND not addressed by the redesigned Members tab (which is purely groups/fields).

**Root cause**
`frontend/src/components/TenantAdmin/ParameterManagement.tsx` hard-excluded the ENTIRE
`members` namespace (`EXCLUDED_NAMESPACE = 'members'`) — a stale rule from the old Members
UI. The redesigned typed Members editor owns only the FIELD-DEFINITION keys (`field_overlay`
+ `scope_dimensions`). The mail params + `default_page_size` have no typed door; their
intended door is `/api/tenant-admin/parameters` (per `parameter_schema.py` +
`_projection_config_builders.py`).

**Definition note** — these params are DEFINED in code (`backend/src/services/parameter_schema.py`,
`members` namespace); the DB rows are per-tenant overrides. Save-time validation exists in
`backend/src/services/members_config_validation.py` (`validate_members_param`), so raw
editing is safe.

**Fix**
- `ParameterManagement.tsx` — replaced the namespace-wide exclusion with a KEY-level one:
  hide only `members.field_overlay` + `members.scope_dimensions` (typed-editor-owned); SHOW
  every other `members.*` key (mail_*, default_page_size).
- Test: updated fixture + rewrote the exclusion block in `ParameterManagement.test.tsx` to
  the selective contract. Verified: 35/35 passed.

---

## [FIXED — supporting] seed-hdcn-members-config.py stale `test_mode` kwarg

`scripts/onboarding/members/h-dcn/seed-hdcn-members-config.py` called
`DatabaseManager(test_mode=False)`, but `test_mode` was removed from the constructor
(test-env Phase 3). Changed to `DatabaseManager()` (matches the already-fixed sibling
`project-config-to-prod.py`). Found while confirming where h-dcn's `members.*` config is
stored (local Docker `finance` — rows DO exist; the operator had queried a different DB).

---

## [OPEN] "Save as second layer" — member_number format.checker None

**Symptom (NOT yet fixed)**
Saving a change intended for the SAM module:
`invalid members config: membership.member_number: format.checker None is not a
platform-known token (known: EMAIL, IBAN)`

**Notes for investigation**
A `member_number` field override carries a `format` whose `checker` is `None`, which the
validator rejects (only EMAIL / IBAN are known checker tokens). Needs: trace where the
`format.checker: None` is being authored/serialized (likely the typed Members field editor
emitting an empty `format` object instead of omitting it), and the `members_config_validation`
rule that rejects it. Decide: omit an empty `format`, or accept `checker=None` as "no format".

## Questions
### where are the attributes to connect a field to the applcation form
When looking in the members tenantadmin groups/fields I do not see the attrubutes needed to define the content of the application form.

### In which tenant is the s3 shared bucket liocated