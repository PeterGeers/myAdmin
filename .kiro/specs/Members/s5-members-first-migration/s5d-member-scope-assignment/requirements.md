# Requirements Document

## S5d — Member-user scope assignment (field-value scope, Tenant-Admin managed) — Requirements

- Status: **Draft** (requirements phase — check in before design)
- Builds on: **s5c** (`.kiro/specs/multi-tenant/s5c-members-runnable-in-spa/`) — the Members surface,
  the `members.scope_dimensions` config, the `scopegrant#<email>#<dimension>` projection row, and the
  module's `resolve_scope_access` are all in place. s5d REPLACES how a member-user's scope is
  **authored + stored**, keeping the projection/enforcement shape downstream.
- Not in production: there are **no live tenants on this path**, so s5d makes a **clean break** — no
  compatibility bridge, no data migration, and the legacy `Regio_*` role-name scope encoding is
  **removed** (not deprecated).
- Governing steering: `20-platform-architecture`, `21-identity`, `31-backend-database`,
  `32-frontend-ui`, `33/34` (testing), `35-sam-module-architecture-sam`, `40-spec-workflow`.

## Introduction

Today a member-user's scope (which subset of members they may see) is encoded as a **role name** in
`user_tenant_roles` (e.g. `Regio_Oost`), and `ProjectionSync` decodes that string back into a
`scopegrant#<email>#region = ["Oost"]` row. This conflates *roles* (what a user may do) with *scope*
(which records a user may see), leaks a `Regio_` verb prefix into role names, is awkward for
multi-value and multi-dimension scope, and — critically — **cannot be assigned through the product**
(the Tenant-Admin role picker only offers module-capability roles, never the config-driven scope
values), so scope can only be set by a direct DB write.

s5d adopts the simpler, correct model the user articulated:

> **Scope is a member FIELD plus a VALUE (or values) to filter on.** A user's visible members are the
> rows where the member's value for that field intersects the user's granted values.

Scope becomes an explicit per-user-per-tenant grant, stored in a new **`user_tenant_scope`** table
(JSON, keyed `(email, administration)`), authored through a Tenant-Admin UI (a fuzzy multi-select of
the field's plain values per scope dimension), decoupled entirely from `user_tenant_roles` (which
stays PURE capabilities). Multiple scope dimensions (multiple fields) and multi-valued membership
(a user or a member holding several values) are first-class.

## Glossary

- **Scope dimension** — a tenant-designated MEMBER FIELD used to scope visibility (h-dcn: `region`).
  Its allowed **values** are the field's values (tenant PARAMETER data, from `members.scope_dimensions`
  / the field's enum choices). A tenant MAY designate more than one (multi-dimension).
- **Scope grant** — the set of values a specific user is allowed to see for a dimension, e.g.
  `region: ["Oost","Friesland"]`, or the **all** sentinel (`["*"]`) meaning every value.
- **`user_tenant_scope`** — the NEW governance table (MySQL) that stores a user's scope grants per
  tenant as JSON: `{ "<dimension>": ["<value>", ...] | ["*"], ... }`, keyed `(email, administration)`.
- **`scopegrant#<email>#<dimension>`** — the DERIVED DynamoDB projection row the Members module reads
  at request time (UNCHANGED shape); s5d builds it FROM `user_tenant_scope`, not from a role name.
- **multi_valued (OUT OF SCOPE)** — a legacy `members.scope_dimensions` flag for a member holding
  several values of one dimension. NOT realized and NOT required; s5d treats a member as SINGLE-valued
  per scope field and removes this flag. (The USER GRANT is still multi-value; the MEMBER is not.)
- **Deny-by-default** — a member-capable user with NO scope grant for a required dimension sees
  **nothing** (Property 4). Absence of a grant is deny, never allow-all.

## Guiding principles (settled — requirements enforce them)

- **Scope = field + value(s).** Enforcement is a filter: a member is visible when the member's
  value(s) for the scope field intersect the user's granted values. `["*"]` = unfiltered (all).
- **Roles and scope are separate concerns.** `user_tenant_roles` holds ONLY capability roles
  (`Members_CRUD`/`Members_Read`/`Members_Export`/...). Scope lives in `user_tenant_scope`. The
  `Regio_*` role-name scope encoding is REMOVED.
- **Plain values, no verb prefix.** The admin selects and the system stores the plain field value
  (`Oost`), never `Regio_Oost`.
- **MySQL is system of record; projection is one-directional** (ADR 0005). `user_tenant_scope` →
  `scopegrant#…` via `ProjectionSync`; the module never reads MySQL and never invents scope.
- **Generic + tenant-agnostic.** No `if tenant == "h-dcn"`. Which field(s) are scope dimensions and
  what values they carry is tenant config/parameter data.
