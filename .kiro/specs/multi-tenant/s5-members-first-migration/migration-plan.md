# S5 — Members-first migration plan (h-dcn → myAdmin platform)

- Status: Draft (the plan; each step becomes tasks when executed)
- Companion: `members-wireframe.md` (current-state scope of the app being migrated).
- Decision of record: ADR 0003 (platform base + SAM-backed modules), ADR 0004
  (verified-JWT-only), ADR 0005 (two-pool identity + MySQL SoR + projection), ADR 0006
  (entitlement-in-token; functions available for adoption).
- Governing user directions (this plan implements them):
  1. **Members is the first app to migrate**, done in independently-deployable steps.
  2. **New tables** for the migrated app so the **existing h-dcn keeps running** in
     parallel — no big-bang, no breaking the live app.
  3. Use **myAdmin's proper app tooling** (module registry, `tenant_modules` entitlement,
     the `sam/shared` verified-auth + entitlement toolkit, the S3 projection, `LeadingKeys`).
  4. The AWS-footprint consolidation (S3/SNS/SES/DynamoDB → shared portal account) is
     **deferred until AFTER this first migration** proves the pattern.
  5. The first migration ends at an explicit **Go / No-Go** decision point for further
     migrations, plus a **lessons-learned** capture.

## Principle: parallel-run, additive, reversible

The migrated Members app is built **alongside** the live h-dcn Members app, reading/writing
**new tenant-scoped tables**, entitled through myAdmin's module system. The live h-dcn app
is untouched and keeps serving members throughout. At each step we can stop and still have a
working live app. Nothing is cut over until the Go/No-Go gate says so.

## Design target (best practice from the start — no double steps)

h-dcn's Members backend is ~18 one-Lambda-per-action handlers. That granularity is a
learning-curve artifact (h-dcn was the first Kiro/TS/Python/AWS project), **not** a design
to preserve. The migration goes **straight to the best-practice shape** — we do not port
18 handlers 1:1 and then refactor (that would be double work). The target:

- **Members is ONE module.** A single SAM-backed deployable — a thin Members API Lambda
  with **internal routing** by method/path (create/get/list/update/delete/export,
  memberships, transitions, delegates, payments) — mirroring how myAdmin's Flask modules
  already work (one app, many routes). The verified-auth + entitlement toolkit is adopted
  **once**, not 18 times; the auth→validate→CORS→response boilerplate exists in one place.
- **Reuse** h-dcn's *business* logic (regional access, membership workflow rules,
  response shapes) — that is real domain value. **Replace** the structure (18 Lambdas →
  one module) and the auth layer (unverified `extract_user_credentials` → myAdmin verified
  `sam/shared`).
- **New tenant-scoped tables** so live h-dcn keeps running unchanged; nothing cut over
  until the Go/No-Go gate.

## The steps (each independently deployable)

### Step 1 — Design the consolidated Members module + its tenant-scoped data model
- Define the single Members module: its internal routes (the union of the 18 handlers'
  behaviours), the reused business rules (regional access, workflow), and the new
  tenant-scoped DynamoDB table design (PK `tenant_id`, SK member/membership id; counters
  + member-payments as needed), `LeadingKeys` IAM. One deployable unit, myAdmin module
  tooling. This is design/spec, deployable as the module skeleton.
- **Fixed vs. variable fields (data-model principle — see `members-wireframe.md`).** Design
  the member data model in two layers from day one:
  - **Fixed (platform base registry):** **personal data** + **membership data** — the same
    for every tenant, first-class attributes of the tenant-scoped `members` table, with
    canonical field keys/validation from the base registry.
  - **Variable (per-tenant overlay):** **club details** (h-dcn's Motor/region/club-specific
    fields) resolved per `tenant_id` via the per-tenant field-config mechanism
    (myAdmin `tenant_template_config` / `FieldConfigMixin` + h-dcn's hybrid field registry),
    applied over the fixed core — so a second tenant later needs a new overlay, **not** a
    schema change.
  - Split h-dcn's existing member fields accordingly (personal+membership → fixed base;
    club/Motor/region-specific → variable overlay). **Tenant `h-dcn`** is the first overlay.

