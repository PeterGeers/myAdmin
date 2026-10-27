---
inclusion: fileMatch
fileMatchPattern: "sam/**/*.py"
---

# Data & Service Access (SAM plane / DynamoDB)

> **Scope: the SAM module plane only** (`sam/**`). This is the DynamoDB counterpart to
> `31-backend-database-flask-mysql.md`. The LAYERING (handler → service → repository →
> DynamoDB) is owned by `35-sam-module-architecture-sam.md`; this file adds the DATA-ACCESS
> rules that keep storage shape from leaking. Both planes are specializations of one principle:
>
> **A store's raw record shape and its client stay inside the repository. Every consumer —
> handler, domain service, API response, and the frontend — uses a RESOLVED domain view for
> READ and writes by DOMAIN IDENTITY. No consumer ever sees or reconstructs the physical layout.**

This rule exists because its absence caused a real, repeated production bug: the raw
`config#fields` item shape (`fields` / `overrides` / dotted `{group}.{key}` keys) was served to
the frontend, which then reconstructed that identity and drifted from it — empty groups, missing
fields, stuck toggles. See `.kiro/specs/Members/root-cause-analysis.md`.

## Abstraction layer

All DynamoDB (and SES / SNS / S3 / SQS / CloudFront / outbound HTTP) access goes through the
**repository layer** (`sam/<module>/repository/`, plus `sam/shared/` for the JWKS fetch). No
handler or domain file constructs or imports a service client.

```python
# repository owns the client; everyone else depends on an injected interface
from sam.members.repository.projection_config_reader import MembersProjectionReader
```

- **No `boto3` (client/resource), no `requests`/`urllib`/`http.client`, outside the repository
  layer.** This mirrors `31`'s "no `mysql.connector` outside `database.py`". The allowed files are
  the explicit list the access guard reads (see Enforcement).
- Handlers call domain services; domain services call repositories via a constructor-injected
  Protocol; `app.py` is the single composition root that wires the real repository in (tests
  inject an in-memory fake — the existing `Static*Provider` pattern).

## The resolved-view contract (the core rule)

- A repository returns a **resolved domain view** — origin-agnostic, identity-stable. For
  `config#fields` that is the flat field list keyed by the **bare `key`**, each field carrying its
  resolved `functional_group` (the server already computes `functional_group or group`). The
  physical two-map/dotted-key layout (`fields` vs `overrides`, `personal.gender`) is an INTERNAL
  detail of the repository.
- A repository accepts a **write by domain identity** (field `key` + the attribute change) and
  performs the logical→physical placement itself (which map, which key). **The caller never
  supplies physical placement.** The frontend never constructs `{group}.{key}`.
- **Raw record shape MUST NOT cross the repository boundary** — not to a domain service, not into
  an API response, not to the frontend. Specifically: an API response MUST NOT carry
  `field_overlay`, `overrides`, `fixed_overrides`, or dotted `{group}.{key}` keys.
- A repository method that returns the raw item (e.g. a legacy `get_raw_*`) is a code smell; it may
  exist only as an internal helper, never on the API/cross-boundary path.

## The Change-Op write contract (no whole-record replace)

> This is the write-side companion to the resolved-view read rule above. It generalizes the fix
> proven for `config#fields` (ADR
> [`0009-config-fields-crud-change-op-server-owned`](../../docs/decisions/0009-config-fields-crud-change-op-server-owned.md);
> reference spec `.kiro/specs/Members/03 - config-fields-foolproof-crud/`). It is the SAM-plane
> default for any mutable aggregate, not a config-only special case.

- **A write is a Change-Op addressing ONE domain identity, never a whole-record replace.** The
  client sends intent by identity (which field/group/attribute, and the new value) — it never sends
  a whole record, a whole catalog, or any physical container to be stored wholesale. The
  server-owned placement rule (above) decides the physical path.
- **Writes address a single path via `update_item`.** The repository translates the identity to one
  path expression (`SET`/`REMOVE` on a named attribute path) and issues a single path `update_item`.
  DynamoDB leaves every attribute the op did NOT name physically untouched, so untouched
  slices and base-derived definitions survive **by construction** — not "if an in-memory merge is
  perfect". A partial payload therefore cannot truncate a sibling slice or a catalog.
