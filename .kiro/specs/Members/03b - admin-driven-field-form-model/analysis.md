# 03b — Admin-driven field/form model: ANALYSIS (decisions-first, no code)

> Spec-workflow phase 1 (steering 40): understand the problem, map scope overlap with the
> backlog, cite the governing steering, and surface the DECISIONS the owner must make BEFORE
> requirements/design/tasks are written. This doc commits NO design and NO code. It exists so the
> 03b spec is built on explicit owner decisions, not assumptions (the discipline lesson from 03a).
>
> Seed: `.kiro/specs/myBacklog/admin-driven-field-form-model-simplification.md` (the principle +
> the five hardcoded rules). That file also carries the **🚧 promotion gate** blocking `test→main`
> until this simplification lands.

## 1. The principle this spec encodes (owner, 2026-10-29)
> The tenant administrator decides what the application form collects and what is required. The
> software STORES those choices and APPLIES them — it does not overrule the admin with hardcoded
> rules. The form validates data entry against the admin's choices; on submission the admin can
> REJECT the application or MANUALLY FIX it in members-CRUD. The human is the backstop, not a wall
> of hardcoded guards.

**Success test ("done"):** an admin can set any field's booleans FREELY both ways; the owner can
predict EXACTLY what the form + members-CRUD do; the change REDUCES code. No hidden rules.

## 2. Why now (the trigger, evidenced this session)
- Staff-record `required` toggle-off did not persist (sent `undefined` → dropped by the Change-Op
  diff → stored `required:true` never cleared). Interim fix shipped on `test` (commit daa11b3bc),
  NOT deployed, NOT promoted.
- The SAME toggle-off bug is still live for the two application-form booleans
  (`application_visible`, `application_required`).
- 03a added scope write-guards (W1/W2/W3) + a scope-as-separate-source read model that OVERRULED
  the established "field owns its options" design and BROKE the only scope-field authoring path
  (W2). W2 removed (commit 5951b6bd1); W1/W3 still to be re-examined.
- Owner: the accumulation of implicit rules makes behaviour hard to predict and erodes confidence.

## 3. Scope-overlap map with the backlog (the consolidation you asked for)
Read all 9 backlog items. Classification:

### 3a. ABSORB into 03b (reduces/closes the backlog item)
- **`admin-driven-field-form-model-simplification.md`** — IS the 03b seed. Becomes this spec;
  the backlog file is retired/relinked once 03b exists.
- **`scope-dimension-authoring-trigger.md`** — LARGELY folds in: 03b's "field is the single
  authoring surface, admin decides" directly resolves the authoring-trigger question (the field
  editor save must derive + mirror the scope dimension to both planes). CARVE-OUT that STAYS a
  dependency, not absorbed: the cross-plane PROPAGATION mechanics + grant-orphaning reconciliation
  (access-control blast radius). Decision D2 below sets the boundary.

### 3b-align: REDUCE scope of (align toward, don't build)
- **`json-editor.md`** (generic definition-driven typed config editor) — 03b's "two plain
  booleans, no hardcoded rules, definition-driven field attributes" is a concrete step toward that
  framework. 03b can SHAPE its field-attribute model to the json-editor definition contract so the
  later extraction is cheap (rule-of-three, steering 38 rule 7 — do NOT extract now). This REDUCES
  json-editor's future scope; it does NOT close it (draft/publish + the actual extraction remain).
  Decision D3 below.

### 3c. REFERENCE only (distinct; cross-cite, do not absorb)
- **`error-exposure.md`** (two-tier caller-safe error contract) — 03b surfaces validation/fail
  errors; it should CONSUME the error contract's principle (no `str(e)` leak; caller-safe +
  logged) where it raises, but error-exposure is a codebase-wide sweep far larger than 03b. Keep
  separate; 03b references it for its own error surfaces only.

### 3d. OPTIONAL quick win (owner decides in/out)
- **`findings.md` #2** — the Members status-field FILTER uses the enum KEY instead of the
  language LABEL (other enum filters use the label). Adjacent to 03b's enum/label presentation
  area (steering 38 rule 6: value is language-neutral, label is per-language). Small. Decision D4.

### 3e. NO overlap — leave untouched
- `google-drive-oauth-rotation.md` (OAuth client config), `session-hardening.md` (idle
  logout + device trip-logger), `kiro-crew.md` (tooling evaluation). Unrelated domains.

