# Members config & field-structure redesign — analysis

> **Status: ANALYSIS (Track 3).** Findings + the open design questions the user raised, grounded
> in the current code. NOT a solution — no requirements/design/tasks yet. The point is to decide
> *what the problem really is* and *where the config should live* before building anything.
>
> Grounding reads (SAM plane): `sam/members/domain/field_resolver.py` (fixed ⊕ overlay ⊕
> calculated), `calculated_fields.py`, `scope_dimensions.py`, `view_contexts.py` +
> `seed_view_contexts.py`, `lifecycle_config.py`; the authoring path spec
> `.kiro/specs/Members/s5j-members-config-authoring-path`; and the parked design concerns in
> `.kiro/specs/Members/pivot-output-actions/bugs-to-solve.md` (#6/#7/#8/#11/#12/#13 + the
> "config-home architecture fork").

## 1. Why this spec exists

The Members runtime (dynamic field structure → generic filter/column table) is rated **TOP** by
the user. The problem is NOT the result — it is the **authoring + config model** behind it:

- it is spread across the Flask tenant-admin UI as four `members.*` parameters
  (`field_overlay`, `scope_dimensions`, `view_contexts`, `mail_enabled`);
- it is projected Flask → DynamoDB (`config#fields` / `config#scope` / `config#views` /
  `config#mail`) for the SAM edge to read;
- the authoring UI is confusing (`overlay` vs `fixed`), awful to manage (groups/fields/
  attributes), and some of it (`view_contexts`) may be made redundant by the generic UI;
- there is a recurring functional symptom (bugs #6/#7/#8 — "no analytics config", enum choices
  not saving) that suggests the config path is not just ugly but **unreliable**.

This spec decides: **do we need these params in tenant-admin at all, what the field model should
be, and where it should be authored** — then (separate phase) rebuild the authoring UI.

## 2. What the pieces actually ARE today (findings, grounded in code)

### 2.1 Field origins: `fixed` ⊕ `overlay` ⊕ `calculated`
- A resolved member field (`ResolvedField`) has an **origin**: `FIXED`, `OVERLAY`, or
  `CALCULATED` (`field_resolver.py`, `calculated_fields.py`).
- **fixed** — the platform's built-in member fields (first_name, last_name, email, birth_date,
  joined_date, member_number, status, …). Defined in code, same for every tenant.
- **overlay** — tenant-authored custom fields (`members.field_overlay` param → `config#fields`
  projection). h-dcn's `iban`, `motor_type`, `region`, `newsletter_pref`, etc. are overlay.
- **calculated** — derived, read-only (display_name, age, years_member, birth_month). Code-defined
  (`calculated_fields.py`), surfaced read-only like any other field.
- **Finding (re Q2.1):** the fixed/overlay split is a *provenance* distinction (built-in vs
  tenant-added), but to the USER authoring config it reads as an arbitrary, confusing divide —
  especially since both end up as "just fields" in the generic UI. The runtime already treats
  them uniformly (`valueFor` reads either). So the split is **real in storage, incidental to the
  user**. Candidate simplification: present ONE field list with a small "built-in / custom /
  calculated" badge, not two separate concepts the user must understand.

### 2.2 Scope dimensions
- `members.scope_dimensions` (param → `config#scope`) is a LIST of dimensions; each binds a
  member FIELD (e.g. `region`) that a record is scoped by, and user GRANTS (multi-value) decide
  what a user may see (`scope_dimensions.py`). h-dcn uses one dimension (`region`).
- **Finding (re Q2.3):** the mechanism works and is genuinely needed (multi-tenant scope
  isolation, R3). The user's complaint is the **UI**, not the model. So: keep the model, redo the
  editor. (Note: the user→tenant→roles side may stay in Flask — see Q3.2 below.)

### 2.3 View contexts — the suspect
- `members.view_contexts` (param → `config#views`) is a list of `ui.tables`-shaped contexts, each
  with: `key`, bilingual `label`, `permission_roles`, **`columns`**, **`filterable_columns`**,
  **`default_sort`**, **`page_size`** (`view_contexts.py`, `seed_view_contexts.py`).
- A tenant with none gets ONE synthesized default context (empty-is-valid, R5.1).
- **Finding (re Q2.4 — the user's hypothesis is well-founded):** view_contexts predate / overlap
  the **generic filter + flexible-columns table** the user now loves. Everything a view context
  encodes (which columns, which are filterable, default sort, page size, role gating) is exactly
  what the generic UI + per-user column prefs (`session-columns` spec) + the capability gates do
  at runtime. **Strong candidate for retirement**: if the generic UI fully subsumes view_contexts,
  the `members.view_contexts` param + `config#views` projection + the Phase-2 editor can be
  removed, eliminating a whole config surface. MUST VERIFY: is anything still *reading*
  `config#views` to drive behavior the generic UI doesn't already cover (e.g. role-restricted
  column visibility)? If a residual need exists (per-role column allow-list), fold it into the
  field model (a field carries its own `permission_roles`) rather than a separate context object.

### 2.4 The four `members.*` params + the dual editing surface
- `members` namespace = `field_overlay`, `scope_dimensions`, `view_contexts` (json) +
  `mail_enabled` (boolean) — matches `parameter_schema.py`.
