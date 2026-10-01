# Tenant-Onboarding Tooling — Requirements

> **Status:** Phase 1 (DRAFT). This spec defines a reusable, **module-centric** folder +
> secrets convention for onboarding **any tenant to any module**, and migrates the existing
> h-dcn **members** onboarding tooling onto it as the phase-1 pilot. Later phases extend the
> convention to additional modules, additional tenants, and generic (less hand-run) automation.
>
> **Framing (changed requirement):** onboarding is organized by **module**, not by execution
> plane. A module implicitly determines which planes it touches (e.g. the members module spans
> the SAM/DynamoDB data plane, the Flask/MySQL config plane, and the Cognito identity plane);
> the convention therefore does **not** encode a plane in its structure.

## 1. Background & problem

`scripts/aws/` has grown into a flat mix of two different kinds of thing:

- **Tenant-agnostic operator runners** — reusable scripts that take `--tenant` and act on a
  tenant's data/config (`provision-members-tables.py`, `load-cognito-users.py`,
  `seed-hdcn-catalog.py`, `seed-hdcn-members-config.py`, `project-config-to-prod.py`,
  `backfill-hdcn-members.py`, `cleanup-membernum-guard-rows.py`,
  `verify-member-scope-normalization.py`, plus `cognito-users.sample.json`).
- **Tenant-specific config/data** — committed, version-controlled onboarding config for one
  tenant/module (`scripts/aws/h-dcn/`: `ONBOARDING.md`, `members_config.json`,
  `members_source_mapping.csv`, `members_config_loader.py`, `members_mapping_loader.py`).

There is **no documented convention** for where onboarding tooling lives as more tenants and
modules come online, and the two kinds of thing are tangled together. The current `aws/`
grouping also mislabels the work: it names an execution plane, but onboarding a tenant to a
module is a module-level concern that may touch several planes. The scripts are also coupled
by **fragile path logic**: triple-`os.path.dirname()` walks to find the repo root, and
sibling-directory by-path imports that break the moment a file moves.

## 2. Goals

1. Establish a **reusable, documented, module-centric folder convention** for tenant-onboarding
   tooling that scales to many tenants and many modules without duplicating generic runners and
   without encoding an execution plane in the structure.
2. Establish a **tenant-wide onboarding-secrets convention** so a tenant's cross-plane,
   cross-module onboarding material (one or more co-located credential files, sheet IDs, Drive
   folder IDs) lives in exactly one tenant-owned place, with obvious ownership, and is never
   duplicated per module. These are onboarding-only credentials, distinct from the production
   secret store.
3. **Migrate the h-dcn members onboarding tooling** onto the new convention as the pilot,
   fixing the brittle path/import coupling in the process.
4. Keep the migration **behavior-preserving**: every script does exactly what it did before,
   from new paths, with every existing CLI flag intact.

## 3. User stories & acceptance criteria

### R1 — Module-centric, plane-agnostic organization
**As** an operator onboarding a tenant to a module,
**I want** onboarding tooling organized by module (not by execution plane) with reusable
runners separated from tenant-specific config,
**so that** the structure matches how onboarding actually works and I never copy generic code
per tenant.

- R1.1 Onboarding tooling is grouped by **module**. The structure does **not** encode an
  execution plane; the module implicitly determines which planes it touches.
- R1.2 Within a module, **tenant-agnostic runners** are separated from **tenant-specific,
  version-controlled config** so a runner is never copied per tenant.
- R1.3 A runner is reusable across tenants via `--tenant`; it contains no hardcoded tenant.
- R1.4 The convention generalizes: adding a new module or a new tenant means adding a folder in
  the established places, with no change to generic runners.

### R2 — Tenant-wide onboarding secrets, co-located per tenant
**As** an operator,
**I want** a tenant's onboarding secrets and credentials in one tenant-owned location,
**so that** every module (members/events/webshop) and every plane it touches read the same
file, and ownership of a credential is always obvious.

- R2.1 Per-tenant onboarding values live in one **tenant-wide** location (one dir per tenant),
  not under any module leaf, so they are shared across all of a tenant's modules and planes.
- R2.2 These are **onboarding-only** credentials, explicitly **not production** secrets.
  Production secrets have a separate solution (encrypted, in MySQL); this convention is for
  operator-local, discoverable, finite-lifetime onboarding material and must not be treated as
  the production secret store.
