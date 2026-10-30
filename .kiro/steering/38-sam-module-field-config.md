---
inclusion: auto
---

# SAM module field config — the proven tenant-configurable field pattern

Recommended practice for a SAM module that needs a **tenant-configurable field model**
(which fields exist, how they group/order, their per-field attributes, their labels). Members
proved this pattern; Events/Webshop should follow it instead of re-deriving. This file is THIN
on purpose — it points at the reference impl and the spec for detail, it does not restate them.

> **Scope: the SAM plane** (`sam/<module>/domain/`). The Flask-plane config store/projection
> rules are in `36-config-and-parameters.md` — this file is the field-model shape that rides on
> top of them.

## The rules

1. **Catalog-first.** Model a module's fields as ONE canonical attribute catalog **derived** from
   the code registries (the fixed + calculated field definitions) — never a second, hand-maintained
   source of truth. The derived catalog is a VIEW over the registries; **guard it with a drift test**
   (catalog inventory ⇄ registries) so the two can't silently diverge. (This kills the
   hand-transcription drift class.)

2. **group → field → attribute, with ordering derived.** The model is first-class functional (display)
   **groups** (`key`, `label`, `order`) + a base set, **fields**, and **per-field attributes**. Display
   position is **derived by the consumer** as `(group.order, field.order, key)` — do NOT add a new
   position field to the response.

3. **No view/analytics param objects in the field model.** Columns / sort / filter / pagination are
   runtime behaviours of the generic table + per-user prefs; analytics are calculated fields + pivot
   filters. Keep view-contexts and analytics as **separate tenant config**, never baked into the
   catalog shape as fields.

4. **First-class, versioned, observable config rows.** The tenant config lives in **first-class,
   versioned, observable** `config#*` rows (the Members pattern), not ad-hoc reads. Version
   **per-row** (not off a coarse tenant row) and expose a read-side delivered/loaded status. Ship
   this from day one — don't retrofit observability.

   > **Authoring is SAM-owned (Members, spec-02).** A module's `config#*` rows are authored
   > DIRECTLY by the module via its own typed write path (`PUT /<module>/config/*`, Change-Op for
   > the field config), NOT projected from a MySQL source. In Members, `ProjectionSync` emits ZERO
   > `config#*` rows — only identity GRANTS (`role#`/`scopegrant#`) still project from MySQL. A new
   > module authors its config on the SAM plane; do not reintroduce a Flask-writes-config /
   > SAM-reads projection path for module config.

5. **One authoring surface, written by Change-Op.** A single typed editor/save path folds inputs
   into the stored shape: **one save → one re-projection**. Never grow two doors to the same rows (no
   raw param table edits alongside the typed editor for the module's namespace). The save path writes
   by **domain identity via a Change-Op** (single path `update_item`), never a whole-record replace —
   the authoring client sends intent by identity and the server owns physical placement. The
   contract (Change-Op / no whole-record replace / Merge_Target = Resolved_Record / version-conditional)
   is owned by `39-backend-data-access-sam-dynamodb.md` and ADR 0009; this rule only points at it.

6. **i18n = labels are plain per-language values stored in config; shipped resource files are a
   SEED/DEFAULT only.** A field's / group's / enum-option's label is a plain inline per-language
   value (`{nl, en, …}`) stored ON the config (the tenant overlay → projection) and resolved from
   there at RUNTIME. A tenant edits a label in the config editor and it takes effect on the next
   re-projection — **no app rebuild, no new deploy**. Shipped i18n resource files
   (`locales/*/<ns>.json`) are ONLY a one-time SEED/DEFAULT for the platform's own base fields (so a
   fresh tenant sees sensible labels without typing); they are **NOT** the runtime resolution source
   for a tenant-editable label (a tenant can't write the build-time bundle, and it is global, not
   per-tenant). An enum `value` is **language-neutral** (never translated — it is the stored key);
   only its `label` is per-language. Resolve order: `stored label[active locale] → en → nl → key`
   (never blank).

   > **Guardrail — why NOT resource-key resolution for tenant labels (reversed 2026, Members
   > drill-down remediation).** The earlier "Option (b): shipped labels via resource keys" model was
   > unsustainable for a tenant-editable label: resource files are baked into the SPA build and are
   > global, so a tenant's rename would require a code change + redeploy and could not be per-tenant.
   > Tenant-authorable labels therefore live in config and resolve at runtime; resource files are
   > seed-only. A new module (Events/Webshop) MUST follow this — do not reintroduce resource-key
   > resolution as the authority for tenant labels.

7. **Extraction boundary — rule of three.** Keep the catalog in the module's own `domain/`
   (e.g. `sam/members/domain/`). Do NOT extract a `sam/shared` field-config library until a **THIRD**
   module needs it. Shape the model **module-neutrally now** (no module-only concepts in the dataclass
   shape — the actual field data stays module-specific), extract later. Until then a new module COPIES
   the Members shape, guided by this file. (Rule of three, per `35`/`37`.)

## Reference implementation

Members is the reference — read it, don't re-invent:
- `sam/members/domain/attribute_catalog.py` — the derived catalog (attribute vocabulary + computed
  inventory + group set + label rule) and its import-time drift guard.
- `sam/members/domain/field_resolver.py` — base registry ⊕ per-tenant overlay merge + ordering.
- `.kiro/specs/Members/Parameter redesign/phase-1-catalog-backbone/` — the design (esp. §10 R9) and
  the proven-lessons rationale behind each rule above.

## Related

- `35-sam-module-architecture-sam.md` — the SAM layering (domain owns field resolution) + the
  rule-of-three/CODE-shared-DATA-per-module boundary this file applies to the field model.
- `39-backend-data-access-sam-dynamodb.md` — the resolved-view READ rule **and** the Change-Op WRITE
  contract (no whole-record replace; Merge_Target = Resolved_Record; version-conditional) that the
  "one authoring surface" (rule 5) save path follows. ADR 0009 is the decision record; the first and
  hardest application is `config#fields` (spec `03 - config-fields-foolproof-crud`). This file does
  not restate that contract — it points at it.
- `36-config-and-parameters.md` — how tenant/module config is stored and projected across planes; the
  versioned `config#...` rails rule 4 rides on. (Members config authoring is **SAM-owned** — the
  `config#*` rows are written via `PUT /members/config/{configId}`; the earlier Flask
  writes-config#* / SAM-reads projection path is retired for authoring and must not be revived.)
- `37-shared-building-blocks.md` — where a shared capability lands IF/when extraction triggers.
