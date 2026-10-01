# `scripts/onboarding/` — tenant-onboarding tooling

Tooling for onboarding a **tenant** to a **module**. Organized **by module** — the structure
does NOT encode an execution plane, because a module implicitly determines which planes it
touches (the `members` module spans the SAM/DynamoDB data plane, the Flask/MySQL config plane,
and the Cognito identity plane).

Spec: `.kiro/specs/Common/Tenant/tenant-onboarding-tooling/`.

## Layout

```
scripts/
  onboarding/
    README.md                 # this file — the convention
    _lib/                     # shared helpers (NOT tenant/module specific)
      paths.py                #   repo-root + backend/src on sys.path via a repo-MARKER walk
      secrets.py              #   tenant secrets loader + named-credentials resolver
    <module>/                 # e.g. members/
      _generic/               #   tenant-agnostic runners (parameterized by --tenant)
        README.md             #     per-runner purpose + usage tracking
      <tenant>/               #   that tenant's COMMITTED config + tenant-specific runners
        README.md             #     (e.g. h-dcn/: config, loaders, the Ledenbestand importer)
  tenants/
    <tenant>/                 # that tenant's cross-module, cross-plane SECRETS (git-ignored)
```

Two separate axes, deliberately kept apart:

- **`onboarding/<module>/_generic/`** — reusable runners. A runner takes `--tenant` and never
  hardcodes a tenant; it reads only generic `sam.<module>.*` code.
- **`onboarding/<module>/<tenant>/`** — a tenant's **committed, version-controlled** config for
  that module (field overlay, scope dimensions, mapping CSV, the ONBOARDING runbook) **plus any
  runners whose payload is tenant-specific** (e.g. h-dcn's Ledenbestand importer and its
  catalog/config seeds live in `members/h-dcn/`, co-located with the config they read).
- **`tenants/<tenant>/`** — a tenant's **git-ignored** onboarding secrets (credentials + IDs),
  shared across every module and plane. See `scripts/tenants/README.md`.

## Conventions

- **Robust paths (R4).** Runners find the repo root by walking up to a marker (`.git`/`.kiro`),
  not by counting `../` levels — so a script survives being moved to any depth. Repo-root +
  `backend/src` go on `sys.path` via `_lib.paths.ensure_backend_src_on_path()`. Loaders that
  live in a dashed, non-package dir are imported via `_lib.paths.import_by_path`.
- **Secrets precedence (R2/R3).** `explicit CLI flag  >  tenant secrets.local.json  >  loud
  named error`. There is no third fallback: a missing required key fails, naming the key. See
  `scripts/tenants/README.md` for the named-credentials map.
- **Dry-run first (R5).** Every runner defaults to a dry-run that writes nothing; `--apply`
  performs writes. Runners are idempotent and never auto-target a tenant (`--tenant` is required
  with no default, except where the operation is tenant-global such as table provisioning).

## Adding a new module or tenant

- **New module** `M`: create `onboarding/M/_generic/` (runners) and `onboarding/M/<tenant>/`
  (committed config); reuse `_lib` unchanged.
- **New tenant** `T` for an existing module: add `onboarding/<module>/T/` (config) and
  `tenants/T/` (secrets). No change to the generic runners.
