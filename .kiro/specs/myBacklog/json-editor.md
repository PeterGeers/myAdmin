# Generic definition-driven config-editor framework (platform backlog)

> Focused backlog item. Origin: `.kiro/specs/multi-tenant/s5c-members-runnable-in-spa/analysis.md`
> (F.3/F.4) — surfaced while analysing how Members authors its scope dimensions + user-defined
> fields. Status: **idea / not scheduled.** This is **platform infrastructure**, not a Members
> deliverable.

## Idea

Extract ONE generic **definition-driven typed config editor** the whole platform reuses, instead
of the current several half-overlapping mechanisms. A single pattern:

- a **definition** per field: `key`, `type` (scalar + `string[]`/`options` + **list-of-objects**
  + **map-of-field-defs**), `label_nl`/`label_en`, `description`, `depends_on` (conditional
  visibility), `module` (active-module gate);
- a **GET endpoint** serving the definitions (module-filtered);
- **one renderer component** producing typed controls (switch / select / multi-select / nested
  list / nested map) over a stored **JSON value**;
- written back via the parameter/config service.

Authors never hand-edit raw JSON; a new SAM/Flask module adds config by shipping a definition
file — no bespoke editor.

## Why

The same "typed config authoring" concept is currently implemented 3+ times (see observations).
A generic framework removes the duplication and gives every module a consistent, bilingual,
conditional, module-gated config-authoring UI.

## Observations — where a "typed config authoring" mechanism already exists today

1. **`PARAMETER_SCHEMA` — structured settings UI.**
   `backend/src/services/parameter_schema.py` declares params with metadata (`label`/`label_nl`,
   `type`, `required`, `default`, `options`, `visible_when`, namespace-level `module` gate);
   `get_schema_for_tenant(active_modules)` filters by active module; the Tenant-Admin settings UI
   renders structured controls from it. Covers `storage`, `str_branding`, `zzp_branding`, `fin`,
   `str`. **Limit:** scalar types only — no nested list/object shapes.

2. **`ParameterManagement.tsx` — generic parameter editor (raw JSON).**
   `frontend/src/components/TenantAdmin/ParameterManagement.tsx` + `services/parameterService.ts`
   list all tenant/system parameters and edit them in a modal; for a `json` value it shows a
   **raw-JSON textarea** with `JSON.parse` validation (`jsonError`). Can edit object/list params
   today, but as free-form JSON text — error-prone, not friendly.

3. **Ledger-account "parameters" — definition-driven TYPED editor (closest to the target).**
   `backend/src/config/ledger_parameters.json` (array of defs: `key`, `type` =
   `boolean|string|string[]`, `label_en`/`label_nl`, `description`, `module`, `depends_on`,
   `options`) served by `GET /api/config/ledger-parameters`
   (`backend/src/routes/config_routes.py`); `frontend/src/components/TenantAdmin/AccountModal.tsx`
   renders a typed editor from the defs — `Switch` (boolean), input/`Select` (string), multi-select
   (`string[]` + `options`), `depends_on` conditional visibility, bilingual labels — read/written
   as a per-account JSON blob. **This is the field-builder-lite pattern to generalize.**
   **Limit:** flat `key -> value` per row; no nested list-of-objects or map-of-field-definitions.

4. **Members (the NEXT consumer, from s5c) — needs the richest shape.**
   `members.scope_dimensions` (a **list of dimension objects**: key/label/values/all_wildcard/
   required_for — where `values` is exactly a `string[]`+`options` "allowed scope items" list, used
   BOTH for scope propagation AND as the member-app dropdown) and `members.field_overlay` (a **map
   of user-defined field definitions**: key/type/label/required/visible + fixed-field overrides).
   These exceed the flat ledger blob, so generalizing must add **list-of-objects** and
   **map-of-field-defs** to the type system. See the s5c analysis (F.3/F.4).

## Draft / publish (resume-across-sessions) — a first-class framework capability

Config-*definition* editing is a longer, structured task where "I'll finish tomorrow" is real.
The current parameter model has **no draft concept** — a parameter is either saved (immediately
live + projected) or not (unsaved edits lost on interruption). So an interrupted edit either loses
work OR pushes a partial definition live. The generic framework should provide:

- **Draft state** — a persisted draft copy that is **NOT projected** (the running module never
  sees it), so an admin can edit, stop, and **continue next day** without losing work and without
  a half-authored definition going live.
- **Explicit Publish** — a Publish action promotes draft → live and fires the on-change sync
  (`enqueue_sync`) once, atomically. Optionally autosave the draft as you go.
- **Save-once granularity** — the editor commits the whole config object per logical save (one
  PUT → one re-projection), never per-field/per-keystroke.

This is deliberately a **framework** capability, not a per-module one: every module's config
authoring wants it. s5c (Members) ships WITHOUT draft/publish — it uses save-once + an
unsaved-changes guard (acceptable because h-dcn config is authored once at onboarding). Draft/
publish is added when this framework is extracted. See the s5c analysis F.4 write-granularity/
draft-state note.

## Recommended sequencing (avoid blocking the pilot)

- **s5c REUSES the ledger-parameters pattern** for `members.*` now, extended only as far as Members
  needs (list-of-objects + map-of-field-defs).
- **Then extract THIS generic framework as its own platform spec** once Members is the 2nd real
  consumer (rule-of-three), and retrofit ledger + Members + `PARAMETER_SCHEMA` onto it.
- Design Members' authoring to the same definition/endpoint contract so the later extraction is
  cheap. Generic framework = platform infra (like the PreTokenGen entitlement channel), NOT a
  Members deliverable.