- **Duplication (bugs #12):** the three json params are editable in BOTH (1) a dedicated typed
  **Members tab** editor AND (2) the raw **Advanced parameters** key/value view — two doors to the
  same rows. Evidence of phase-evolution (raw params first, typed editor layered on later without
  retiring the raw surface).

## 3. The user's questions → framed as decisions

### Q1 — Do we need member-analytics params in tenant-admin at all?
- User impression: **not necessary.**
- Finding: three of the four (`field_overlay`, `scope_dimensions`, `view_contexts`) ARE the member
  config the SAM runtime consumes — they are needed *as data*; the question is **where authored**
  (Q3) and **whether view_contexts survives** (2.3). `mail_enabled` is the parked keep-vs-remove
  fork (#12). So "in tenant-admin" is really two questions: (a) is the Flask tenant-admin the right
  HOME, and (b) is each param still needed. **Decision needed per param**, not a blanket drop.

### Q2 — The runtime is TOP; the authoring is the problem
- 2.1 overlay/fixed confusing → present as one field list + provenance badge (decision).
- 2.2 field/group/attribute management UI is **awful** → the core UX rebuild (see Q4).
- 2.3 scope dimensions model fine, UI questionable → keep model, redo editor.
- 2.4 view contexts opaque, likely subsumed by the generic UI → **candidate for retirement**
  (verify residual role-column need first).
- 2.5 = Q1.

### Q3 — Where should the tenant members field structure be authored? (THE central question)
Three options (from bugs-doc "config-home fork"):
- **Option A — status quo:** Flask `parameters` = source of truth → projected to DynamoDB → SAM
  reads. Works; steering-36 compliant; but the over-complicated path (manual projection, version-
  bump trap #12/#8, dual editing surface).
- **Option B — keep Flask-authors-SAM-reads, but make the projection reliable/first-class**
  (auto-bump, no stale trap). Removes the operational pain WITHOUT changing the writer model.
  Steering-36 compliant.
- **Option C — author INSIDE the SAM plane (user's Q3.1 lean):** SAM/Members owns its config
  natively in DynamoDB; no Flask param rows, no projection for members config. One home, one plane,
  "there where it should be."
  - ⚠️ **CONTRADICTS steering 36** ("MySQL `parameters` is the single source of truth; Flask
    authors; SAM reads a one-directional projection; never two writers"). Option C is therefore
    **NOT a refactor — it is a steering-level architecture change**. Choosing it REQUIRES revisiting
    steering 36 first. This analysis flags it explicitly rather than quietly violating it.
- **Q3.2 — user→tenant→roles stays in Flask + keeps its projection.** Reasonable and consistent:
  auth/entitlements (the pretokengen path, ADR 0006) is cross-cutting and already Flask-authored;
  only the *members field/scope/view config* is a candidate to move. Keep the two concerns
  separate: identity/roles = Flask; members field structure = (A/B/C decision).
- **Q3.3 — Sender Addresses:** split into its OWN spec (user's instruction) — see
  `members/<sender-addresses>/analysis.md`. NOT part of this spec.

### Q4 — Proposed authoring UI
- A **list of functional groups**; click a group → modal of its possible attributes.
- A separate control to **show the fields in a group**; click a field → shows the attributes it
  uses + an option to add attributes. (Needs a **clear catalog of attributes per field / group**.)
- **4.1 — the only truly FIXED attribute is `member_id` (UUIDv4).** Everything else is
  configurable. (This is a strong simplifying statement: it means even "fixed" platform fields
  become defaults-you-can-adjust, not immovable — reframes 2.1 entirely.)
- **4.2 — keep storing most non-member data in the `sam-members` table as now** (no storage move).
- **Finding:** this is a **group → field → attribute** authoring model. To build it we need the
  one thing the doc keeps asking for: a **canonical attribute catalog** (what attributes a field
  can have: key, label{nl,en}, type, enum choices, required, visible, permission_roles,
  calculated?, scope-binding?, …). That catalog does not exist as a single artifact today — it is
  implicit across `field_resolver`, `calculated_fields`, enum validation, and the overlay schema.
  **Producing that catalog is a prerequisite** for both the redesign and the new UI.

## 4. Key tensions / risks to resolve before design
1. **Steering 36 vs Q3.1 (Option C).** The user leans to authoring in SAM; steering 36 forbids a
   second writer. This is the pivotal decision and gates everything else. Resolve FIRST.
2. **view_contexts retirement** depends on proving the generic UI fully covers it (esp. per-role
   column visibility). Verify before deleting.
3. **"Only member_id is fixed" (4.1)** is a big reframing — it collapses fixed/overlay into
   "configurable fields with defaults". Powerful simplification, but changes the data model and
   every consumer that assumes fixed fields are immutable. Scope carefully.
4. **The #6/#7/#8 reliability symptom** (enum choices not saving, "no config") must be reproduced
   against the CURRENT deployed stack (not the stale local Flask) to know if it is a live bug or a
   local artifact — before deciding A/B/C, since a flaky projection argues for B or C.
5. **Attribute catalog** must be authored as a first-class artifact; it is the backbone of both
   the model and the UI.

## 5. Explicitly OUT OF SCOPE of this spec
- Sender Addresses (own spec, Q3.3).
- `mail_enabled` keep-vs-remove (#12 fork) — related but decided alongside the mail feature.
- User↔tenant↔roles authoring (stays Flask per Q3.2) — referenced, not redesigned here.
- Any storage move of member data (4.2: keep `sam-members` as is).

## 6. Open decisions for the user (to drive requirements)
1. **Config home: A, B, or C?** (C requires a steering-36 revision — confirm you want that path.)
2. **Retire `view_contexts`?** (pending the "does the generic UI fully cover it" check.)
3. **Adopt "only `member_id` is fixed; all else configurable" (4.1)?** (reframes the field model.)
4. **One unified field list with a provenance badge** instead of the fixed/overlay split? (Q2.1)
5. **Build the attribute catalog first** as the backbone artifact? (prerequisite either way.)