### Step 2 — Register Members as a myAdmin module (entitlement plumbing)
- `members` entry in `MODULE_REGISTRY` (backing: sam) + entitle the pilot tenant via
  `tenant_modules`; confirm the S3 projection carries the tenant's `members` module +
  roles and `get_entitlements`/`has_capability` answer for `members`. **Deployable/reversible.**

### Step 3 — Stand up the Members module (read path) on myAdmin tooling
- Build the single Members Lambda with internal routing for the READ routes
  (`get_member*`, lists, export), using the vendored `sam/shared` verified-auth +
  entitlement toolkit **once**, reusing h-dcn's regional-access business logic, reading
  the new tenant-scoped tables (`tenant_id` partition + `LeadingKeys`). API contract the
  frontend expects is preserved. **Deployable** (read module + pilot/shadow route);
  **reversible** (pilot route only; live h-dcn untouched).

### Step 4 — New tenant-scoped tables + backfill (parallel to h-dcn's)
- Create the new tables (data account, PAY_PER_REQUEST, outside-CFN/retain per
  `aws-accounts.md`). Backfill existing member records stamped with the pilot `tenant_id`
  (dry-run first; the h-dcn `migrationHDCNLedenbestand` import is prior art). The live
  h-dcn `MembersTable` is untouched. **Deployable/reversible** (new tables are a copy).

### Step 5 — Members module write path + workflow
- Add the WRITE/lifecycle routes to the module (create/update/transition/delegates/
  memberships) on the tenant-scoped tables + verified auth, reusing h-dcn's workflow
  rules. Decide dual-write vs. read-replica-until-cutover. h-dcn stays the fallback.
  **Deployable per route group; reversible.**

### Step 6 — Pilot cutover for one tenant/region + soak
- Route real Members traffic for one pilot tenant/region to the migrated module; soak and
  compare against live h-dcn (parity: authz incl. regional, data, API contract, workflow;
  error rates; latency). **Deployable (routing); reversible (route back to h-dcn).**

## The Go / No-Go decision point (end of the first migration)

After Step 7's soak, hold an explicit **Go / No-Go** review for migrating further apps
(Events, Webshop). Decide against concrete criteria captured during the pilot:

- **Parity:** migrated Members matches h-dcn behaviour (authz incl. regional, data, API
  contract, workflow) for the pilot tenant.
- **The toolkit held:** the myAdmin verified-auth + entitlement + projection + tenant-scoping
  tooling was sufficient — what was reusable as-is, what needed change (feeds the roadmap).
- **Operational:** deploy/rollback per step worked; cold-start/latency within budget; the
  cross-account trigger (if the live Pool A PreTokenGen trigger was wired for the pilot)
  behaved; fail-safe held (no broken logins).
- **Effort/ROI:** actual effort per step vs. estimate → is app-by-app migration worth
  continuing, or should the approach change?

Outcome is recorded (Go → proceed to the next app with the refined tooling; No-Go →
document why + what would change the decision) in `go-no-go.md` (a deliverable of the
pilot), with **lessons learned** feeding a roadmap revision.

## What this migration deliberately defers

- **AWS-footprint consolidation** (move myAdmin's S3/SNS/SES/local-DynamoDB + shared
  services into the shared portal/data account) — **after** this first migration, informed
  by it. Not a prerequisite.
- **Production Pool A PreTokenGen trigger** (S4 T18) — wired only if/when the pilot needs
  live entitlement in the token; the functions are already built + tested and available to
  adopt. The pilot can run against the test pool first.
- **Events / Webshop** migrations — gated behind the Go/No-Go.
- **Frontend consolidation** — the pilot is backend-first; UI stays on h-dcn until parity.

## Tooling this reuses (myAdmin, already built)

- `sam/shared/auth_utils.py` — verified JWT + `get_verified_claims`/`get_groups` +
  `get_entitlements`/`has_capability` (S2 + S4).
- `sam/shared/entitlement_claim.py` — the vendored claim decoder (S4).
- `services/module_registry.py` + `tenant_modules` — module entitlement (S1/S3).
- The S3 one-directional projection + `projection_schema` + `LeadingKeys` plan (S3).
- The S4 entitlement resolver/codec + PreTokenGen Lambda (built + tested; trigger deferred).
