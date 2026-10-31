# SPEC CANDIDATE: SAM-plane data migration framework (versioned, ledgered, pipeline-run)

**Status:** BACKLOG — proposed after a real PROD incident (see "Motivating incident"). Not started.

## Problem

The SAM / DynamoDB plane has **no standard data-migration process**, unlike the Flask / MySQL
plane (which has a schema + a migration runner on schema `finance` — see the `#database` skill).
When a SAM change alters how STORED data is read or written (a "reader/writer contract change"),
nothing forces the already-stored data to be migrated in lockstep with the code. Backfills are
one-off scripts run **by hand**, per environment, with no record of what ran where. So a backfill
that was run on TEST but forgotten on PROD ships a code change that the PROD data does not satisfy —
and there is no checkpoint that would have caught it.

MySQL gets this discipline for free: a relational schema is ENFORCED, so a column/constraint change
*must* be applied in lockstep and there is a natural, mandatory migration step. DynamoDB is
schemaless and the app tolerates heterogeneous item shapes by convention (empty-is-valid, additive
fields, resolver fallbacks). That flexibility is exactly what lets a contract/data drift hide until
a request hits the one tenant whose data was never migrated.

## Motivating incident (2026-10-30) — the `choices → options` gap

Spec 03a (C7) changed the Members overlay reader to read enum vocabulary ONLY from `options` and
to STOP reading the legacy `choices` key (`_fields_overlay_reader._build_overlay_field` /
`_build_override`). A one-time `choices → options` **backfill** was meant to run per environment.
It ran on TEST (local DynamoDB) but **never on PROD**. After the `test → main` promotion deployed
the new reader to PROD, h-dcn's enums that still carried only `choices` resolved to `options=None`,
tripping `FieldResolver._reject_invalid_overlay` → `OverlayError("an enum variable field must
declare choices/options")` → `GET /members/field-config` **500** → empty member view/edit modals
in production. (region was exempt — scope-backed fields source values from `config#scope`.)

The fix was a hand-run targeted repair over the real PROD `config#fields` row (convert each enum's
stored `choices` into `options` preserving the tenant's OWN values — e.g. h-dcn's `died` status and
its `M/V/X/N` gender set the base code does not define — and drop the stale `choices` on scope/
reference fields). Exactly the backfill C7 intended, done late and manually. **A ledgered,
pipeline-run migration would have made the missing backfill impossible to forget.**

## Why a spec later, not a fix now

This is cross-cutting (every SAM module's data + the deploy pipeline + steering) and must not be
retrofitted carelessly onto a live data path. It is framework work, not a bug patch.

## Proposed approach (in leverage order — mirror existing patterns, don't invent a framework)

### 1. Versioned, idempotent migration scripts under source control (the core)
A `sam/<module>/migration/` dir already exists (e.g.
`membership_type_catalog_to_field_options.py`). Formalize it:
- One **numbered** script per data change: `0001_choices_to_options.py`, `0002_…`. The number is
  ordering + identity.
- Each is **idempotent / re-runnable** — re-running a completed migration is a no-op (the same
  property `ConfigFieldsCrudService.remove_legacy_choices` already has: no-op when the key is
  absent). This is what makes a ledger safe and reruns harmless.
- Each writes through the **Change-Op write repository** (`MembersConfigWriteRepository.apply_ops`),
  NEVER a raw `put_item` — so steering 39's write contract holds and a partial run cannot truncate
  a sibling slice or catalog.
- Each is **`--dry-run` by default / `--apply` to write** (the shape used for the incident fix), so
  every migration is previewable before it mutates PROD.
- Each proves the round-trip against REAL data (steering 39 "Change-with-tests + real data"), not a
  hand-built fixture.

### 2. A migration ledger (the checkpoint MySQL gives for free)
Record which migrations have run **per environment**. Candidate storage: a `migration#<id>`
sort-key row under a tenant-agnostic `_platform` partition in `governance_projection` (or a small
dedicated table). A tiny runner reads the ledger, runs PENDING migrations in order, records
completion (id, timestamp, applied-count). Then "has C7 run on PROD?" is a **query, not a guess**.

### 3. Wire the runner into the deploy pipeline (closes the exact gap)
Per steering 43 a merge to `main` IS a production deploy. Add a migration step to
`deploy-sam-members.yml` (OIDC → `NonprofitDeployRole`) that runs PENDING migrations against the
branch's resolved env AFTER the Lambda deploys. A reader-contract change and its data backfill then
ship together — the lockstep MySQL enforces, reproduced on the SAM plane. (Decide: fail the deploy
on migration error vs. alert; and ordering vs. the stack update.)

### 4. Make reader/writer contract changes defensive during the transition (belt-and-suspenders)
The deeper lesson: C7 made the reader HARD-IGNORE `choices` BEFORE the data was guaranteed migrated.
Safer transition = **expand → migrate → contract** (the online-schema-change discipline):
1. **Expand:** reader tolerates BOTH shapes for one release (`options or choices`).
2. **Migrate:** ship the backfill (items 1–3).
3. **Contract:** remove the legacy read in a LATER release.
Then even a missed migration degrades gracefully instead of 500-ing.

**Sequencing:** items 4 + 1 would have PREVENTED this incident outright; items 2 + 3 make it
systematic going forward.

## Scope / relations
- **Code:** `sam/<module>/migration/` (formalize), a new ledger + runner, `deploy-sam-members.yml`
  (and `deploy-sam-pretokengen.yml` if it ever grows data). `governance_projection` ledger row.
- **Steering:** add the migration convention to `39-backend-data-access-sam-dynamodb.md` (write
  contract already lives there) and the pipeline step to `43-cicd-deploys.md` (which today
  explicitly states "there is NO Terraform workflow" and "Infrastructure/data migration is manual"
  — this is the data-migration analogue of that gap).
- **Relates to:** the Flask `#database` migration runner (the plane this mirrors); spec
  `Members/02 - members-config-sam-owned-write-path` (its per-record TEST→PROD cutover is a manual
  precursor of exactly this); the "Secret & config management is inconsistent across planes"
  backlog item (same "promote TEST config/data to PROD" theme — that item notes a manual
  local→Railway copy of `members.*` rows was needed for the same class of reason).
- Own spec.
