---
inclusion: auto
---

# Config & parameters — how tenant/module config is stored, used, and shared across planes

The standing convention for handling configuration and parameters for any purpose, usable on
the Flask plane and/or projected to the SAM plane. Follow this instead of inventing a new config
store or a tenant-name branch.

## The model in one line
**MySQL `parameters` is the single source of truth. Flask authors it. SAM reads a one-directional
projection of it. Never two writers.**

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

3. **Flask writes, SAM reads (one-directional).** Flask is the only writer. For a parameter to be
   usable on the SAM plane it is **projected** into `governance_projection` by `ProjectionSync`
   (`backend/src/services/projection_sync.py`, e.g. the `config#...` rows), and the SAM module
   reads that projection via its projection reader — a Lambda NEVER queries MySQL at request time
   (ADR 0005/0006). New SAM-consumed config = a new projected `config#<name>` row, riding the same
   rails as `config#fields` / `config#scope` / `config#views`.

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

## Related
- Connection details, the `railway-db.sh` wrapper, migrations → the **`#database` skill** (this
  file carries rules, not connection how-to; facts live in one place).
- Module entitlement + backing selection → `MODULE_REGISTRY` (`services/module_registry.py`),
  `31-backend-database-flask-mysql.md` (MySQL-plane data rules),
  `35-sam-module-architecture-sam.md` (SAM plane).
