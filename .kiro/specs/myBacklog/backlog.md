
# Time tracking

- Quick add part
  -- Missing product or NOT
  -- What about more people able to track time
  -- What about access to the time tracking app as a stand alone app (cognito/jwt impact)
  -- What is the added value
  -- How can we easy filter a period for submitting (day, week, month or year)


# STR Import Guesty

https://app.guesty.com/reservations?viewId=6a72237ce377681f84e3746c
Add website data loading from guesty
Strip fee is not in Guesty and can be found in stripe link reservation code

What is this : https://report.guesty.com/apps/reservations?apiKey=89b048a6196d1b5fbcbc40f8cb6b75924419bce37cd1efa83af5d4c6b230e089ddb4caaaad87ab85a5444543e00bcd0c80e18d3bb037d66aca1a1f7513fea2ff

## prompt:
Checkin is between 2 months ago and 1 year into the future for Platform Manual


# FIN Recalculation of balance sheet for validation
Out of scope: Full recalculation mode (reading all years while excluding OpeningBalance records) is a separate audit/verification feature to be wired into tenant administration as its own deliverable. See future spec: balance-verification-audit.


# ZZP Modal to manage trip presets
The database has an is_manual boolean field on each preset:

is_manual = true → user-created via the management UI
is_manual = false → auto-learned from trip history
Both show up equally on the Quick Entry screen — the user doesn't need to care how a preset was created. They just see their routes sorted by usage frequency.

Where the distinction matters:

Scenario	Manual	Auto-learned
Shown in Quick Entry	✓ (always)	✓ (top X by use_count)
User can edit	✓	✓
User can delete	✓	✓
Gets pruned if unused for 6 months	No	Yes (falls off the top X)
Created before first trip	✓ (plan ahead)	✗ (needs trips first)
So the practical value of manual presets: you can add a route you will drive (new client, new office) before you've actually driven it. Auto-learned ones only appear after you've used the route.

In the management UI, you could show a small badge ("Handmatig" / "Geleerd") to distinguish them visually, but it's purely informationa

# s3 object management module and SAM
How can we manage s3 management attributes similar as in Flask

# PITR / Backup in dynamodb
Check the current settings and what is needed

# Fall back mechanosm outside tenant scope 
- Should be impossible
- Pre-check on parameters/config availability after new deployment??


# Projection sync does not reconcile obsolete role# / module# / config# rows (only scopegrant#)
Found during s5d C.12 (2026-09-23). `ProjectionSync.sync_administration` (backend/src/services/projection_sync.py)
only diff-deletes obsolete `scopegrant#` rows (`_reconcile_scopegrants`). Its own docstring notes
`tenant`/`module#*`/`role#*`/`config#*` are "never listed and never deleted (out of s5d's scope)".
Consequence: a role REMOVED from MySQL `user_tenant_roles` leaves a STALE `role#<email>#<role>` row in
`governance_projection` indefinitely — the projection keeps advertising a role the source no longer grants
(SECURITY-relevant staleness, same class as the scopegrant staleness that reconcile was built to fix).
Real example: prod `h-dcn` had 3 orphaned role# rows with no MySQL source (`Regio_All`, a `h-scn` typo'd
Tenant_Admin, and a `member-test@example.com` row) — cleaned up manually in C.12.
- Options: extend the reconcile to `role#` (and consider `module#`) with the same diff-and-delete pattern,
  scoped per tenant; OR a periodic reconciliation sweep.
- Note the capability path today is token/entitlement-based (has_capability off `custom:entitlements`), and
  the resolver reads the projection — so a stale `role#` row could inflate a resolved entitlement once the
  PreTokenGen trigger is live (s5d PHASE CE). Worth fixing before/with CE.2.
- Related: "Fall back mechanism outside tenant scope" above (projection integrity / post-deploy pre-checks).


# SAM deploys are ad-hoc (no committed samconfig / CI) — codify test+prod
Surfaced during s5d PHASE CE (2026-09-23). The SAM Lambdas are deployed by hand-typed
`sam deploy` commands with INLINE `--parameter-overrides`, not from committed config or CI.
Consequences seen:
- **`sam/pretokengen` has NO `samconfig.toml`** and NO deploy workflow. The prod-stage Lambda
  (`pretokengen-prod`) was never deployed — only `pretokengen-test` exists (stack
  `pretokengen-data`, deployed with `Stage=test`).
