# Spec: Admin Surface Registry (tenant administration architecture)

**Status:** Draft · **Created:** 2026-11-17
**Domain:** `Common/Tenant` (platform / admin surface)

> **Moved here 2026-11-17** from `.kiro/specs/myBacklog/tenant-administration-architecture.md` —
> the backlog candidate graduated into this functional area (`git mv`, history preserved).
> The **normative** parts of this spec are the trio
> [`requirements.md`](./requirements.md) · [`design.md`](./design.md) · [`tasks.md`](./tasks.md).
> The original framing that this spec grew out of is preserved below under
> [Original framing](#original-framing-moved-from-mybacklog-2026-11-17) with inline `[updated]`
> notes where the finished design diverged from the first sketch.

## What this is

The Tenant-Admin dashboard renders a **flat, hardcoded tab list with ad-hoc gating**
(`frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`). Some tabs always render,
some are `if hasFIN`, one is `if hasMembers`, none model *why* a surface exists. This spec
replaces that with **one registry of admin surfaces** in which each surface declares *when it
applies*, and each module declares *what it consumes*. The dashboard then **derives** its tabs
instead of hardcoding them.

## The four kinds of admin surface

> The original framing below listed **three** kinds (`always` / `module` / `capability`). This spec
> adds a fourth — `role` — so the generic Advanced surface is *registered* rather than special-cased.

| Kind | Meaning | Examples | Applies when |
| --- | --- | --- | --- |
| `always` | Platform baseline for any Tenant Admin | Users, Tenant Info, Sender, Landing Page | unconditional |
| `module` | Config owned by exactly one module | Financial (FIN), Members (MEMBERS) | that module is entitled |
| `capability` | Cross-cutting surface that **serves** modules | Storage, Templates, Media, Pivot, Functions | **any entitled module declares it consumes the capability** |
| `role` | Role-gated generic surface | Advanced (raw namespace params) | caller holds a required role |

## The three planes — and where tenant config actually lives

This feature ships on **three delivery planes** (steering 40, "All-planes delivery") — keep that
topology separate from the question of *who owns config*:

| Plane | Code | Role in this spec |
| --- | --- | --- |
| **Frontend** | `frontend/src/**` | Renders the derived surfaces; **owns no config namespace**; the only bridge — it performs each plane's write |
| **Flask** | `backend/src/**` | The surface registry + derivation + `GET /api/tenant/admin-surfaces`; author of `flask`-owned config |
| **Module** | `sam/**` ("Plane B") | Author of its own `config#*` rows (Change-Op path); reader of the projection |

Within those three planes, **config ownership is a two-way relation**: each tenant-scoped namespace
is written by exactly one owner. That is a property of a *namespace*, not a taxonomy of planes —
calling the owners "two planes" would hide the frontend, which is a plane and does write, as the
bridge:

| | `flask`-owned | `module`-owned |
| --- | --- | --- |
| Store | MySQL `parameters` (via `ParameterService`, scoped user → role → tenant → system) | DynamoDB governance projection, `config#*` rows |
| Writer | the Flask plane (retired per namespace once cut over) | the owning module's Change-Op write path |
| Reader | Flask; a module only via a projected row | the module's projection reader / resolved (Flat_View) model |
| Example | `storage.*`, `fin.*`, `str.*`, `zzp.*` | `members.*` → `config#fields` / `config#scope` / `config#mail` |
| Editor | **Advanced** (generic) or a Flask typed editor | the module's **typed** editor only |

**Consequences** (normative text in `requirements.md` Req 7 + 11, `design.md` §7 + §8):

- `Advanced` is the generic MySQL-`parameters` editor, so it covers **only** `flask`-owned
  namespaces. It must never render `members.*` — that table is not that namespace's store, and a
  second door there is the *two-writers-one-config* hazard the module-plane cutover removed.
- `ProjectionSync` emits **zero** `config#*` rows today: the module plane owns every one of them
  (split ownership — it owns `config#*`, `ProjectionSync` owns `tenant`/`module#`/`role#`/`scopegrant#`).
- The two **backend** planes never call each other at runtime; the **frontend**
  performs each plane's write separately — module-plane first (authoritative), then the Flask leg as
  a best-effort mirror — and surfaces a mirror failure.
- `admin.typed_editor.owner` (`flask` | `module`) records ownership, so the boundary is checked at
  startup rather than trusted to prose.
- **Scope:** ownership governs **tenant-scoped** namespaces that an admin surface edits. User-scoped
  config (e.g. per-user column preferences, served by the module plane) and pure frontend UI state
  are not namespaces and are out of scope.

## Files

| File | Contents |
| --- | --- |
| [`requirements.md`](./requirements.md) | Glossary + numbered requirements with acceptance criteria, success metrics, out of scope |
| [`design.md`](./design.md) | Registry schema, derivation algorithm, API contract, decisions D1–D6, correctness properties, error handling, testing strategy |
| [`tasks.md`](./tasks.md) | Phased task breakdown with requirement traceability, all-planes coverage, CI/CD tasks |

## Original framing (moved from myBacklog, 2026-11-17)

_Verbatim from the backlog candidate, except for the `[updated]` notes that flag where the finished
design diverged from the original sketch._

**Problem:** the Tenant-Admin dashboard tabs are a HARDCODED flat list with ad-hoc gating
(`frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`): some tabs always render
(Users, Functions, Storage, Templates, Media, Tenant Info, Sender, Pivot, Landing), FIN shows
`if hasFIN`, Members `if hasMembers`, Advanced `if isSysAdmin`. There is NO model of "which admin
surface belongs to / is needed by which module", so the differences a user sees
(FIN admin gets Advanced/Storage; Members admin gets a 4-subtab editor; etc.) are ACCIDENTAL, not
designed. Standardize it.

### The three KINDS of admin surface (the core model — as originally framed)

> `[updated]` The finished registry formalises these as a `kind` value on each surface:
> kind 1 → `capability`, kind 2 → `module`, kind 3 → the generic `role`-gated `advanced` surface.
> Note the plane split above: `advanced` is a **Flask `parameters` editor only**, so kind 3's
> "editor" covers Flask-authored namespaces — a module-plane-owned namespace (`members.*`) is
> covered solely by that module's typed editor. See `design.md` §1, §7 and §8.

1. **Cross-cutting capabilities** — Storage, Functions, Pivot, Templates, Media Assets, Advanced.
   Not owned by one module; they SERVE modules. Storage is the clearest: one tenant choice that
   many object-storing modules (FIN invoices, Members docs, STR) consume.
2. **Module-specific config** — Financial (FIN), Members (MEMBERS). Owned by exactly one module;
   meaningful only when that module is entitled. A module's panel may be a single view (FIN) or a
   sub-tabbed panel (Members' 4 tabs) — richness is the module's own concern, NOT something to
   force uniform.
3. **Namespace-driven parameter views** — "Advanced" is the generic one: it renders ALL params in
   a namespace as a table. It is not a feature; it is a GENERIC parameter editor pointed at a
   namespace. Members' typed config editor is the FRIENDLY version of the same underlying thing.

### The architecture: one registry of admin surfaces + modules declare what they CONSUME

> `[updated]` The finished declaration is a single `admin: {panel, consumes, typed_editor}` block per
> module (the `admin_panel` sketch below became `panel`); see `design.md` §2.

Replace the hardcoded tab list with a registry; each surface declares WHEN it applies:
- **`always`** — platform baseline for any Tenant_Admin (e.g. Users, Tenant Info).
- **`module: <NAME>`** — shown only when that module is entitled (Financial→FIN, Members→MEMBERS).
- **`capability` (cross-cutting)** — shown when ANY entitled module DECLARES it consumes that
  capability. Storage renders because some entitled module said `consumes: storage`, NOT because
  it is hardcoded always-on.

Extend `MODULE_REGISTRY` (`backend/src/services/module_registry.py`) with an admin declaration
per module, e.g.:
```
FIN      → admin_panel: "financial";  consumes: [storage, templates, pivot]
MEMBERS  → admin_panel: "members";    consumes: [storage, media]
STR      → consumes: [storage, pivot]
```
The dashboard DERIVES its tabs: baseline ∪ (module panels for entitled modules) ∪ (cross-cutting
surfaces any entitled module consumes) ∪ (role-gated surfaces e.g. Advanced for SysAdmin). No
if-ladder. Adding a module's admin surface = one registry entry, not editing the dashboard.

### Storage — a SHARED CAPABILITY with a per-tenant choice (the key example)
Storage is "one choice relevant for many modules that store objects." Architecture:
- **Config once** — a tenant-scoped param (`storage.invoice_provider`, options
  google_drive/s3_shared/s3_tenant), authored in the Storage admin surface.
- **Many consumers via one resolver** — `services/storage_resolver.py::resolve_storage_provider`
  is the single dispatch; FIN, Members, STR all call it. (This is the config-value→handler
  pattern; see the "Member number policy" spec's StrategyResolver — Storage is a sibling use.)
- **Surface visibility** — the Storage tab appears when an entitled module declares
  `consumes: storage`. So a Members-only tenant that stores docs still gets Storage; a tenant
  whose modules store nothing does not.

### "Advanced" + Members config — one thing at two polish levels (namespace parameter editing)

> `[updated]` **Advanced is NOT SysAdmin-gated**, contrary to the Problem line above (`if isSysAdmin`)
> and the "role-gated surfaces e.g. Advanced for SysAdmin" note below. The shipped dashboard shows it
> to any Tenant_Admin of the tenant, and the backend scopes rows to the tenant's active modules and
> masks secrets. The finished design keeps that and records it as Decision **D3** (`design.md`
> §Decisions) so it is a decision rather than an accident.

> MOVED (2026-10-12) → `.kiro/specs/Members/Parameter redesign/analysis.md` §2.4 (the typed-vs-raw
> namespace-editor model now lives next to the Members dual-surface #12 it shapes). The platform-wide
> admin-surface registry that makes "Advanced" a registered catch-all surface stays this spec's
> concern — see the SCOPE line below ("the generic namespace param editor").

### Open questions (design pass) — resolved 2026-11-17

> **All four are now answered.** Q1 (always vs capability) → Decision **D1**; Q2 (where the registry
> lives) → **D2** (backend); Q3 (relationship to `tenant_functions`) → **D4**; the SCOPE line became
> this spec. The rulings are in `design.md` §Decisions and the work is in `tasks.md`.

- Which cross-cutting surfaces are truly `always` vs `capability`-consumed? Today Storage/
  Templates/Media are always-on — likely wrong for a module that stores nothing. Make each an
  explicit per-module `consumes` decision.
- Where does the admin-surface registry live: extend `MODULE_REGISTRY` (backend, projectable) vs
  a frontend-only surface map? Prefer backend so both the entitlement truth and the surface
  declaration share one source.
- Relationship to `tenant_functions` (the Functions tab): that is the WITHIN-module toggle layer;
  the admin-surface registry is the WHICH-surfaces layer. Keep them distinct but consistent.
- SCOPE: `MODULE_REGISTRY` + `TenantAdminDashboard.tsx` + the generic namespace param editor +
  the storage resolver. Relates to: "Member identity & number policy" (StrategyResolver / config
  patterns), "Fail-loud integrity" (generic-vs-tenant placement), "Shared frontend component
  library" (the dashboard is a reuse consumer). Own spec **— now this spec; the backlog entry was retired on 2026-11-17.**

## Related specs (consumed, not redefined)

- **Config & parameters:** `.kiro/steering/36-config-and-parameters.md` — "config-value selects a
  registered strategy" (the resolver shape Storage rides).
- **Typed-vs-raw namespace editor model:** `.kiro/specs/Members/01 - members-config-projection-and-cleanup/Parameter redesign/analysis.md` §2.4 — *the reference in the framing above points at the older `Members/Parameter redesign/` path, which has since moved.*
- **Optional functions:** `.kiro/specs/Common/Tenant/tenant-optional-functions/` (`FUNCTION_REGISTRY`) — the *within-module* toggle layer; this spec is the *which-surfaces* layer.
- **Storage routing:** `backend/src/services/storage_resolver.py`; `.kiro/specs/FIN/provider-aware-folder-routes/`.
- **Frontend conventions:** `.kiro/steering/32-frontend-ui.md`; **CI/CD:** `.kiro/steering/43-cicd-deploys.md`.
- **Decision records (`docs/decisions/`):** ADR **0003** (platform base + the `backing` contract shape this spec extends), **0004** (verified-JWT-only), **0005** (MySQL system-of-record + one-directional projection — *its decision text still needs the config-ownership carve-out note*), **0006** (entitlement in token via PreTokenGen), **0007** (active-tenant resolution at the module edge), **0009** (`config#fields` Change-Op CRUD, read stays the Flat_View). Full mapping: `design.md` → *Alignment with decision records*.
