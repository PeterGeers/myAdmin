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

4. **First-class, versioned, observable projection.** The tenant config projects to a **first-class,
   versioned, observable** projection (the Members pattern), not ad-hoc reads. Version **per-param**
   (not off a coarse tenant row) and expose a read-side delivered/loaded status. Ship this from day
   one — don't retrofit observability.

5. **One authoring surface.** A single typed editor/save path folds inputs into the stored shape:
   **one save → one re-projection**. Never grow two doors to the same rows (no raw param table edits
   alongside the typed editor for the module's namespace).

6. **i18n = Option (b).** Shipped labels via **resource keys** (namespace per module, e.g.
   `<module>.field.<key>`; add a language = add a resource file, translator-owned). Tenant-authored
   labels via an **inline per-language override**. An enum `value` is **language-neutral**; only its
   `label` is per-language. Fallback order: active → `en` → `nl` → key.

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
- `36-config-and-parameters.md` — how tenant/module config is stored (Flask writes) and projected
  (SAM reads) across planes; the versioned `config#...` rails rule 4 rides on.
- `37-shared-building-blocks.md` — where a shared capability lands IF/when extraction triggers.
