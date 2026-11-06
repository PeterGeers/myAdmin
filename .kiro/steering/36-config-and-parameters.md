---
inclusion: auto
---

# Config & parameters — how tenant/module config is stored, used, and shared across planes

The standing convention for handling configuration and parameters for any purpose, usable on
the Flask plane and/or projected to the SAM plane. Follow this instead of inventing a new config
store or a tenant-name branch.

## The model in one line
**MySQL `parameters` is the single source of truth for Flask-authored config. Flask authors it.
SAM reads a one-directional projection of it. Never two writers *for that config*.**

> **Carve-out — SAM-owned config is authored and owned by SAM, not projected from Flask.** The
> Flask-writes/SAM-reads model above governs *Flask-authored* config only. A class of config is
> **SAM-owned**: SAM is the author and owner, it writes its own values directly on the governance
> projection table via the Change-Op write path, and there is **no Flask writer and no Flask→SAM
> projection** for it. The canonical case is **page look-and-feel (presentation)** — see
> [SAM-owned config authoring](#sam-owned-config-authoring-look-and-feel-presentation) below. Do not
> force SAM-owned config back through the Flask→projection rails; the one-directional projection
> interface proved **too weak to depend on** for config SAM must author itself (Members 15,
> `sam-page-look-and-feel`).

## The rules

1. **One store, scoped.** All config lives in the `parameters` table, resolved
   user → role → tenant → system → code-default via `ParameterService`
   (`backend/src/services/parameter_service.py`). Define every parameter in
   `parameter_schema.py` (`type`, `default`, `required`, `options`, `visible_when`). Do NOT add a
   parallel config store.

2. **Data vs. strategy.** Most config is just **data** (currencies, prefixes, field configs,
   thresholds) — read it and use it. When a config value must **select which code runs**, give it
   an `options` list and dispatch on the value through a small resolver. The canonical example is
   `services/storage_resolver.py` (`storage.invoice_provider` → a storage handler, with a safe
   default). **Config chooses; code runs.** Reuse/extend that resolver shape; never grow an
   `if tenant == ...` or a per-tenant code branch (that anti-pattern is currently ABSENT on the
   Flask plane — keep it that way).

3. **Flask writes, SAM reads (one-directional) — for FLASK-AUTHORED config.** For config Flask
   authors, Flask is the only writer. For such a parameter to be usable on the SAM plane it is
   **projected** into `governance_projection` by `ProjectionSync`
   (`backend/src/services/projection_sync.py`, e.g. the `config#...` rows), and the SAM module
   reads that projection via its projection reader — a Lambda NEVER queries MySQL at request time
   (ADR 0005/0006). New SAM-consumed *Flask-authored* config = a new projected `config#<name>` row,
   riding the same rails as `config#scope` / `config#views`.
   **Exception — SAM-owned config:** when SAM is the author/owner (page look-and-feel; see the
   [carve-out section](#sam-owned-config-authoring-look-and-feel-presentation)), SAM writes its own
   values directly via the Change-Op write path and there is **no Flask writer and no projection**
   for it. `config#fields` is a mixed row: its `fields` / `overrides` slices follow the projection
   model, while its `look_and_feel` slice is SAM-authored (same row, different owner per slice).

4. **Validate at the seam.** Reject invalid config on save, before it is stored/projected — the
   `members.*` params do this via `services/members_config_validation.py` (fail-fast, surfaced as
   a 400). A bad value must never reach the projection.

5. **No shared code across planes — guard shared vocabularies with a test.** `backend/src` and
   `sam/` are separately packaged and MUST NOT import each other. When both planes must agree on a
   vocabulary (e.g. the allowed strategy names in a param's `options` vs the keys a SAM registry
   accepts), keep one source and enforce agreement with a test — mirroring how
   `members_config_validation` keeps its field-key set honest against the SAM `fixed_fields`.

## Tenant-configurable BEHAVIOR (not just data) — selection style
When behavior differs per tenant, choose the selection mechanism in this order:
- **(preferred) config-value selects a registered generic strategy** — like `storage_resolver`.
  The tenant authors a param whose value names a strategy; a resolver maps it to a registered
  generic handler with a safe default. No tenant literal.
- **(only for genuinely bespoke logic)** a tenant-keyed hook registry with safe generic defaults —
  the SAM `TenantHookRegistry` / `HookName` pattern (`sam/members/domain/tenant_hooks.py`), the
  core never branching on the tenant (Property 5).
- **(never)** an `if administration == "<tenant>"` / hardcoded-tenant-name branch.
Data-only differences stay in `ParameterService` / `FieldConfigMixin` / `FUNCTION_REGISTRY`.

## SAM-owned config authoring — look-and-feel (presentation)

**Page look-and-feel (presentation) is SAM-owned config: SAM authors it, SAM owns it, and SAM
renders it.** It does NOT ride the Flask landing plane, is NOT authored in MySQL `parameters`, and
is NOT projected Flask→SAM. This section is the standing convention for this config class; follow it
instead of adding a `members.*` / landing-page parameter or a projection row.

### The three-layer model

Look-and-feel is produced by three layers with a strict **one-directional** data flow — authoring
values → generator → render. No layer reads backward.

- **Layer 1 — stored VALUES (SAM-authored).** The attribute values (NOT generated CSS) live in a
  distinct named **`look_and_feel` slice** on the SAM-owned `config#fields` row (the tenant's member
  field-config row) on the governance projection table. It is a separate presentation slice, not a
  member field attribute and not mixed into `fields` / `overrides`. Authored **values-only** via a
  single version-conditional **Change-Op** through the Members SAM edge
  (`MembersConfigWriteRepository.apply_ops`); `config#fields` is already in the closed writable set
  `_WRITABLE_CONFIG_IDS`, so no guard widening. The seven supported attributes are `color_primary`,
  `color_accent`, `font_heading`, `font_body`, `base_spacing`, `border_radius_global`,
  `shadow_style`. A write is authored by **domain identity** (which page, which attribute, new
  value) — never a whole record, never generated CSS.
- **Layer 2 — the SAM-owned CSS generator (`Styling_Logic`).** A pure, deterministic,
  **page-type-agnostic** function (`render_page_styles(values) -> PageStyles` in
  `sam/shared/page_styles/`) that turns the stored values into CSS. It reads only the supplied
  values mapping and holds **no** page-specific state: identical values → identical output; the same
  values produce the same styling regardless of page type. Absent attribute → SAM-owned default;
  unsupported attribute → rejected (no styling). This is the SAM-owned source of truth — there is
  **no** Flask `landing_page_styles` module and **no** build-time vendored copy in the layer.
- **Layer 3 — publish wiring (render).** At publish time `ApplicationPublishService.publish`
  resolves the Layer-1 values for the verified tenant, runs Layer 2, and passes
  `branding=<generated styles>` into `render_application_form_page`, baking the CSS into the
  published artifact. If Layer 2 fails, publish does not write the artifact and the previously
  published page is left intact.

The admin live preview is a second Layer-2/3 implementation (React/Chakra, in-browser) kept in
parity with the Python output by a shared fixture — same values, same appearance, two
implementations by design, not one shared renderer.

### Rules for SAM-owned look-and-feel config

1. **SAM is the author and owner.** SAM writes the values directly via the Change-Op path; there is
   no Flask writer and no Flask→SAM projection for this config (the carve-out to rule 3 above).
2. **Values-only at Layer 1; CSS is generated at publish.** Never store generated CSS — it goes
   stale when defaults or the generator change. Store only the attribute values.
3. **The generator is page-type-agnostic.** Page type lives in the *caller* (Layer 3), never in
   Layer 2. The pattern generalizes as "each page type stores its look-and-feel as a `look_and_feel`
   slice on its OWN existing SAM-owned record" — today only the application form (`config#fields`)
   is wired; landing pages reuse the flow only WHEN they become SAM-owned (no generic `Page` entity
   until a second real consumer, steering 37 rule-of-three).
4. **Tenant isolation.** Values are scoped to the verified `tenant_id` (`LeadingKeys` isolation);
   authoring routes resolve the tenant from the verified identity, never from the request body, and
   are `members:admin`-gated.

### Operational note — legacy `config#fields` rows have no `look_and_feel` parent map

New-tenant seeding adds the `look_and_feel` parent map to the `config#fields` skeleton, so a
single-attribute `SET ["look_and_feel", attr] = v` Change-Op has a map to write into. **Pre-existing
(legacy) `config#fields` rows predate that seed and have NO `look_and_feel` parent map.** A
single-attribute `SET look_and_feel.#attr = :v` against such a row fails — DynamoDB cannot set a
nested attribute when the parent map is absent. So **the FIRST authoring write on a legacy tenant
must be a WHOLE-SLICE set/copy** (`SET look_and_feel = :snapshot`, i.e. the copy op shape), which
creates the parent map; subsequent single-attribute SETs then work normally. Treat "first write on a
legacy row" as whole-slice, not single-attribute.

## Related
- Connection details, the `railway-db.sh` wrapper, migrations → the **`#database` skill** (this
  file carries rules, not connection how-to; facts live in one place).
- Module entitlement + backing selection → `MODULE_REGISTRY` (`services/module_registry.py`),
  `31-backend-database-flask-mysql.md` (MySQL-plane data rules),
  `35-sam-module-architecture-sam.md` (SAM plane).
- SAM-owned look-and-feel config (the three-layer model, the `look_and_feel` slice, the SAM-owned
  generator, publish wiring) → the Members 15 `sam-page-look-and-feel` spec; the SAM Change-Op write
  contract and resolved-view read rules → `39-sam-data-access-sam.md`; the one-directional
  projection ADR this carve-out qualifies → `docs/decisions/0005-two-pool-identity-mysql-system-of-record-one-directional-projection.md`.
