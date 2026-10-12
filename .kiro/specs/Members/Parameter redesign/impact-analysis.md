# Members config redesign — impact analysis (current → greenfield)

> **Status: IMPACT ANALYSIS.** Grounded in the current SAM + Flask + SPA code (file/function level).
> Companion to `analysis.md` (findings) and `recommendation.md` (greenfield target). This doc answers:
> **what can be deleted, what is unused, what is a pure UI change, which SAM functions implement
> concepts the greenfield wouldn't have, and the migration risks.**
>
> Grounding: SAM `sam/members/domain/{field_resolver,calculated_fields,scope_dimensions,view_contexts,
> seed_view_contexts,lifecycle_config}.py`, `sam/members/domain/_membership_writes.py`,
> `sam/members/handler/app.py`, `sam/members/repository/projection_config_reader.py`; Flask
> `backend/src/services/{parameter_schema,members_config_validation,_projection_config_builders,
> projection_sync}.py`; SPA `frontend/src/pages/MembersPage.tsx` +
> `frontend/src/components/TenantAdmin/MembersConfig/*`.

## 0. Three corrections the code forced on the analysis/recommendation

Before the impact table, three grounded facts that refine the earlier docs:

1. **No `valueFor` on `ResolvedField`.** Field *values* are computed by
   `calculated_fields.compute_calculated_fields` / `CalculatedField.evaluate`, not on the resolved
   field. (`analysis.md` 2.1 mentioned `valueFor` — it doesn't exist.)
2. **"Analytics" is already NOT a param.** The analytics slice (`AnalyticsConfig`, `AnalyticsRole`,
   `JubileeRule`, `AddressMapping`) **rides on the same `config#fields` row** (ODI-2), not a
   separate `members.*` param. So the greenfield "no analytics param surface" (recommendation §2.6)
   is partly already true — the work is to fold analytics *fully* into field attributes/calculated
   fields, not to delete a standalone param.
3. **The version-bump trap is worse than "manual bump".** `_scope_config_version` keys off the
   **tenant row's** version/updated_at, not a per-param revision. A `members.*` edit can therefore
   be **silently skipped** by the conditional put — the edit never reaches DynamoDB. This is a
   functional defect, not just friction (explains the #6/#7/#8 "config not saving" symptom).

   > **Field evidence + interim workaround (folded in from the backlog "Projection version gap"
   > item, 2026-09-30 / moved here 2026-10-12).** First hit during the s5m h-dcn SAM migration:
   > after seeding `members.field_overlay`, `sync_administration` reported `written=0 skipped=15`
   > and the app kept serving the OLD config until the tenant row was manually bumped
   > (`UPDATE tenants SET updated_at = CURRENT_TIMESTAMP WHERE administration='h-dcn'`) and the
   > sync re-run (`written=4`). **Interim mitigation now committed:**
   > `scripts/aws/project-config-to-prod.py --tenant <t> --apply` does seed → `tenants.updated_at`
   > bump → AWS re-strip + STS account guard → `ProjectionSync.sync_administration` → read-back
   > verify, and **refuses to report success on `written==0`** (the signal the version bump did not
   > take; dry-run is the default). This removes the manual-dance footgun but is NOT the fix — the
   > proper fix is the per-param revision in Phase 0 step 2 below. **Proper-fix options** (from the
   > backlog item): (a) `ParameterService.set_param` stamps/increments a per-namespace revision the
   > builders read; (b) the param-change route enqueues the sync AND the builders version off the
   > param's own `updated_at` rather than the tenant row's. **Acceptance:** a param change ALONE
   > yields `written>0` (add that test). NOTE: the committed runner also depends on the
   > `load_dotenv()`-clobbers-`AWS_PROFILE` fix, now promoted to its own bugfix
   > (`.kiro/specs/BUGS/20261012 load_dotenv clobbers AWS_PROFILE/analysis.md`) and designated the
   > **prerequisite gate before this Phase 0**. The runner carries a `_restrip_aws_env()` workaround
   > to survive that bug today (so Phase 0 is not hard-blocked), but the bugfix should land first so
   > these projection runs can trust `AWS_PROFILE` directly and the crutch can be retired. That infra
   > bug stays a separate deliverable, not part of this spec.

## 1. DELETE — surfaces/code the greenfield removes outright

### 1.1 `view_contexts` — safe to delete server-side (pure UI config)
**Finding: nothing server-side acts on view-context contents.** The only runtime consumer is
`_membership_writes.get_field_config` (~L996), which calls
`_view_contexts_provider.get_view_contexts(tenant_id)` and serializes each via
`_serialize_view_context` into the `/members/field-config` response. The code comment is explicit:
"the frontend renders these; the module enforces nothing off them." All actual use of `columns` /
`filterable_columns` / `default_sort` / `page_size` / `permission_roles` is **client-side** in
`MembersPage.tsx` (`isContextSelectable`, `contextColumns`, `filterableSet`, table toolkit). There
is **no server-side per-role column-visibility logic** — row scope is enforced entirely separately
via scope grants (§3). So the "verify residual role-column need" caveat in `analysis.md` 2.3 is
**resolved: there is none.** The real residual is **pagination/`page_size`** only.

Deletable once the SPA stops consuming view contexts:
- SAM domain: `view_contexts.py`, `seed_view_contexts.py` (entire files), `get_view_contexts` in
  `projection_config_reader.py`, the provider wiring, and `_serialize_view_context` + the
  `view_contexts` array in `get_field_config`.
- Flask: the `view_contexts` param in `parameter_schema.py`, `validate_view_contexts` in
  `members_config_validation.py`, `build_config_views_row` in `_projection_config_builders.py`,
  the `config#views` projection in `projection_sync.py`.
- SPA: the view-context sub-editor in `MembersConfig/` and the context machinery in `MembersPage.tsx`.
- Tests retired/rewritten: `test_seed_view_contexts.py`, `MembersPage.viewContexts.test.tsx`, the
  view-context parts of `test_config_roundtrip_props.py` and the MembersConfig suite.
- **Keep as a field/tenant default:** `page_size`/pagination (recommendation §4).

### 1.2 Legacy `overrides` key — dead on the authoring side
Authoring/validation uses `fixed_overrides`; the projection attribute and `TenantOverlay.overrides`
use `overrides`; `build_config_fields_row` and `get_overlay` accept **both** for back-compat. The
legacy `overrides` read path is dead weight once a one-time migration rewrites stored rows to
`fixed_overrides`. Delete the dual-accept branches afterwards.

### 1.3 `SAMPLE_SCOPE_CONFIG`
Fixture-only (North/South/East/West), never a runtime fallback (Decision D16). Lives in
`scope_dimensions.py` but belongs in tests. Move or delete.

## 2. UNUSED / DRIFT — fix regardless of the redesign

- **`CALCULATED_FIELD_KEYS` drift (latent bug).** `members_config_validation.py` hand-transcribes
  only 5 calculated keys (display_name, age, birthday, years_member, application_year) but
  `calculated_fields.CALCULATED_FIELDS` defines **9** (missing birth_day, birth_month, birth_year,
  birth_quarter). View-context validation would wrongly **reject** columns referencing those real
  calculated keys. The greenfield single-catalog model removes this hand-transcription class of bug
  entirely (one source, not two packaged-separately copies).
- **Version-bump trap** (§0.3) — functional dead-weight that must be fixed in any option that keeps
  param-edit propagation (A/B).
- **No read-side version/staleness surface** — `MembersProjectionReader` never exposes the row
  `version`; no delivered/loaded indicator exists. (recommendation §2.7 / `analysis.md` risk #6.)

## 3. KEEP THE MODEL, CHANGE ONLY THE UI/AUTHORING

- **Scope dimensions — model stays, surface changes.** `config#scope` →
  `MembersProjectionReader.get_scope_config` → `ScopeConfig`; row filtering resolved in
  `handler/app.py` (`resolve_scope_access_for_config`, `_resolve_scope_access_for_admin`,
  `_gating_dimension_key`) combining enabled dimensions with projected `scopegrant#<email>#<dim>`
  rows → `allowed_scopes`. **Scope is ALREADY field-bound**: each `ScopeDimension.field` names the
  member field (h-dcn `region`), and its `values` feed that field's enum via `_scope_vocab` (D1a).
  Greenfield impact: this is **mostly a UI change** — expose scope-binding as a **field attribute**
  (recommendation §2.5) instead of a standalone `scope_dimensions` editor. The resolution code in
  `handler/app.py` can stay; only the authoring representation and the `scope_dimensions` param
  change. **Low code-churn, high UX win.**
- **Calculated fields — keep as-is.** The 9-field registry (`display_name`, `age`, `birthday`,
  `birth_day/month/year/quarter`, `years_member`, `application_year`) is clean, code-defined,
  import-time-guarded, never stored. Greenfield keeps it; it is the mechanism that absorbs
  "analytics params" like jubilee years (recommendation §2.6). No deletion.
- **`lifecycle_config.py`** — out of the four `members.*` params (module-declared, surfaced as
  `lifecycle` in field-config). Not in scope; leave untouched.

## 4. SAM functions implementing concepts the greenfield wouldn't have

| SAM symbol (file) | Concept today | Greenfield |
|---|---|---|
| `ViewContext`, `default_view_context`, `ViewContextsProvider`, `StaticViewContextsProvider` (`view_contexts.py`) | stored per-view column/sort/page config | **gone** (generic UI; pagination is a default) |
| `SEED_VIEW_CONTEXTS`, `seed_view_contexts_list`, `build_seed_view_contexts` (`seed_view_contexts.py`) | seed/placeholder view data | **gone** |
| `get_view_contexts` + `_serialize_view_context` (`projection_config_reader.py`, `_membership_writes.py`) | ferry view config to SPA | **gone** |
| dual `overrides`/`fixed_overrides` accept (`get_overlay`, `build_config_fields_row`) | back-compat alias | **gone** (one key) |
| `_as_variable_field` fixed/overlay provenance branching (`field_resolver.py`) | fixed vs overlay distinction | **collapses** to one field list + provenance badge; only `member_id` immovable (4.1) |
| `_scope_config_version` tenant-row versioning (`projection_sync.py`) | coarse version proxy | **replaced** by per-config auto-version + delivered/loaded status |

**Not a deletion but a reshaping:** `FieldResolver.resolve` keeps the merge+sort+project pipeline,
but the `_apply_override` / fixed-vs-overlay branch simplifies once "only `member_id` is fixed".
`AnalyticsConfig`/`AnalyticsRole`/`JubileeRule`/`AddressMapping` fold into field
attributes/calculated fields rather than a distinct analytics object on `config#fields`.

## 5. Pure UI changes (no/low backend impact)

- One unified field list + provenance badge instead of the overlay/fixed two-section split
  (`MembersConfigEditor.tsx` sub-editors 1/2/5 all already edit the single `field_overlay` object —
  so this is largely a **frontend re-presentation**, backend unchanged).
- The group → field → attribute authoring UX (recommendation §2.3/§2.2).
- Removing the "unresolved columns" opaque block (dies with view_contexts, §1.1).
- Retiring the **dual editing surface** (typed Members tab + raw Advanced params) — keep the typed
  `MembersConfig` editor, drop the raw members-param rows from the generic parameter editor. The
  raw surface is `frontend/src/components/TenantAdmin/ParameterManagement.tsx`, mounted via
  `AdvancedTab.tsx` (SysAdmin-only tab in `TenantAdminDashboard.tsx`); it is the
  parameter_schema-driven key/value editor that currently exposes the `members.*` rows alongside
  the typed editor. Scope the change to **excluding the `members.*` namespace** from
  `ParameterManagement` rather than removing the component (it still serves every other namespace).

## 6. Migration risks / ordering

1. **view_contexts deletion is gated on the SPA**, not the server. Sequence: move pagination to a
   default → strip SPA view-context consumption → remove server serialization → drop param +
   projection + domain files. Reverse order breaks the field-config contract.
2. **Fix `CALCULATED_FIELD_KEYS` drift before** tightening any validation, or valid configs break.
3. **The version trap must be fixed before trusting param-edit propagation** (A/B). Otherwise the
   redesign inherits the "edit silently not saved" defect.
4. **`fixed_overrides` migration** needs a one-time rewrite of stored `overrides` rows before the
   dual-accept branches are removed.
5. **Config-home (A/B/C) is still the gate** (`analysis.md` Q3). Everything above is writer-agnostic
   except the version/projection fixes, which are only needed if Flask stays the writer (A/B). If C
   (SAM-native authoring) is chosen, the projection builders + `projection_sync` config rows + the
   version machinery are **deleted wholesale** instead of fixed — but that requires a steering-36
   revision first.

## 7. Test blast radius (what to update on deletion)

- **Delete/rewrite:** `test_seed_view_contexts.py`, view-context assertions in
  `test_config_roundtrip_props.py`, `MembersPage.viewContexts.test.tsx`, view-context parts of the
  `MembersConfig/__tests__` suite.
- **Update:** `test_projection_sync.py` (drop `build_config_views_row`; add version/delivered-status
  assertions), `test_parameter_schema.py` (members namespace minus `view_contexts`),
  `members_config_validation` tests (drop view-context validator; fix calculated-key set),
  `test_field_resolver.py` (provenance collapse if 4.1 adopted).
- **Keep:** `test_calculated_fields.py`, `test_scope_dimensions.py`, `test_scope_access.py`,
  `test_members_projection_reader.py` (minus views), `test_empty_is_valid_props.py`,
  `test_members_resolved_field_surface.py`.

## 8. Summary — one-line dispositions

- **Delete:** `view_contexts` + `seed_view_contexts` (server + param + projection + SPA), legacy
  `overrides` key, `SAMPLE_SCOPE_CONFIG`.
- **Fix now (bugs):** `CALCULATED_FIELD_KEYS` drift, version-bump trap, missing read-side status.
- **Keep model, redo UI:** scope dimensions (already field-bound), the whole field catalog.
- **Keep as-is:** calculated fields, lifecycle config.
- **Reshape:** fixed/overlay provenance → one list; analytics object → field attributes/calculated.
- **Pivotal gate unchanged:** config-home A/B/C (C deletes the projection layer but needs a
  steering-36 revision).

## 9. Effort — logical steps and relative sizing

Sizing is **relative** (S / M / L), not a time commitment — it reflects code churn + blast radius +
coordination across the three planes (SAM, Flask, SPA), not calendar estimates. Steps are ordered so
each lands safely on its own; the two "fix now" bugs are deliberately first because they de-risk
everything after them and deliver value even if the redesign stalls.

**Phase 0 — de-risk / quick wins (do first, independent of A/B/C)**
1. **Fix `CALCULATED_FIELD_KEYS` drift** (S). Single Flask file (`members_config_validation.py`);
   add the 4 missing calculated keys so valid configs stop being rejected. Pure bug fix.
2. **Fix the version-bump trap** (M). `projection_sync.py` / `_scope_config_version` — thread a
   per-param revision so edits always project. Touches the write path + `test_projection_sync.py`.
   Needed for any Flask-writer option (A/B). High value: directly addresses the #6/#7/#8 symptom.
3. **Add read-side delivered/loaded status** (M). Expose the row `version`/last-synced through
   `MembersProjectionReader` and surface it in the editor. Makes stale/failed projection visible.

**Phase 1 — catalog backbone (prerequisite for the UX)**
4. **Author the canonical attribute catalog** (M). New first-class artifact derived from the
   already-existing registries (`fixed_fields`, `calculated_fields`, overlay schema). Mostly
   consolidation, not new logic. Resolve the **i18n label** question here.
5. **Settle functional-group identity + ordering** (S–M). Decide first-class object vs field
   attribute (analysis Q4.3); encode display order. Shapes the catalog, so do it alongside step 4.

**Phase 2 — delete the redundant surface**
6. **Retire `view_contexts`** (M, but gated on the SPA). Order matters: (a) move `page_size` to a
   field/tenant default, (b) strip SPA consumption in `MembersPage.tsx`, (c) remove server
   serialization (`_serialize_view_context`, the `view_contexts` array), (d) delete the param +
   `build_config_views_row` + `config#views` projection + `view_contexts.py` / `seed_view_contexts.py`.
   Churn is spread but each sub-step is mechanical. Low *risk* (no server behaviour depends on it),
   moderate *volume*.
7. **Clean dead code** (S). Delete legacy `overrides` dual-accept (after a one-time row migration to
   `fixed_overrides`) and move `SAMPLE_SCOPE_CONFIG` into tests.

**Phase 3 — reshape the model + UI**
8. **Collapse fixed/overlay to one list + provenance badge** (M). Mostly SPA re-presentation
   (`MembersConfigEditor.tsx`) since the sub-editors already write one `field_overlay` object; the
   SAM `_apply_override` branch simplifies if "only `member_id` is fixed" (4.1) is adopted — that
   adoption is the one part that touches many consumers (L if taken literally; scope carefully).
9. **Fold scope-binding into a field attribute** (M). The resolution code in `handler/app.py` stays;
   change the authoring representation + retire the standalone `scope_dimensions` editor.
10. **Fold analytics fully into field attributes / calculated fields** (M). Analytics already rides
    on `config#fields`; the work is representing jubilee-years-type needs as calculated fields and
    the alias as a field attribute, then removing the separate analytics object.
11. **Rebuild the group → field → attribute authoring UI** (L). The largest single piece —
    net-new SPA on top of the settled catalog. This is where most visible value lands.

**Phase 4 — config-home decision (the gate)** — ✅ **DECIDED = Option B (user, 2026-10-12).**
12. **Option B (CHOSEN):** steps 2–3 already made the projection first-class — effectively done
    (M, already counted); no additional config-home work and **steering 36 is kept unchanged**.
    (Option A status-quo and Option C SAM-native are not pursued. Option C would have deleted the
    projection builders + `projection_sync` config rows + version machinery and **required a
    steering-36 revision first** — explicitly rejected.)

**Rough shape:** Phase 0 is small and high-leverage. Phases 1–2 are medium and mostly mechanical.
The genuine investment is Phase 3 step 11 (the new UI) and — only if chosen — Option C. Nothing here
is a storage migration of member data (explicitly out of scope, 4.2), which keeps the blast radius
bounded.

## 10. Conclusion — does this add value?

**Yes — but the value is concentrated and separable, so it should be sequenced, not done as one big
bang.**

- **Clear, near-unconditional value (do regardless of the redesign):** the Phase 0 fixes. The
  `CALCULATED_FIELD_KEYS` drift and the version-bump trap are **real bugs** — the latter is the most
  likely root of the "config won't save" (#6/#7/#8) pain that triggered this whole spec. Fixing them
  plus adding delivered/loaded visibility removes the reliability problem for small effort. This
  alone justifies opening the work.

- **Strong value, moderate effort:** retiring `view_contexts` (removes an entire confusing,
  server-inert config surface and the opaque "unresolved columns" UX) and collapsing the
  fixed/overlay split. These make the thing the user already rates TOP *easier to author* without
  risking the runtime, because no server behaviour depends on what's being removed.

- **Highest value, highest effort:** the group → field → attribute catalog + new authoring UI
  (Phase 1 + Phase 3 step 11). This is the actual "redesign" and where the user's core complaint
  (authoring is awful) is resolved. It's worth doing, but it depends on the catalog existing first,
  so it can't be short-cut.

- **Proceed-with-caution:** "only `member_id` is fixed" (4.1) and **Option C**. Both are powerful
  simplifications but have outsized blast radius — 4.1 touches every consumer that assumes fixed
  fields are immutable; C is a steering-level architecture change, not a refactor. Neither is
  required to capture most of the value above. Treat them as separate, explicitly-decided bets.

**Bottom line:** the change adds real value and is low-regret **if staged** — ship the bug fixes and
the view_contexts retirement early (fast reliability + simplicity gains), build the catalog + UI as
the main investment, and defer the two high-blast-radius bets (4.1, Option C) to explicit decisions.
The one thing to avoid is treating it as a single monolithic rewrite or letting the unresolved
config-home question (A/B/C) block the Phase 0–2 wins, which are **writer-agnostic**.

## 11. Starting the next modules (Webshop, Events) — best approach from lessons learned

Steering 35 already names **Events and Webshop as the next SAM modules after Members**, and the
Members migration is the pilot meant to prove the pattern. So these two don't start from scratch —
they start from the Members lessons captured in this spec. The best approach is to **inherit what
Members proved right and pre-empt the config/authoring mistakes this redesign exists to fix.**

### Carry over (what Members proved right — reuse, don't reinvent)
- **The four-seam SAM layering (steering 35).** Thin handler (parse → authenticate + tenant context
  → authorize → delegate → respond); storage-agnostic domain service; repository as the ONLY
  DynamoDB touch-point with `tenant_id` PK + IAM `LeadingKeys`; React presentation-only. Both new
  modules are "write the domain service + repository; reuse the edge + tenancy."
- **The shared edge toolkit (`sam/shared`).** Verified-JWT auth, entitlement/capability checks, and
  **active-tenant resolution via `X-Tenant`** (ADR 0007) are adopted once at the edge — steering 35
  says Events/Webshop resolve tenant identically. Do not re-implement per handler.
- **Registered building blocks (steering 37).** Reach for the Table Filter Framework v2, the API
  response & error standard v1.0 (one envelope, machine `code` + i18n), and LazySelect before
  writing local variants. The generic filter/pivot table is the thing users rate TOP in Members —
  both new modules should lean on it, not grow bespoke tables.
- **Stack-per-environment + per-module tables (steering 35).** Each module owns `WEBSHOP_TABLE` /
  `EVENTS_TABLE` (fail-fast env var, never hardcoded), TEST/PROD as distinct stacks with the
  `test_` prefix, deployed via committed `samconfig.toml` + OIDC CI — never inline overrides.

### Pre-empt (the Members config pain this spec fixes — don't repeat it)
These are the concrete lessons from §0–§10 above, applied forward:
1. **Design the field/config model as a catalog from day one.** Members' pain is that the attribute
   model was implicit across code + hand-transcribed copies, and fixed/overlay was a user-facing
   split. Start Webshop (products, variants, price rules) and Events (sessions, tickets, capacity)
   with **one field list + a canonical, versioned attribute catalog** and a **provenance badge**,
   not two concepts. Only the true identity key is immovable.
2. **Make config a group → field → attribute model with explicit ordering** — the authoring UX
   Members is being rebuilt toward. Build it that way the first time.
3. **No standalone "view/column/analytics" config objects.** Columns, sort, filter, pagination are
   runtime behaviours of the generic table + per-user prefs, not stored config (the view_contexts
   lesson). Analytics needs are calculated fields + pivot filters, not a params surface.
4. **If config is projected, make the projection first-class from the start** — per-config
   auto-versioning (NOT a coarse tenant-row proxy, the version-bump trap) and a **read-side
   delivered/loaded status**. Members had to retrofit this; the new modules should ship it.
5. **One authoring surface, never two.** Members grew a typed editor on top of a raw params editor
   and never retired the raw one. Pick one surface per module from the outset.
6. **Honour steering 36 and rule 5a.** Config has ONE writer (MySQL `parameters` → one-directional
   projection → SAM reads); a module's data — including its feature/config/saved-set data — is
   persisted by its OWN repository in its OWN table, NEVER via another plane's store (the F-012
   anti-pattern). This is the single biggest "don't" — Webshop orders and Events bookings must not
   piggy-back on a Flask table to reuse it.

### Build order per module (apply the §9 phasing forward)
1. **Define the module's attribute catalog + functional groups first** (the backbone, before any
   UI) — same prerequisite Members discovered the hard way.
2. **Stand up the four seams**: handler edge (reuse `sam/shared` + ADR 0007 tenant resolution),
   domain service (the module's actual business rules — Webshop: cart/stock/payment/fulfilment
   workflow; Events: planning/budget/calendar/capacity), repository + own table, React presentation.
3. **Wire config as a first-class projection** (auto-version + delivered/loaded status) if config is
   Flask-authored — or decide the config-home question up front rather than retrofitting it.
4. **Compose from registered building blocks** (filter table, API/error standard, LazySelect); only
   extract a NEW shared block when a second consumer appears (**rule of three**, steering 35/37) —
   e.g. a shared analytics library is built only when the second module needs it, not speculatively.

### Module-specific notes
- **Webshop** ("the whole handling"): the business logic is heavier (cart, inventory, pricing,
  payment, order lifecycle, fulfilment) and belongs squarely in the **domain service**, with
  **DynamoDB enforcing data invariants** (conditional writes for stock/uniqueness, transactions for
  order+payment atomicity) — steering 35 rule 2. Order/payment integrity is the part to design
  against the DynamoDB conditional-write + transaction patterns, not application-level locking.
- **Events** (planning, budget, calendar, landing pages): mostly configuration + scheduling +
  content. The field-catalog + group model fits it naturally (event types as groups, their
  attributes as fields). **Landing pages** should reuse the existing landing-page capability
  (`infrastructure/landing-pages.tf`, the LandingPage editor) rather than a new one — a reuse, not a
  rebuild. Budget/calendar are read-heavy pivot/table use cases → lean on the generic table +
  calculated fields.

### Bottom line for the new modules
Start both modules on the **proven Members skeleton** (four seams + shared edge + building blocks +
own-table tenancy), and bake in the **five config lessons** (catalog-first, group→field→attribute,
no view/analytics param objects, first-class versioned+observable projection, single authoring
surface) that this redesign exists to retrofit into Members. The net effect: Webshop and Events get,
on day one, the authoring model Members is spending this spec to reach — turning a costly Members
retrofit into a cheap "do it right the first time" for the next two modules. **This is high-value and
low-regret** precisely because the pattern is already proven and the mistakes are already documented
here.