- **The whole-record `put_item` is an internal create/migration primitive ONLY — never
  client-reachable.** It is sanctioned solely for (a) seeding a new record's skeleton at
  create time and (b) a one-time migration backfill. No handler, domain service, API body, or
  frontend path may reach it. The write INTERFACE exposes only Change-Ops, so the dangerous
  whole-replace operation does not exist to be misused.
- **Merge_Target = Resolved_Record.** When placement needs the current state (to validate the op and
  pick the physical path for a base ⊕ overlay aggregate like `config#fields`), the server reads the
  **Resolved_Record** (the same resolved domain view consumers read), with `ConsistentRead=True`, and
  uses it ONLY to validate + choose the path — it does NOT read-merge-write the whole record. The
  single `update_item` is then issued against that one path. This keeps read and write reasoning on
  the SAME resolved view, and keeps the stored row a minimal delta.
- **Clear-vs-unchanged semantics:** within an op, an ABSENT attribute means "leave untouched" (no
  path written); an explicit `null` means "remove that attribute" (a scoped `REMOVE`). Reverting a
  whole override is an explicit reset op, not a payload of nulls.
- **Concurrency is version-conditional.** Each Change-Op's `update_item` carries a
  `ConditionExpression` on the record's `version` (and bumps it in the same expression), so a stale
  write fails cleanly with no partial change and surfaces as a caller-safe 409 (reload-and-retry) —
  never last-writer-wins.

## Core rules

- **Fail-fast resource resolution:** the table/bucket/queue resolves from an environment variable
  with **no default** (`GOVERNANCE_PROJECTION_TABLE` model, `35`/spec 02); a missing value raises at
  the first real call, never silently targets the wrong resource.
- **Tenant isolation:** `tenant_id` partition key, resolved from the verified token — never from the
  request body; `LeadingKeys` as documented in `23-aws-accounts.md` / `35`. No `.scan()` across
  tenants.
- **Accounts/identity:** follow `23-aws-accounts.md` and the override-ranking trap in
  `41-shell-environment.md`; never hard-code account ids or endpoints in a repository.
- **One repository per external service / aggregate** — each with a tight, intention-revealing
  method set (domain operations, not `get_raw_item`). Today: the `config#*` reader/writer, the
  members repository, `slug_marker_store` (S3), `mail_send_queue`/`mail_send_adapters` (SES/SQS),
  `scheduler_api`, `template_body_store`.

## Change-with-tests + real data (non-negotiable)

- A behavior change to a repository or the view it returns updates its paired test in the SAME
  change (`34-backend-testing.md`).
- **Prove round-trips against REAL data, not a hand-built fixture.** For config, use the real
  `config#fields` row (e.g. `h-dcn`) and assert read → write → read preserves the field (identity,
  group, flags). "Tests pass" and "task checked" are NOT sufficient evidence — a wrong fixture has
  hidden this exact bug before (spec 11: *trust runs, not inference*). Before marking a data-touching
  change done, exercise it against a real row.

## Enforcement (so the rule can't silently decay)

- **Access guard** (mirrors the Flask `DB-access` pre-commit guard): a committed
  `scripts/check_sam_service_access.py` that fails on (a) a service-client import outside the
  allowed repository/shared files, (b) a raw-shape key (`field_overlay` / `overrides` /
  `fixed_overrides`) in an API response, and (c) a raw `put_item`/`update_item`/`delete_item` on the
  governance table outside the Change-Op write repository (so the whole-record replace stays an
  internal primitive — the Change-Op write contract above). Wired into `.githooks/pre-commit` and
  CI (`43-cicd-deploys`).
  A new egress is added to the allow-list in a reviewed change — never by suppressing the guard
  (`--no-verify` is not the path).
- **Boundary test** (`sam/tests/test_handler_repository_boundary.py`): asserts the layering imports
  and that a handler response (over the real fixture) carries no raw-shape key.
- Introduce the guard report-only, clear the baseline, then flip to blocking — never red every branch
  on day one.

## Reference

- Layering + responsibility matrix: `35-sam-module-architecture-sam.md`.
- Field-config specifics: `38-sam-module-field-config.md`.
- Change-Op CRUD decision + the first (hardest) application: ADR
  [`0009-config-fields-crud-change-op-server-owned`](../../docs/decisions/0009-config-fields-crud-change-op-server-owned.md)
  + spec `.kiro/specs/Members/03 - config-fields-foolproof-crud/`.
- Flask/MySQL sibling: `31-backend-database-flask-mysql.md`.
- Why this exists: `.kiro/specs/Members/root-cause-analysis.md`.
