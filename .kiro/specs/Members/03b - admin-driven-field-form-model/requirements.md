# Requirements Document

## Introduction

This spec removes accumulated HARDCODED BINDINGS between member fields — business rules the
software imposes that OVERRULE the tenant administrator's configuration — and the dead/stale code
left behind, so the field/form behaviour becomes predictable and the codebase SHRINKS. It concerns
the **SAM Members module** (`sam/members/`) and its React frontend.

The governing principle (owner, `analysis.md`): the tenant administrator DECIDES what each member
field is and does; the software STORES those choices and APPLIES them, and does NOT overrule the
admin with hardcoded rules. On an application submission the human admin is the backstop (reject or
fix in members-CRUD), not a wall of guards. The one system invariant is that `member_id` (the
system-generated UUID) is intrinsically required; every other field is a tenant-admin configuration
field.

That principle is largely ALREADY the product intent (see Product Context below); it is NOT re-
specified here. 03b's own work is the subtractive part: REMOVE the bindings that violate the
principle, REMOVE dead code, and make enum-label handling uniform. Where this spec's direction
changes the documented data model, it is FLAGGED as a conflict and its mechanics are proven by a
read-only blast-radius trace in the design phase — no code until design is approved.

Feasibility is not in question, and the data model is GENERIC: a field in `config#fields` is a JSON record with no fixed attribute schema, so functional attributes can be added to a field and acted on — exactly how `status` carries `required` and how the code already added `application_*` attributes with no schema change. The unified model is therefore CONSISTENT with the data model, not a fight against it. The only real data-model change is relocating the two shapes that store values ELSEWHERE and have side-effecting consumers — `region` (on `config#scope`, feeding access grants) and `membership_type` (catalog rows, referenced by member records). The open question for those two is MIGRATION SAFETY, which a design-phase proof must establish (Requirement 3).

## Glossary

The verbs of this spec (not the storage fields — those live in the data model):

- **Hardcoded_Binding** — a business rule in code that ties one field's behaviour to another, or
  forces a field's behaviour, WITHOUT the admin authoring it (e.g. "a platform-required field may
  not be made not-required on the form"). The subject this spec removes.
- **Overrule** — the software substituting its own rule for the admin's configured choice. 03b
  removes every overrule except the single `member_id` invariant.