## 4. Governing steering (must be honored / possibly amended)
- **38-sam-module-field-config.md** — the field-model shape 03b edits. Rule 5 "one authoring
  surface, written by Change-Op, one save → one re-projection" is central; rule 6 (labels are
  per-language config values, value is language-neutral) governs the enum/label area + findings#2.
- **36-config-and-parameters.md** — config storage/projection rails; "validate at the seam" (a bad
  value never reaches the projection) is the boundary 03b's admin-choice validation rides.
- **39-backend-data-access-sam-dynamodb.md** — the Change-Op write contract (no whole-record
  replace; absent-vs-null semantics — the exact semantics the toggle-off bug violates) + resolved-
  view read. 03b's toggle fix lives inside these semantics.
- **30-backend-api-flask-mysql.md** — caller-safe errors (ties to error-exposure reference).
- **40 / 43** — spec structure + the mandatory CI/CD tasks; 03b tasks.md must name the gates +
  the branch→env deploy (note: frontend changes only deploy from `main`; TEST frontend is local).
- **Possible steering amendment (governance DoD, steering 40):** if 03b REMOVES the no-relax /
  forced-required rules, any steering that endorses them (candidate: 38, or a Members design doc)
  must be updated in the same spec. To confirm during design.

## 5. DECISIONS
**D1–D5 ALL RESOLVED (owner, 2026-10-29) — recorded below.** 03a's lesson is not to assume these; every decision below is explicit owner intent, not assumption.

**D1 — Hardcoded rules: RESOLVED → ALL REMOVE (owner, 2026-10-29).**
The governing invariant: **the ONLY intrinsically-required field is `member_id` (the system-owned
UUID). EVERY other field — including `last_name` — is a tenant-admin configuration field.** There
are no other platform-required fields and no hardcoded per-field special-cases. Specifically:

  - **D1a — REMOVE** the no-relax lock on `application_required`. The admin freely toggles
    "[required on form]" ON and OFF for any field, platform or tenant-added (no forced-on, no
    disabled toggle).
  - **D1b — REMOVE** the "membership-type is always application-required / always on form"
    special-case. membership_type is NOT special. Because it ALWAYS has a default value, it may be
    left OFF the application form entirely — the application form can supply the default when the
    field is absent. So: not forced required, not forced on-form; the admin decides, and "off the
    form + default applied" is a valid configuration.
  - **D1c — REMOVE** every platform-required field EXCEPT `member_id` (UUID). `last_name` and all
    other fields become ordinary tenant-admin configuration fields (requiredness, on-form, label,
    options — all admin choices). `member_id` is the single system invariant (opaque, system-
    generated, never a human-entered/required-by-config field).
  - **D1d — REMOVE W1 and COLLAPSE "reference" into the enum model.** There is no distinct
    "reference field" kind. membership_type is just an ENUM whose options each carry an **`allowed`
    boolean** (freely toggleable per option): `allowed:true` = offered in the picker;
    `allowed:false` = GRANDFATHERED — not offered for new/changed records, but existing values
    (e.g. `erelid`) are KEPT, displayed, and respected on read/validation. This single flag
    replaces the entire reference apparatus: the separate live-catalog source, the read-seam
    `_active_membership_type_options` injection, the `active_only` / soft-delete filtering, AND the
    W1 inline-options rejection — a net CODE REDUCTION, and it unifies every selectable field under
    ONE enum-with-options model (no per-kind branching), exactly the 03b principle.
    - **`allowed` semantics (three explicit behaviours the old `active_only`/soft-delete only
      approximated):** (a) hidden from the picker for NEW/changed entries; (b) existing stored
      values retained + displayed; (c) still VALID on read/validation for records that already
      carry it. The flag is freely toggleable both ways (re-enable a retired value by flipping it
      back) — not a one-way retirement.
    - **W3 (inline enum cannot be saved with an explicit empty options list):** also REMOVE as a
      hard block — a field with no options yet is a legitimate in-progress/admin state (create the
      field now, add options later), consistent with "admin decides, human backstops". (If any soft
      guidance is wanted it is a non-blocking hint, never a save-blocking guard.)
    - **Design-phase caveat (MUST trace before committing design):** the reference/catalog
      machinery for membership_type may be consumed elsewhere (the membership-type catalog CRUD
      screen, the application form, member-record validation, access/scope). Collapsing to
      enum-with-`allowed` is the right DIRECTION; the blast radius needs a read-only trace in the
      design phase (what reads the catalog / `active_only`) so nothing that depends on it silently
      breaks. Direction decided; mechanics proven in design, not assumed.