- **Verified-JWT only / scope off the token** (ADR 0004/0006). Scope is resolved from the projected
  grant keyed by the verified `email`, never carried on the token, header, or body.

## Requirements

### R1 — Store member-user scope in a dedicated per-user-per-tenant table

- **R1.1** The system SHALL persist a member-user's scope in a NEW MySQL table
  **`user_tenant_scope`**, keyed uniquely by `(email, administration)`, with a JSON `scopes` column
  holding `{ "<dimension_key>": ["<value>", ...] | ["*"] }` and standard `created_at`/`created_by`
  (steering 31: `administration NOT NULL`, `idx_administration`, FK to `tenants`).
- **R1.2** `user_tenant_roles` SHALL hold ONLY capability roles. The `Regio_*` (scope-in-role-name)
  encoding SHALL be REMOVED from the codebase (decode path, available-roles expansion attempts, and
  any seeded `Regio_*` rows). Removing scope from a role SHALL NOT remove the user's capability roles.
- **R1.3** A user's scope record SHALL be independent of their role rows: creating, updating, or
  deleting a scope grant SHALL NOT read or write `user_tenant_roles`, and vice versa.
- **R1.4** The JSON `scopes` value SHALL support MULTIPLE dimensions (one key per scope field) and
  MULTIPLE values per dimension (a list of VALUES ONLY — no labels), plus the all-access sentinel
  `["*"]` per dimension. Labels are resolved for display at render, never stored (OD3).
- **R1.5** WHEN a scope record is absent for a `(email, administration)`, the user SHALL have NO
  scope grant for any dimension (deny-by-default downstream), never implicit all-access.

### R2 — Derive the projection from `user_tenant_scope` (not from role names)

- **R2.1** `ProjectionSync` SHALL build each `scopegrant#<email>#<dimension>` projection row by
  reading `user_tenant_scope` for the tenant, emitting one row per (user, dimension) that has a grant,
  with `values` = the granted plain values, or `["*"]` for all-access.
- **R2.2** The role-name decode (`_decode_grant_for_dimension` / `_scoped_role_prefix` and the
  `Regio_` prefix machinery) SHALL be removed; scope grants SHALL no longer be derived from
  `user_tenant_roles`.
- **R2.3** WHEN a user has a scope record but a dimension is absent from its JSON (or maps to an empty
  list), the builder SHALL emit **no row** for that (user, dimension) — deny-by-default (R2.6 of s5c).
- **R2.4** A scope write (create/update/delete via the Tenant-Admin surface) SHALL trigger
  `enqueue_sync(tenant)` so the projection reflects the change (best-effort; reconciliation backstops).
- **R2.5** The `scopegrant#<email>#<dimension>` row SHAPE and the module's `resolve_scope_access`
  SHALL be UNCHANGED — only the SOURCE of the grant values changes.

### R3 — Enforcement: filter members by field value(s) ∩ granted value(s)

- **R3.1** A user's visible members SHALL be exactly those whose value(s) for the scope dimension's
  field intersect the user's granted values; `["*"]` SHALL mean unfiltered (all members); no grant
  SHALL mean deny (see nothing) for a dimension the capability requires.
- **R3.2** A member carries a SINGLE value per scope field. A member SHALL be visible for a dimension
  WHEN its (single) field value is one of the user's granted values (i.e. `member.<field>` ∈ grant).
  (Multi-value PER MEMBER — a member in several regions at once — is explicitly OUT OF SCOPE: it was
  never realized and is not required. The USER'S GRANT is still multi-value — a user may be granted
  several values of a dimension, e.g. Oost + Friesland.)
- **R3.3** WHEN a tenant designates MULTIPLE scope dimensions, a member SHALL be visible only if it
  satisfies the scope check for EVERY dimension the user's capability requires (AND across dimensions),
  each dimension evaluated independently against that dimension's grant.
- **R3.4** A scope dimension SHALL bind to a NORMAL member field, and enforcement SHALL read the
  member's value directly from that field (`member.<field>`). The separate `scope_values` bucket
  (and the s5c `_surface_scope_values` workaround) SHALL be RETIRED — there is exactly ONE
  representation of a member's scope value: the field itself. (DECIDED — resolves former OD1.)
- **R3.5** Enforcement SHALL match a member's scope-field value against the granted values by
  **canonicalized equality**: a deterministic canonicalization (trim / case / diacritic / separator
  fold — OD5/R9.6) is applied IDENTICALLY to both sides, then compared for exact equality on the
  resulting CANONICAL value (the single vocabulary of R5.2 / R9). Fuzzy,
  partial, or prefix matching SHALL NOT be used at enforcement time — access control is exact and
  deterministic. This is the third link of the chain: **fuzzy FINDS** (authoring picker, R5.4) →
  **canonical STORES** (the picker always resolves to a canonical value, R5.3) → **exact ENFORCES**
  (here). Because the match is exact, it is CORRECT ONLY IF both sides are drawn from the same
  canonical value set — see R9 (the normalization precondition). A member whose field value is not
  canonical will not match a canonical grant (silent empty result), which R9 exists to prevent.