- **Derive** — compute one artifact from another the admin DID author (e.g. the `config#scope`
  dimension derived from a scope field's own options). A binding that FLOWS FROM the admin's
  choice — kept, because it does not overrule the admin.
- **Grandfather** — keep an existing stored value valid, displayed, and round-trippable even though
  it is no longer OFFERED for new entries. The behaviour a retired-value mechanism must preserve.
- **Store_Verbatim / Apply** — the two things the software MAY do with a config: hold the admin's
  choice unchanged, and enforce it. As opposed to Overrule.
- **Dead_Code** — code/config paths no one emits or reads (confirmed instance: the retired
  `config#views` residue). Removed by this spec.

## Product Context (NOT 03b requirements — recorded to anchor scope)

The admin-decides principle and the field model are PRODUCT behaviour documented outside this spec;
03b does not re-specify them, it removes what contradicts them. Sources:

- `sam/members/docs/data-model.md` + `config-guide.md` — the authoritative stored shapes
  (`config#fields`, `config#scope`, the `membershiptype#<code>` catalog, member records).
- Steering `38-sam-module-field-config.md` (field model: one authoring surface, Change-Op,
  per-language labels) and `35-sam-module-architecture-sam.md` (layering: React presents, Lambda is
  authoritative, repository owns DynamoDB).

The product already holds: `member_id` is the system identity; fields are tenant-configured; enum
`value` is language-neutral while `label` is per-language. 03b RELIES on these; it does not restate
them as its own acceptance criteria.

## Requirements

### Requirement 1: Remove hardcoded field-to-field bindings that overrule the admin

**User Story:** As a tenant admin, I want the platform to apply exactly the field configuration I set, so that it does not silently overrule me with rules I never authored.

#### Acceptance Criteria

1. THE no-relax binding (a platform-required field may not be set not-required on the application form) SHALL be REMOVED, so the admin freely sets application-requiredness for any field
2. THE forced-required and forced-visible special-cases (incl. any that single out membership_type) SHALL be REMOVED, so no field is forced on the form or forced required except by the admin's own configuration
3. AFTER removal, the only requiredness the software enforces independent of tenant config SHALL be the `member_id` invariant; every other required/visible decision SHALL come from the admin's configuration
4. THE software SHALL NOT reject a field-configuration combination the admin chose on the basis of a Hardcoded_Binding the admin did not author
5. THE precise code to remove SHALL be identified by a read-only blast-radius trace of the SAM Members module in the design phase (direction decided here; exact locations proven in design), so no consumer silently breaks

### Requirement 2: Config toggles persist both ways (no dropped write)

**User Story:** As a tenant admin, I want turning a field setting OFF to stick, so that a correction does not silently revert to the previous value.

#### Acceptance Criteria

1. WHEN the admin turns a field's `required`, `application_visible`, or `application_required` OFF and saves THEN the write SHALL emit an explicit value under the Change-Op contract (never a dropped `undefined`), and a reload SHALL show OFF
2. WHEN the admin turns any of those ON and saves THEN a reload SHALL show ON
3. THE fix SHALL apply uniformly to every field in every functional group, not a special-cased subset
4. (Confirmed scope note) the `required` toggle was fixed for staff records in 03a; this requirement extends the SAME fix to the application-form toggles (`application_visible`, `application_required`), which still drop the OFF write

### Requirement 3: One unified enum-field model (relocate the two side-effecting shapes)

**User Story:** As the platform owner, I want every selectable field to be one kind of thing — an enum whose features (requiredness, retired-value, scope, application-form behaviour) hang off the field's own options — so that the module has one model to reason about instead of several divergent ones.

> **Data-model framing (owner-confirmed): the model is GENERIC — a field is a JSON record with no
> fixed attribute schema, so features-as-attributes already fit it.** `status` (inline `choices`)
> and the `application_*` attributes already live ON the field under this generic model; `status`
> needs no relocation, and `application_*` is a DOCUMENTATION GAP (written by the code, not yet in
> `data-model.md`/`config-guide.md`), NOT a structural divergence — closed by AC 4.
>
> The only real data-model CHANGE is the two shapes that store values ELSEWHERE and have
> SIDE-EFFECTING consumers, hence the migration-safety proof (AC 5):
> - **`region`** — values live on `config#scope`, the field is deliberately empty; feeds
>   `user_tenant_scope` access grants (a careless move could STRAND a grant).
> - **`membership_type`** — separate `membershiptype#<code>` catalog rows with an `active`
>   soft-delete flag, referenced by stored member records (a careless move could ORPHAN a
>   member's `membership.membership_type`); no authoring UI exists today.

#### Acceptance Criteria

1. THE target model SHALL be: a selectable field is a single ENUM; its options each carry value + per-language label + a retired/grandfather flag; and the field carries its feature attributes (requiredness, application-form flags, scope-binding) directly on the field — no separate per-kind storage model and no `active_only` catalog apparatus
2. FOR a retired value THE behaviour SHALL be Grandfather semantics: hidden from the picker for new/changed records, WHILE existing stored values equal to it are retained, displayed, and accepted on read and validation; and the retired/active state SHALL be freely toggleable both ways
3. THE unification SHALL relocate the two side-effecting shapes (`region` from `config#scope`, `membership_type` from the catalog) onto the field model; `status` and the `application_*` attributes already fit the generic model and SHALL NOT require relocation
4. THE `application_*` attributes (`application_visible` / `application_required` / `application_choices`) SHALL be documented in `data-model.md` as part of the field model (closing the documentation gap)
5. THE design phase SHALL produce a MIGRATION-SAFETY PROOF — gating implementation and requiring owner sign-off BEFORE any code — that, against the REAL stored h-dcn data, maps every currently-stored `region` and `membership_type` value onto the unified model and shows that NO `user_tenant_scope` grant is stranded and NO stored member's `membership.membership_type` reference is orphaned
6. IF the proof shows relocating a shape is unsafe THEN unifying only the BEHAVIOUR (Grandfather + uniform features) for that shape, without moving its storage, SHALL be the accepted fallback — decided in design and reflected back into this requirement

### Requirement 4: Scope dimension is DERIVED from the field (the one binding kept)

**User Story:** As a tenant admin, I want to manage a scope field's values only in the field editor, so that the access-control dimension always matches the field's options without my editing anything twice.

> **Two things, both stay working.** SCOPE DEFINITION — which field is a scope field and its values
> — is authored on the SAM side (`config#scope`). USER ACCESS — `user_tenant_roles` /
> `user_tenant_scope`: which user is granted which values — is authored in Flask and PROJECTED into
> SAM as `scopegrant#` rows. This spec changes the DEFINITION's authoring surface (the field editor)
> and must leave the Flask→SAM projection of roles/grants working UNCHANGED.
>
> **Save triggers an update of TWO items** (the UI trigger): saving a scope field (1) derives and
> writes the `config#scope` definition, and (2) keeps the Flask side (`members.scope_dimensions`
> mirror the grant validators read) consistent so `user_tenant_scope` keeps working.
>
> **A breaking change is a combined Tenant_Admin + SysAdmin effort (prior decision, recorded in
> `scope-dimension-authoring-trigger.md`).** The reconciliation that classifies routine vs.
> grant-orphaning changes EXISTS (`UserTenantScopeService.reconcile_scope_change`) and is unit-
> tested, but is currently UNWIRED — no save path calls it. 03b must WIRE IT INTO the scope-field
> save; it is NOT a free "reuse".

#### Acceptance Criteria

1. THE field editor SHALL be the single authoring surface for a scope field's vocabulary; there SHALL be no separate standalone scope-dimension editor
2. WHEN the admin saves a scope field THEN the save SHALL update BOTH items: derive and write the SAM `config#scope` definition (authoritative), then keep the Flask `members.scope_dimensions` mirror consistent (the frontend-mirror the grant validators read); the Flask→SAM projection of `user_tenant_roles` / `user_tenant_scope` grants (`scopegrant#` rows) SHALL be left UNCHANGED and keep working
3. WHEN the authoritative `config#scope` write fails THEN nothing SHALL be mirrored to Flask AND the admin SHALL see a caller-safe error
4. WHEN only the Flask mirror write fails THEN SAM SHALL remain authoritative AND the admin SHALL be offered a retry of just the mirror
5. WHEN a save is ROUTINE (adds a dimension or value, stranding no existing grant) THEN it SHALL apply and remind the admin to review user scope grants
6. WHEN a save would rename or remove a value/dimension that strands an existing `user_tenant_scope` grant THEN it SHALL be BLOCKED with a "contact your System Administrator to realign grants" message (a breaking change is a combined Tenant_Admin + SysAdmin effort); the save SHALL NOT silently strand a grant. This SHALL be implemented by WIRING IN the existing `reconcile_scope_change` / `assert_appliable` reconciliation (currently built but unwired), not by reimplementing it
7. Access-control RESOLUTION (which members a scoped caller may see) SHALL be UNCHANGED by this spec; only the authoring/derivation trigger and the wiring-in of reconciliation are added, with regression coverage

### Requirement 5: Uniform per-language enum labels in display and filters

**User Story:** As a user, I want every enum field to show its label in my language in the table, detail, and filters, so that I never see a raw stored key.

#### Acceptance Criteria

1. FOR every enum field THE table and detail display SHALL show the resolved per-language label (`label[active locale] → en → nl → value`), never the bare stored value when a label exists
2. FOR every enum field THE filter control SHALL present and match on the resolved per-language label, not the stored value
3. THE Members status-field filter SHALL use the resolved label like every other enum filter (correcting the recorded case, `findings.md` #2, where it keyed off the stored value)

### Requirement 6: A data migration is required, naming each table/row, run TEST and PROD identically

**User Story:** As the platform owner, I want the stored data reshaped to the unified model by a controlled, verifiable migration that names exactly which rows in which tables it touches, so that no tenant's live data is left half-converted or diverging between environments.

> **Scope note (corrected against spec 02):** `config#fields` and `config#scope` are NOW authored
> directly by the SAM write path in `governance_projection` (they are no longer projected from
> MySQL — `data-model.md`'s "projected from MySQL" line is stale for these two rows and is updated
> by Requirement 8). So this is a SAM-plane (DynamoDB) migration across TWO tables, each with its
> `test_` sibling; the MySQL `members.*` params are SAM-owned mirrors, not the migration source.

#### Acceptance Criteria

1. THE migration SHALL state, per change, the exact table + row it rewrites:
   a. `config#fields` (in `governance_projection` / `test_governance_projection`) — relocate `region`'s values onto the field, fold `membership_type` into the field's enum `options` with the `allowed`/retired flag, and carry any 03a `choices`→`options` backfill not yet applied to that environment;
   b. `config#scope` (same table) — reconcile the derived dimension values with the relocated `region` field (Requirement 4); a value RENAME/REMOVE that would strand a `scopegrant#` / `user_tenant_scope` grant is BLOCKED pending SysAdmin realignment (Req 4.6), never silently applied by the migration;
   c. `sam-members` / `test_sam-members` — retire the `membershiptype#<code>` catalog rows once folded into the field, leaving existing member records' `membership.membership_type` references valid (grandfathered, not orphaned)
2. THE migration SHALL be idempotent and re-runnable, and SHALL back up every affected row (per table) before writing
3. THE migration SHALL be preceded and followed by an integrity scan asserting zero un-migrated rows, zero stranded grants, and zero orphaned member references, consistent with the Requirement 3.5 proof
4. THE migration SHALL be run against TEST (`test_*` tables) and PRODUCTION (unprefixed tables) IDENTICALLY, each integrity-scan-gated, before `test → main` is considered safe (promotion/migration-parity gate, analysis D5); account targeting per steering 23/41 (`nonprofit-deploy`, 506221081911)
5. IF Requirement 3.6 selects the behaviour-only fallback for a shape THEN no storage migration SHALL run for that shape, and the acceptance criteria above SHALL cover only the shapes actually relocated

### Requirement 7: Remove dead and not-asked-for code

**User Story:** As the platform owner, I want dead and unrequested code gone from the Members frontend and backend, so that the module is smaller and easier to reason about.

#### Acceptance Criteria

1. 03b SHALL NOT touch `config#views` (neither the leftover rows nor the cleanup routine). The user-preferred-columns feature it belonged to is a VALID requirement that was removed during an earlier spec over an unresolved error; it is DEFERRED (Out of Scope), not dead-to-delete — removing the residue now could make reviving the feature harder
2. THE removed-binding plumbing from Requirement 1 (the no-relax / forced-required / forced-visible machinery and its tests) SHALL be deleted, not merely disabled
3. THE design-phase trace SHALL enumerate further dead/stale paths in the Members frontend and backend (unused builders, readers, options no longer reachable after Requirements 1 and 3) for removal in THIS spec
4. THE change SHALL result in a net DECREASE in lines of code across the touched Members modules

### Requirement 8: Governance definition-of-done

**User Story:** As the platform owner, I want the steering and docs updated alongside the code, so that the written model matches reality after the removals.

#### Acceptance Criteria

1. ANY steering file that documents a removed rule (candidate: `38-sam-module-field-config.md`) SHALL be updated within THIS spec
2. `sam/members/docs/data-model.md` SHALL be updated to reflect the final enum/retired-value model decided in design (Requirement 3) and the removed `config#views` residue
3. THE CI/CD quality gates and the promotion/migration-parity gate (below) SHALL be honored before `test → main`

## Out of Scope

- Access-control scope RESOLUTION (who-sees-what) beyond the authoring/derivation trigger (Req 4.6).
- The generic json-editor framework extraction (analysis D3: Members-specific, no alignment now).
- OAuth, session-hardening, and tooling backlog items.
- User-preferred overview columns (the retired `config#views` / `view_contexts` feature): a VALID, DEFERRED requirement — not revived and not deleted by 03b; `config#views` residue is left untouched.
- A codebase-wide error-handling sweep: 03b uses caller-safe errors on its OWN surfaces; it does
  not take on `error-exposure.md`'s scope.

## CI/CD and Promotion (detailed per-task in tasks.md, steering 43)

- Quality gates: CodeQL + GitGuardian per PR; the nightly Full Test Suite.
- Frontend changes deploy only from `main` (the TEST frontend is the local dev server); SAM changes
  deploy on push per the `deploy-sam-*` paths.
- Promotion gate (analysis D5): `test → main` is BLOCKED until 03b lands AND the production
  `choices`→`options` migration (03a parity) plus any 03b data migration are run against PRODUCTION,
  each integrity-scan-gated, identically to TEST.

## Dependencies and References

- `analysis.md` (decisions D1–D5), `principle-and-simplification-seed.md` (the promotion gate).
- `sam/members/docs/data-model.md` + `config-guide.md` (authoritative stored shapes).
- Steering (per-task citations in tasks.md): 11-tech-stack, 35-sam-module-architecture,
  38-sam-module-field-config, 39-backend-data-access-sam-dynamodb, 36-config-and-parameters,
  32-frontend-ui, 33/34-testing, 30-backend-api-flask-mysql (scope mirror + caller-safe errors),
  40-spec-workflow, 43-cicd-deploys, 23-aws-accounts, 41-shell-environment, 42-local-dynamodb-testing.
- Absorbs backlog items: `scope-dimension-authoring-trigger.md` (via Req 4) and `findings.md` #2
  (via Req 5).
