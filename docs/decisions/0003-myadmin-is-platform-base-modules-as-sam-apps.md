# ADR 0003 — myAdmin is the platform base; evolve in place; import apps as SAM-backed modules

- Status: Accepted
- Date: 2026-09-15
- Supersedes: ADR 0001 (new target workspace `mysaas`), ADR 0002 (myAdmin = pattern
  source, not trunk)

## Context

Two systems are being unified into one multi-tenant platform: h-dcn (AWS SAM +
DynamoDB member portal/webshop, greenfield — only real user webmaster@h-dcn.nl) and
myAdmin (Flask + MySQL finance app on Railway, live with real tenants/data).

ADR 0001 decided to create a new, clean workspace (`mysaas`) as the platform trunk,
seed it from analysis, author fresh governance, and lift myAdmin's admin code into
it. ADR 0002 refined that to "myAdmin is the pattern source and the admin-plane code,
not the single trunk."

That approach was pursued and did not work. Standing up a fresh trunk meant
re-hosting proven, live code before delivering anything, and the discipline it
required — the new workspace being the "definition of record from day one" — was not
sustainable; real work kept happening in myAdmin. Meanwhile myAdmin already contains
a working, live multi-tenant foundation: the `administration` tenant key,
`@tenant_required` / `tenant_context.py`, provisioning services, `jwt_verifier.py`,
and — critically — a module system (`tenant_modules` table + `MODULE_REGISTRY` /
`module_registry.py`, today serving FIN, ZZP, STR, TENADMIN).

## Decision

**myAdmin is the platform base, and we evolve it in place.** There is no separate
`mysaas` trunk and no workspace merge.

Additional applications are imported as **platform modules**, not as a new trunk.
myAdmin's existing module system is generalized so that a module can be **backed by
an AWS SAM app** (Lambda + DynamoDB), not only by in-process Flask/MySQL code:

- A SAM-backed module registers in `MODULE_REGISTRY`.
- A tenant is entitled to it via the `tenant_modules` table (keyed by
  `administration`).
- The module authorizes requests from the verified Cognito token.
- The module scopes its data by `tenant_id`.

The h-dcn portal/webshop is imported as the first such SAM-backed module, keeping its
serverless/DynamoDB stack on its own plane. Governance is myAdmin's existing
`.kiro/steering`, extended in place — never replaced by a from-scratch set.

## Rationale

- myAdmin already carries the proven, live multi-tenant machinery; building on it
  means extending working code rather than reconstructing it in a fresh repo.
- Importing apps as modules keeps each domain on its optimal stack — the portal stays
  serverless/DynamoDB rather than being dragged toward MySQL/Flask. The two-plane
  design (Flask/MySQL admin+finance + SAM/Lambda/DynamoDB modules) is deliberate.
- There is a single place of record (myAdmin), so no second workspace risks becoming
  an aspirational graveyard while real work stays elsewhere.
- Production risk is managed by the test-environment discipline (standing test
  Cognito pool + Docker MySQL + `test_` DynamoDB, gated promotion to production), not
  by relocating code to a new trunk.

## Consequences

- Roadmap step S1 is "prepare myAdmin to host SAM-backed modules" — define the
  generic module plug-in contract and extend steering — replacing the earlier
  "establish `mysaas`" / "lift admin code" steps (former S1/S1b/S6b).
- The h-dcn domain is imported as a SAM-backed module; its code is refactored in
  place onto the module contract rather than merged into the Flask/MySQL plane.
- Reusing myAdmin's code and patterns is expected. The live system is not renamed.
- Identity (two audience-split Cognito pools), MySQL-as-system-of-record, and
  token/table projection decisions are unaffected and carry forward.

### Consequences — S1 refinement (concrete `backing` shape)

S1 (spec `s1-prepare-platform`, Phase 1) settled the concrete shape of the module
"backed by a SAM app" concept in `MODULE_REGISTRY`. Recorded here (append-only) as a
material sub-decision of this ADR:

- `backing` is an **optional** block on a `MODULE_REGISTRY` entry. **Absence means
  in-process Flask** (the default), so FIN/ZZP/STR/TENADMIN are unchanged and carry
  no `backing` key.
- `backing.kind`: `"flask"` (default when omitted) or `"sam"`.
- `backing.api_base_env` (`sam` only): the **name** of the env var that yields the
  module's API base URL — the registry **never stores a URL**; resolution **fails
  fast** (no fallback) if the env var is unset/empty.
- `backing.data_namespace` (`sam` only, optional): DynamoDB table prefix/namespace.
- Read-only accessors: `module_backing(module_name) -> "flask"|"sam"` and
  `resolve_module_api_base(module_name) -> str|None` (fail-fast for `sam`), so call
  sites never inspect the dict shape.

## Related

- ADR 0001, ADR 0002 (both superseded by this decision).
- `overall_roadmap.md`, `myadmin_as_base.md`, `second_thoughts.md`.