- R2.3 A tenant may need **one or more credentials** for onboarding (e.g. a Google
  service-account key for Sheets/Drive, and potentially others later — a different Google
  project, a source-system API token, an SFTP key). Credentials are declared as a **named map
  keyed by purpose**, each entry carrying a `type` and (for file-based credentials) a filename;
  the convention is extensible to new credential kinds without inventing new top-level fields.
- R2.3a Each credential file is **co-located in the tenant folder** — git-ignored — so its
  tenant ownership is self-evident. A credential must **not** live in an external,
  workspace-detached path, because such a path leaves no trace of which tenant it belongs to or
  whether it is safe to delete. (This supersedes the legacy h-dcn arrangement where the key sat
  in a separate, soon-to-be-removed workspace.)
- R2.4 Two-file convention: a **committed** non-secret template `secrets.example.json` and a
  **git-ignored** real file `secrets.local.json`. The real file holds the named credentials map
  (referencing each co-located credential by its sibling filename) alongside non-secret IDs.
- R2.5 Everything in the tenant folder is **git-ignored by default** EXCEPT the committed
  template(s) and README — so any credential file (named or not yet anticipated) is never
  committed, while the convention stays self-documenting.
- R2.6 The named-credentials map is a **declarative convention** that admits any credential
  `type`. Phase 1 **wires only the file-based type** the members pilot needs (a co-located key
  file resolved relative to the tenant dir); other types (env/token, ssh-key, …) are a
  documented pattern, not built, until a tenant needs them (no speculative resolver machinery).

### R3 — No silent substitution
**As** an operator,
**I want** missing config to fail loudly,
**so that** a script never writes to the wrong place with a blank/placeholder value.

- R3.1 The secrets resolver **errors and names the missing key** when a required key is absent
  or blank; it never substitutes a default secret value (mirrors ONBOARDING Decision D16).
- R3.2 `--tenant` stays **required with no default** (R8 / steering 31). Only the secrets
  *path* is convention-derived.
- R3.3 A `--secrets <path>` flag overrides the convention path; explicit per-value flags
  (e.g. `--sheet-id`, `--credentials`) override the file.

### R4 — Robust path/import resolution
**As** a maintainer,
**I want** path/import resolution that survives relocation,
**so that** moving a script doesn't silently break imports.

- R4.1 Repo-root + `backend/src` are placed on `sys.path` by walking up to a **repo marker**,
  not by counting `dirname` levels.
- R4.2 Cross-script and loader imports go through a shared `_lib`, not by sibling-dir path
  joins.

### R5 — Behavior preservation & safety
- R5.1 Every migrated runner remains **dry-run-first** and **idempotent**; defaults write
  nothing.
- R5.2 Every existing CLI flag keeps working (`--config`, `--sheet-id`, `--credentials`,
  `--pool-id`, `--source`, `--apply`, `--reconcile`, …).
- R5.3 Git history is preserved on relocations where practical (`git mv`).

### R6 — Git & scanner hygiene
- R6.1 The existing `.gitignore` carve-out that keeps **module tenant config** tracked (while
  the repo-root legacy tenant dir is ignored) is preserved and retargeted to the new module
  config location.
- R6.2 The tenant **secrets** folder is **ignored by default**, with the committed template(s)
  and README explicitly un-ignored (R2.5) — so a credential file co-located there (named or
  not yet anticipated) is never committed, and no tracked file in the tree is caught.
- R6.3 `.gitguardian.yaml` path references follow the move; the local secrets scan
  (`scripts/scan-secrets-local.sh`) stays clean.

### R7 — Documented contract for future phases
- R7.1 The onboarding root carries a README documenting the convention (module-centric layout,
  generic vs tenant-specific config, the shared resolver, tenant-wide secrets, dry-run-first).
- R7.2 The tenant-secrets root carries a README documenting the one-dir-per-tenant, tenant-wide
  (cross-module, cross-plane) rule.
- R7.3 The spec's `tasks.md` records phase-1 completion and lists deferred phases.

## 4. Out of scope (deferred to later phases)

- Onboarding tooling for modules other than `members` (e.g. events, webshop).
- Onboarding additional tenants beyond h-dcn.
- Generic, less hand-run automation (orchestrating the full sequence from one entry point).
- Any change to what the scripts *do* (data model, backfill decisions, enum vocabularies) —
  this phase is a relocation + robustness refactor only.

## 5. Phasing

- **Phase 1 (this spec):** folder + secrets convention; migrate h-dcn members pilot; make
  path/import resolution robust; update git/scanner config; document the contract.
- **Phase 2+ (deferred):** apply the convention to additional modules and tenants; build
  higher-level orchestration on top of the stabilized contract.