- **Stack naming is unpinned + has a footgun:** `Stage` is only a parameter that names the
  function/layer (`pretokengen-${Stage}`), NOT the stack. Re-deploying the SAME stack
  (`pretokengen-data`) with `Stage=prod` would RENAME/REPLACE `pretokengen-test` →
  `pretokengen-prod`, destroying the working test-pool Lambda. Only manual discipline (pick a
  NEW stack name, e.g. `pretokengen-prod`) prevents this — the tooling doesn't.
- The frontend had the same class of gap: a required build env var (`VITE_MEMBERS_API_BASE_URL`)
  was simply missing from `deploy-frontend.yml`, so prod silently shipped the localhost fallback
  (fixed 2026-09-23, PR #16). Root cause = deploy config not complete/committed.
- Credential fragility compounds it: repo `.env` static AWS keys override `AWS_PROFILE`, so a
  plain profile invocation silently hits the WRONG account (see steering 41 / the export-role-creds
  workaround).
FIX (make prod deploys stable + repeatable BEFORE more high-blast-radius prod steps like the
Pool A trigger attach):
- Add a committed `samconfig.toml` per SAM app (`sam/pretokengen`, and confirm `sam/members`)
  with DISTINCT `test` and `prod` environments — each pinning a distinct stack name + params
  (Stage/Region/GovernanceProjectionTableName), so `sam deploy --config-env prod` is one
  reviewed, repeatable command (no inline params, no rename-the-test-Lambda trap).
- Add a GitHub Actions deploy workflow for `sam/pretokengen` (like `deploy-sam-members.yml` /
  `deploy-frontend.yml`) via OIDC, no stored secrets.
- Until then, PHASE CE manual deploys MUST use a NEW stack name for prod and a changeset review.

# SAM Members edge can't resolve an active tenant for multi-tenant users (403)
Discovered during s5d PHASE CE (2026-09-23). BLOCKS s5d PHASE D.
`sam/members/handler/app.py` `_establish_tenant_context(entitlement)` requires
`len(entitlement.tenant_keys) == 1`, otherwise raises `TenantResolutionError` -> 403.
It never inspects the `X-Tenant` request header. Consequence: any user with access to
more than one tenant (e.g. peter@pgeers.nl = 7 tenants, webmaster@h-dcn.nl = ["mytest3","h-dcn"])
gets a 403 from the Members API even though their token correctly carries the
`h-dcn:[members:admin/export/read/write]` capabilities. This surfaces as "no members shown"
in the UI. The early deny happens at the edge (~3.5ms), so members-prod app logs show no error.

This is NOT the intended model. The active tenant is a PER-REQUEST selection:
- the client sends the chosen tenant via `X-Tenant`,
- the edge validates that tenant is a member of the caller's verified tenant list
  (from the token / entitlement), and
- proceeds with that single active tenant for the request.
A single-tenant user is just the degenerate case (one allowed tenant).

This exact pattern is already proven in the Flask/UI side of myAdmin:
`backend/src/auth/tenant_context.py` (`get_current_tenant` / `validate_tenant_access`)
validates `X-Tenant` against the verified `custom:tenants` list. The SAM edge should mirror it.

FIX: replace the `len(tenant_keys) == 1` check with:
- read `X-Tenant` header,
- if absent and exactly one tenant -> use it (back-compat),
- if present -> require it be in `entitlement.tenant_keys`, else 403,
- if absent and multiple tenants -> 400/409 asking the client to specify a tenant.
Then scope the rest of the request to that single active tenant.

- ADR-worthy (active-tenant resolution contract for the SAM edge).
- Unblocks s5d PHASE D. PreTokenGen trigger is already attached to Pool A (harmless) and
  the token capabilities are correct; only the edge resolution is wrong.
- Related: this is the first of the 3 remediation specs; #2 (projection role#/module# reconcile)
  and #3 (codify SAM deploys) are the other two.


# Member modal UI
The modal is one long list of fields with functional seperator. It would be nice to have 3 or 4 columns on a desktop window reducing columns to 1 on a mobile

# Code qaulity and Full test suite
Do they need updates to supprt sam platform