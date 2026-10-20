# S5 — Generalizing "region" → a tenant-configurable scope dimension

- Status: Draft (design of record; generalizes h-dcn's region feature)
- Companions: `generic-membership-design.md`, `members-wireframe.md`,
  steering `sam-module-architecture.md` (layering), `identity.md`.
- Grounding: h-dcn's real region logic in `backend/shared/auth_utils.py`
  (`validate_permissions_with_regions`, `determine_regional_access`, `Regio_*` roles,
  `Regio_All` wildcard). This document generalizes that, it does not replace h-dcn's rules
  — those become the *body* of the generic hooks.

## The insight: "region" is three jobs bundled together

In h-dcn a "region" simultaneously does:

1. **A data attribute** — a member belongs to a region.
2. **A role scope** — a permission role (e.g. `Members_CRUD`) is meaningless without a
   region assignment; the capability is scoped to region(s) (`Regio_Noord`, `Regio_All`).
3. **A data-visibility filter** — a regional user sees only their region(s)' members;
   admin/national see all (`allowed_regions: ['all']`).

Not every club has "regions" — soccer/hockey have **teams/sections**, multi-site clubs
have **locations/branches**, some clubs have **none**. So the generic model must not
hardcode "region": it offers a **scope dimension** that a tenant configures (h-dcn →
"region"), or disables entirely.

## The general model: a within-tenant scope dimension

> `tenant_id` is the hard tenancy **isolation** boundary (repository + `LeadingKeys`).
> A **scope dimension** is a softer, **within-tenant** partition + role-scoping filter
> (domain layer). A scoped user is always still fully inside their own tenant.

### 1. Scope definition (tenant config — Rung 1)

```jsonc
scope_dimensions: [
  {
    key: "region",              // h-dcn: "region"; soccer: "team"; multi-site: "location"
    label: "Regio",
    enabled: true,              // a tenant with no sub-scoping sets enabled:false
    multi_valued: false,        // can ONE record belong to several values? (see below)
    values: ["Noord","Zuid","Oost","West"],   // or sourced dynamically
    all_wildcard: "Regio_All",  // the "national/all" grant
    required_for: ["Members_CRUD", ...]  // capabilities that REQUIRE a scope grant
  }
]
```

- **Disabled** (`enabled:false` or no dimension) → the feature collapses to "tenant-wide":
  everyone is effectively "all", no code path differs. Clubs without sub-scoping pay nothing.
- **Designed for >1 dimension and multi-value from the start** (see "Cross-club" below):
  `scope_dimensions` is a **list**, and each has `multi_valued`. h-dcn uses a single,
  single-valued dimension; the shape does not assume that.

### 2. Record scoping (data attribute — fixed-but-optional field)

Each member record carries an optional `scope_values: { <dimension_key>: [value...] }`
(h-dcn: `{ region: ["Noord"] }`). This is a **platform-fixed** field the generic model
understands; its *values* are tenant data. Distinct from `tenant_id`.

### 3. Access resolution (the generic authz piece — generalizes `determine_regional_access`)

```
resolve_scope_access(tenant, dimension, user_roles) -> {
  full_access: bool,                 # admin/national -> all values
  allowed_scopes: [values] | ["*"],  # the set the user may see/act on
  access_type: "admin" | "all" | "scoped" | "none"
}
```

- Admin / "all"-wildcard roles → `full_access`, `allowed_scopes: ["*"]`.
- Scoped roles (h-dcn `Regio_Noord`) → `allowed_scopes: ["Noord"]`.
- A `required_for` capability held **without** any scope grant → **denied** (h-dcn's
  "permission requires region assignment").
- Dimension disabled → everyone `["*"]`.

The **repository/domain then filters** list/read queries to `allowed_scopes` unless `["*"]`.

## Layering (per `sam-module-architecture.md`)

- **`tenant_id` isolation** → repository + IAM `LeadingKeys` (hard boundary, data layer).
- **scope-value filtering** → **domain layer** (it is business policy, not tenancy) — a
  scoped user is still inside their tenant; scope just narrows what they see/act on.
- The generic **domain service** calls `resolve_scope_access`, then asks the repository for
  the tenant's records and filters by `allowed_scopes` (or pushes the filter into the query
  where the key design allows).

## h-dcn as the first instance (reuse, not rewrite)

| h-dcn | Generic scope dimension |
| --- | --- |
| "region" | `scope_dimensions[0].key = "region"`, single-valued |
| Noord/Zuid/Oost/West | `values` |
| `Regio_All` | `all_wildcard` |
| `Regio_*` roles | scoped roles → `allowed_scopes` |
| "permission requires region assignment" | `required_for` + `access_type:"none"` deny |
| `determine_regional_access` / `validate_permissions_with_regions` | the **body** reused inside `resolve_scope_access` (Rung 3 hook if the nuance can't be fully declarative) |

## Cross-club pressure test (general domain knowledge — validate, don't treat as fact)

> These are common patterns across soccer/hockey/tennis/gym/scouting clubs, used to
> stress-test the model. Not repo facts; input for the Go/No-Go.

- **Sub-grouping axis differs** (team/section/location/chapter/region) → same dimension,
  different `key`/`values`. ✅ Rung 1.
- **A member in MULTIPLE sub-groups** (two teams; team + committee) → this is why the model
  supports `multi_valued: true` and a **list** of `scope_dimensions` from the start (h-dcn
  doesn't need it; soccer/hockey do). ⚠️ Design-now decision, not a later retrofit.
- **Season / period scoping** (soccer/hockey run Aug–Jun; teams + fees are season-scoped)
  → likely a **second scope dimension** (`key:"season"`) or a lifecycle-period config.
  ⚠️ h-dcn (federation) may not stress this; a sports-club tenant will.
- **Role × scope for volunteers** (coach/manager scoped to a team) → role × dimension,
  exactly h-dcn's role × region generalized. ✅ Rung 1–2.

## Recommendation (what to build for the pilot)

- Build the scope dimension as a **list of dimensions, each optionally multi-valued**, so
  a soccer/hockey tenant (teams + season, multi-valued) fits without a redesign — but wire
  **h-dcn as a single, single-valued "region"** for the pilot (don't over-build).
- Keep `resolve_scope_access` generic; put any h-dcn regional nuance that isn't declarative
  behind a Rung-3 hook whose body reuses h-dcn's existing functions.
- **Go/No-Go signal:** did h-dcn's region fit purely as config/rules (Rung 1–2), or did it
  need a hook? And would teams+season (a soccer club) fit the same shape? Record both.