**D2 — scope-authoring-trigger: RESOLVED → option (i), FULL trigger folds into 03b.**
03b owns the whole flow: the field-editor save DERIVES the scope dimension from the field's enum
options and writes BOTH planes — SAM `config#scope` (authoritative, `PUT /members/config/scope`)
and the Flask `members.scope_dimensions` mirror (frontend-mirror model, steering-verified). This
includes grant-orphaning handling (a value RENAME/REMOVE that would strand a `user_tenant_scope`
grant is surfaced/blocked, not silently applied — reuse the existing `is_orphaning` reconciliation).
This is consistent with D1d: a field owns its options; the catalog/dimension it feeds is DERIVED.
Access-control blast radius is in-scope and must have explicit regression coverage; access-control
RESOLUTION (who-sees-what) itself is unchanged. This ABSORBS `scope-dimension-authoring-trigger.md`
(that backlog item is retired/relinked once 03b lands).

**D3 — json-editor alignment: RESOLVED → option (ii), Members-specific (no alignment now).**
Keep the field model in `sam/members/domain/` per rule-of-three (steering 38 rule 7); do NOT shape
it to the generic json-editor definition contract yet. The `json-editor.md` framework extraction
stays wholly separate and is NOT reduced by 03b.

**D4 — enum label handling: RESOLVED → IN 03b, broadened.** Not just the status-filter bug: 03b
ensures PROPER PER-LANGUAGE LABEL handling for ALL enum fields, in BOTH display AND filters.
`findings.md #2` (the Members status FILTER keys off the enum VALUE instead of the active-language
LABEL, unlike other enum filters) is the concrete instance; the rule is general (steering 38 rule 6:
an enum `value` is language-neutral/stored-key; only its `label` is per-language; resolve
`label[active locale] → en → nl → key`). 03b makes display AND filter use the resolved label
uniformly for every enum field. Absorbs `findings.md #2`.

**D5 — naming + promotion/migration parity: RESOLVED.**
  - Folder name CONFIRMED: `Members/03b - admin-driven-field-form-model`.
  - **Promotion gate (unchanged):** `test → main` stays BLOCKED until 03b lands.
  - **Data-migration PARITY (owner, explicit):** the `choices`→`options` migration already run
    against TEST (the 03a C7 backfill, incl. the scope-aware/`region` correction) MUST ALSO be run
    against PRODUCTION `governance_projection` as part of the promotion — TEST and PROD must not
    diverge. AND if 03b introduces its OWN data migration (e.g. the reference→enum-`allowed`
    collapse re-shaping membership_type rows, or the scope-dimension derivation), that migration
    (or a changed/superseding version of the 03a one) must likewise be run against BOTH TEST and
    PROD, each gated by the all-tenant zero-un-migrated / integrity scan BEFORE C6-class fail-loud
    is active there. Net: every data migration is applied to TEST and PROD identically, scan-gated,
    before `main` is considered safe.

## 6. Out of scope (CONFIRMED)
- Not the error-exposure codebase sweep (reference only).
- Not the json-editor framework extraction (align-only at most, per D3).
- Not access-control scope RESOLUTION changes beyond the authoring-trigger carve-out (D2).
- Not OAuth / session / tooling backlog items.

## 7. Next step — ANALYSIS COMPLETE, proceed design-first
D1–D5 resolved (above). Next, IN ORDER, no code until design is approved:
1. **requirements.md** — user stories in the admin-decides frame; the D1 removals + the
   `member_id`-only invariant + the enum-`allowed` model + the scope mirror (D2) + uniform enum
   label handling (D4) as explicit acceptance criteria; out-of-scope per §6.
2. **design.md** — the collapsed single enum-with-options model (reference folded in via
   `allowed`); the Change-Op toggle semantics (explicit false/null, never dropped `undefined`);
   the field→scope-dimension derivation + two-plane mirror + grant-orphaning; per-language enum
   label resolution for display AND filters; validation-at-the-seam; caller-safe errors
   (reference `error-exposure.md`). INCLUDES the D1d blast-radius read-only trace (what consumes
   the membership_type catalog / `active_only`) BEFORE committing the collapse.
3. **tasks.md** — phased, with the steering-43 CI/CD tasks AND the promotion/migration-parity
   gate (D5): prod `choices`→`options` migration + any 03b migration, each scan-gated, run against
   TEST and PROD identically before `main`.
Backlog bookkeeping once 03b lands: retire/relink `admin-driven-field-form-model-simplification.md`
and `scope-dimension-authoring-trigger.md` (absorbed), and `findings.md #2` (absorbed via D4).