### R4 — Tenant-Admin authoring of a member-user's scope

- **R4.1** A `Tenant_Admin` SHALL be able to view and set, per member-privileged user in the current
  tenant, that user's scope grant for each enabled scope dimension, by EXTENDING the EXISTING
  Tenant-Admin **user-management screen** (the same place roles are managed) with a per-user scope
  editor — NOT a separate screen. (DECIDED — resolves former OD2.)
- **R4.2** The authoring API SHALL write the user's scope to `user_tenant_scope` for the CURRENT
  (verified) tenant only (Property 1 — no cross-tenant write; tenant from `@tenant_required()`, never
  a body value), validate each value against the dimension's allowed values, and reject unknown values.
- **R4.3** The UI SHALL present, per dimension, a MULTI-SELECT of the dimension's PLAIN values (e.g.
  `Oost`, `Friesland` — never `Regio_Oost`), plus an explicit **All** toggle (→ `["*"]`).
- **R4.4** The UI SHALL support assigning MULTIPLE values (multi-select) and, when the tenant has
  MULTIPLE scope dimensions, an independent selector per dimension.
- **R4.5** Setting a user's scope SHALL be an atomic overwrite of that user's `scopes` JSON (the save
  reflects exactly what the admin selected); clearing all selections SHALL remove the grant (deny).
- **R4.6** Only users who hold a Members capability role in the tenant SHALL be offered a scope editor
  (scope is meaningless without a Members capability); the editor SHALL surface each such user.

### R5 — Value source, labels, and fuzzy picker

- **R5.1** The selectable values for a dimension SHALL come from the MySQL `members.scope_dimensions`
  parameter DIRECTLY (the system-of-record source of truth — OD4): the dimension list and each
  dimension's `values` (aligned with the field's enum choices), presented with i18n labels where
  available. The picker/validation SHALL NOT depend on the DynamoDB projection for the value list.
- **R5.2** Stored and matched values SHALL be the canonical field values (e.g. `Noord-Holland`), so a
  grant matches the member's stored field value exactly (dependency: member data normalized to the
  canonical value set — see s5c region normalization).
- **R5.3** The picker SHALL show the plain value/label; the `scopegrant` shall store the plain value.
- **R5.4** The picker SHOULD support fuzzy/typeahead search over the value list (diacritic- and
  spacing-tolerant, e.g. "noord holl" → "Noord-Holland") as an AUTHORING convenience only; the
  selected result is always a canonical value (fuzzy narrows the list, never changes what is stored).

### R6 — Multiple scope dimensions (generic multi-limiter support)

A tenant SHALL be able to scope on MORE THAN ONE member field — a generic multi-limiter feature. The
dimensions AND together to narrow the visible set (e.g. a soccer club scoping a coach to
`age_group=U15` AND `gender=F` AND `squad=talent`; h-dcn uses a single dimension, `region`). This is
the multi-DIMENSION capability. (Multi-VALUE per MEMBER is OUT OF SCOPE — see R3.2.)

- **R6.1** A tenant SHALL be able to designate MULTIPLE scope dimensions, each binding to a distinct
  normal member field. h-dcn designates exactly one (`region`); the design SHALL NOT hardcode a
  single dimension.
- **R6.2** Each dimension SHALL be independently authorable per user (its own grant in the user's
  `scopes` JSON) and independently enforced; a member is visible only if it passes EVERY dimension
  the user's capability requires (AND across dimensions — R3.3).
- **R6.3** The Tenant-Admin scope-dimension AUTHORING UI (`members.scope_dimensions` editor) SHALL
  support adding/removing scope dimensions ("+ Scope Dimension"), each naming the member field it
  binds to and its canonical value set. The `multi_valued` (per-member) flag is OUT OF SCOPE and
  SHALL be removed from the dimension model rather than left as dead configuration.

### R7 — Tests + verification

- **R7.1** Unit tests SHALL cover: `user_tenant_scope` read/write (round-trip, per-tenant isolation),
  the projection builder deriving `scopegrant#…` from the table (single/multi value, `["*"]`, absent →
  no row), and removal of the role-decode path.
- **R7.2** Enforcement tests SHALL cover: single-value grant narrows correctly; MULTI-VALUE GRANT
  (member's single value ∈ granted list, e.g. Oost+Friesland); MULTIPLE DIMENSIONS (AND across
  dimensions); `["*"]` = all; no grant = deny; unknown value rejected at authoring. (No member
  multi-value case — out of scope, R3.2.)
- **R7.3** An end-to-end check SHALL demonstrate: a Tenant-Admin sets `member-test@example.com` →
  `region: ["Oost"]`; the projection carries `scopegrant#…#region = ["Oost"]`; `list_members` returns
  only Oost members; changing to `["*"]` returns all; clearing returns none.
- **R7.4** Frontend tests SHALL cover the scope editor (renders per-dimension multi-selects of plain
  values, All toggle, fuzzy filter, save writes the selected set).

### R8 — Clean break (no production, no legacy)

- **R8.1** No compatibility bridge, dual-read, or migration of `Regio_*` rows SHALL be built. Any
  existing `Regio_*` rows in dev/test MAY be removed as data cleanup.
- **R8.2** The s5c `scope_values` bucket and its `_surface_scope_values` workaround SHALL be RETIRED
  (per R3.4): a scope dimension binds to a normal member field, which is the single source of truth
  for the member's value. Member records / import SHALL store the value on the field (canonical, R9).

### R9 — Canonical value normalization (precondition for exact-match filtering)

Exact-match enforcement (R3.5) is CORRECT ONLY IF the member's scope-field value and the granted
value are drawn from ONE canonical vocabulary. Dirty/variant data (e.g. `"Noord Holland"` vs
`"Noord-Holland"`, trailing spaces, `"Groningen/Drente"` vs `"Groningen/Drenthe"`) makes an
exact filter silently return nothing. Normalization is therefore a first-class, testable REQUIREMENT
of this feature, not an incidental import detail (this class of bug was hit and fixed in s5c).

- **R9.1** A scope dimension SHALL have a single **canonical value set** — the dimension's authored
  `values` (aligned with the field's enum choices). This set is the vocabulary BOTH the grant and
  the member field are expressed in.
- **R9.2** Member scope-field data SHALL be normalized to the dimension's canonical value set at the
  point it enters the system — on import/migration AND on any member write that sets the field — so
  the stored value is always a canonical value (or explicitly empty), never a variant spelling.
- **R9.3** A member value that cannot be mapped to a canonical value SHALL be surfaced (reported /
  flagged), NOT silently kept as a non-matching variant nor silently dropped — so a normalization
  gap is visible rather than manifesting as an unexplained empty filter.
- **R9.4** The authoring picker's value list (R5.1) and the grant values (R5.2) SHALL come from the
  SAME canonical set, so a granted value always has an exact counterpart in normalized member data.
- **R9.5** Verification SHALL include a check that, for the pilot tenant, EVERY distinct member
  scope-field value is a member of the dimension's canonical value set (no un-normalized values),
  and a test that an exact grant returns the expected non-empty subset.
- **R9.6** Enforcement matching SHALL apply a deterministic canonicalization (trim + case-fold +
  diacritic-fold + separator-fold) applied IDENTICALLY to the member value and the grant value, then
  compare for equality (DECIDED — OD5, defense-in-depth on top of stored-canonical R9.2). The
  canonicalization SHALL be exact-in-canonical-space — never partial, prefix, or fuzzy — and SHALL be
  the single shared function used by both the enforcement path and any normalization-at-write (R9.2).

## Resolved design decisions (were open questions — now settled; no open items remain)

All design questions raised during requirements are RESOLVED and folded into the requirements
above. Recorded here for rationale/traceability; none is open.

- **D1 — Member scope value: a NORMAL member field.** Scope binds to a normal member field; the
  s5c `scope_values` bucket is RETIRED; a member is single-valued per scope field. (R3.4/R8.2;
  multi-value lives only on the USER GRANT, not the member.)
- **D2 — Authoring surface: the EXISTING user-management screen.** The per-user scope editor is
  added alongside role management on the current Tenant-Admin user-management screen, not a new
  screen. (R4.1)
- **D3 — Grant shape: VALUES ONLY.** `scopes` JSON is `{ "<dimension>": ["<value>", ...] | ["*"] }`;
  labels are resolved for display at render, never stored in the grant. (R1.4)
- **D4 — Value source: the MySQL `members.scope_dimensions` param, directly.** The picker and
  authoring validation read the dimension list + values from the system-of-record MySQL parameter,
  not the DynamoDB projection. (R5.1)
- **D5 — Enforcement: canonicalized equality.** A single deterministic canonicalization
  (trim + case-fold + diacritic-fold + separator-fold), applied identically to both sides, then
  exact-equality compare — never partial/fuzzy; the same function normalizes at write. (R3.5/R9.6)

**Status:** requirements COMPLETE — ready for design.
