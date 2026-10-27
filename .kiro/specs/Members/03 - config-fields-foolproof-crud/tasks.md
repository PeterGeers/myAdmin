# Tasks — Foolproof CRUD for `config#fields` (SAM plane)

- Status: **Draft** (tasks phase — build gated on approval of requirements + design). **No code until approved.**
- Follows `requirements.md` (R1–R11) and `design.md` (C1–C6, D1–D5). Incorporates the external design
  review (Must-fix #1–4 + Should-fixes) — see `design-review.md` §"External review".
- Ordering principle (root-cause lesson): the **E2E invariant harness lands FIRST** and stays red
  until the fix makes it green — proof precedes "done". Change-with-tests throughout (steering 34).
- Checkbox vocab: `[ ]` not started · `[x]` done · `❌` blocked. Each task names files + a verify step.
- **Decision gate before Phase 2:** ratify D3 (R7 option A inline-protected vs B separate record).
- **Delivery slices (review's phasing — each shippable; safety lands even if the frontend slips):**
  Slice 1 = Phase 0+1 + the row skeleton (2.0a) + migration (2.0); Slice 2 = Phase 2+3+4 (closes
  occurrence 3 server-side); Slice 3 = Phase 5 (frontend) + stale-SPA guard; Slice 4 = Phase 7 (retire
  whole-object); Slice 5 = Phase 6 (R7=B) only if needed. Phases 8–9 (enforcement + verify) ride with
  the slices they protect.

---

## Phase 0 — Decision + ADR + steering (no product code) — ~0.5 day
- [x] 0.1 **Ratify R7 (D3):** A (application attrs inline, protected by the narrow `set_field_application`
  Change-Op) vs B (separate `config#application_form` record). Record the choice + rationale.
- [x] 0.2 Write **ADR 0009** (`docs/decisions/0009-config-fields-crud-change-op-server-owned.md`,
  append-only): Change-Op / server-owned placement; store = nested delta; read = Flat_View; write
  merges onto the Resolved_Record; R7 decision from 0.1; links `root-cause-analysis.md` as the why.
- [x] 0.3 Extend steering **39** with the Change-Op / no-whole-record-replace rule + Merge_Target =
  Resolved_Record; update steering **38** to reference the new CRUD contract. (Docs only.)

## Phase 1 — E2E invariant harness FIRST (proof scaffold, red) — ~2 days  (R9)
- [x] 1.1 Local-DynamoDB pytest fixture (`sam/tests/e2e/conftest.py`): targets `amazon/dynamodb-local`
  (steering 42) via `AWS_ENDPOINT_URL_DYNAMODB` + a test projection table; skips cleanly when the
  container/endpoint is absent (so unit runs are unaffected). Seeds from the COMMITTED real fixture
  `sam/tests/fixtures/hdcn_config_fields_overlay.json` (already captured) using the seed-script pattern.
- [x] 1.2 Invariant engine `assert_change_op_isolated(before_resolved, op, after_resolved)`: diffs the
  FULL resolved record and asserts ONLY the op's named target changed; every other group/field/attr
  byte-identical. Generic over (reader, writer, record_id, op) so it's reusable (R9.4).
- [x] 1.3 **Truncation tripwire** test (the occurrence-3 scenario): a partial/empty groups payload MUST
  NOT reduce the catalog count; a partial fields payload MUST NOT reduce field count. Assert RED now
  against current `put_config` (proves the bug), to go green after Phase 2.
- [x] 1.4 Real-data round-trip cases (RED now): set a base field attr; add/edit/delete a variable
  field; edit a base group's order+label; set enum choices; set application attrs — each asserts
  isolation via 1.2 against the real h-dcn row. (These are the acceptance gate for Phase 2.)

## Phase 2 — Change-Op CRUD via `update_item` paths (corrected per design-review) — ~3.5 days  (R1/R2/R4/R6; C1/C2)
> See `design-review.md` — writes are `update_item` PATH expressions, not `put_item` replace.
- [x] 2.0a **Guarantee the row skeleton (review Must-fix #1 — C6):** create a new tenant's
  `config#fields` with `{fields:{}, overrides:{}, functional_groups:{}}` + a seeded `version`; the
  migration (2.0) backfills the skeleton + `version` onto legacy rows. Path `update_item` REQUIRES the
  parent maps to exist — `if_not_exists`-in-the-same-op does NOT work ("paths overlap"). This + 2.3's
  create-vs-update verb choice is the fix.
- [x] 2.0 **Migrate `functional_groups` LIST → MAP** keyed by group key (design-review Q3a/Q11): update
  the reader, raw-reader, and the empty contract (`[]`→`{}`) in ONE change; **dual-read both shapes
  until all code is deployed** (review Must-fix #4); re-home `order` into the entry (already there);
  migrate every fixture/test; one-time per-tenant whole-row write run through the invariant harness
  against a **copy of PROD** with a PITR restore point / backup taken FIRST. This is what makes the
  catalog truncation STRUCTURALLY impossible.
- [x] 2.1 **IAM:** add `dynamodb:UpdateItem` to `template.yaml` Sid
  `MembersWriteGovernanceProjectionConfig` (today PutItem-only, verified) — least-privilege, reviewed,
  plan-first (steering 43). NOTE: local DynamoDB does not enforce IAM, so this is proven only by the
  deployed-stage smoke test (8.6), not E2E.
- [x] 2.2 New domain service `ConfigFieldsCrudService` with DISJOINT identity-keyed ops (review
  Must-fix #3): `set_field` (DEFINITION attrs only — `{type,label,order,required,visible,choices,
  options,scope,functional_group}`, NO `application_*`); `set_field_application` (the four app attrs
  only); `reset_field` (`REMOVE overrides.<dotted>` → revert to base); `delete_field`; `set_group`;
  `delete_group` (R2.4). No boto3 (steering 35). Absent=untouched / `null`=remove semantics.
- [x] 2.3 Mechanics (design-review Q2/Q8 + review Must-fix #1): read resolved with **`ConsistentRead=True`**
  ONLY to validate + decide placement (`fields.<key>` variable / `overrides.<dotted>` base/calc /
  `functional_groups.<gkey>`); placement chooses the VERB by existence — CREATE a new entry with
  `SET #o.#k = :whole_entry` vs UPDATE an aspect with `SET #o.#k.#attr = :v` (NEVER `if_not_exists`
  parent-seed + child-set in one expression — DynamoDB rejects it). `ExpressionAttributeNames` for
  dotted keys.
- [x] 2.4 `MembersConfigWriteRepository.apply_ops(tenant_id, config_id, ops, base_version, client_op_id=None)`
  — ONE `update_item` with a combined SET/REMOVE expression; `ConditionExpression` with the THREE
  version cases (review Must-fix #2): `version = :base` / `attribute_not_exists(version)` (legacy row) /
  `attribute_not_exists(sk)` (no row). Multi-op ALL-OR-NOTHING; reject overlapping paths up front.
  Optional `client_op_id` idempotency. Closed-id + non-empty tenant guards retained; whole-row
  `put_item` only the C6 create/migration primitive (R1.5).
- [x] 2.5 **Base-group materialize** (R4.1): `set_group` on a base group absent from the overlay writes
  `SET functional_groups.#gkey = :g` (override entry) — all other groups physically untouched. **Catalog
  cannot truncate** (R4.2): no op writes the whole catalog. (Fixes occurrences 2 + 3, structurally.)
- [x] 2.6 Server-owned placement (R2.2): service decides `fields` vs `overrides` + dotted key via
  `fixed_fields.field_by_key`; client never supplies placement. Explicit deletes only (R2.5);
  delete-non-empty-group refused (R4.3). **`delete_field` safety (review Should-fix):** refuse a
  variable-field delete that would orphan member data / a group/application reference — offer
  `visible=false` (hide) instead; a base field "delete" is `reset_field` (revert), never removing a base
  definition (Q9).
- [x] 2.7 Edge: `PUT /members/config/fields` body becomes a **Change-Op list** (design-review Q7a) — one
  route, existing admin gate + tenant-from-token; the whole-overlay body is no longer accepted.
- [x] 2.8 Run Phase-1 cases → GREEN (incl. first-write onto the skeleton, create-vs-update verb,
  dotted-key paths, legacy-no-version branch, version-conflict). Unit tests for placement + delete
  guards + stale-version rejection + overlapping-ops rejection.

## Phase 3 — ENUM / SCOPE / REFERENCE correctness — ~1.5 days  (R5; C4)
- [x] 3.1 ENUM: preserve/strengthen the `options or choices` fallback (`_build_override`); a `set_field`
  choices change rewrites only choice data, preserving other attrs (R5.1/R5.5). Invariant case.
- [x] 3.2 SCOPE: `set_field` preserves `scope` verbatim; `config#scope` untouched by field/group ops;
  scope-dimension-backed choiceless enum still sources from `config#scope` (R5.2). Invariant case.
- [x] 3.3 REFERENCE: `membership_type` subset validates against the live catalog (dangling fail-loud),
  via the shared `application_choices` authority — public read + submit agree (R5.3/R5.4). Invariant case.

## Phase 4 — Concurrency hardening + conflict surfacing — ~0.5 day  (R6; C2)
> The conditional-write mechanism lands in Phase 2.4 (it's intrinsic to the `update_item` op). This
> phase is the remaining surfacing + test depth.
- [x] 4.1 Service maps `ConditionalCheckFailedException` → a caller-safe 409 (R6.2, no change made).
  **One-shot auto-retry WITH a guardrail (review Should-fix):** on a 409, re-read (ConsistentRead),
  re-validate, retry the op set ONCE — but only when the ops are non-overlapping + idempotent by
  identity; if the retry also conflicts, surface the 409 (never loop, never mask a real concurrent edit
  to the SAME path). (Shared-row contention under D3(A) is the trigger that would justify D3(B).)
- [x] 4.2 `client_op_id` idempotency: a lost-response retry carrying the same id that already produced
  the current `version` returns success, not a self-409 (review Should-fix).
- [x] 4.3 Tests: stale-writer (two clients, one base version — second rejected atomically); the
  one-shot-retry success + the retry-also-conflicts→409 path; first-write + legacy-no-version paths;
  the self-409 idempotency path.

## Phase 5 — Frontend: Change-Op writes + Flat_View reads — ~2.5 days  (R2/R3; C3)
- [x] 5.1 Configurator + application-form builder: call the Change-Op API by identity (set field/group/
  application attr); STOP reading `field_overlay` and STOP reconstructing storage keys. Read the Flat_View.
- [x] 5.2 Retire the overlay-model write path (`overlayModel` whole-object assembly, `resolveWriteTarget`
  dotted-key reconstruction) for config writes — the source of the drift.
- [x] 5.3 `get_field_config` stops surfacing `field_overlay` (steering 39 guard); confirm the Flat_View
  carries everything the UI needs (it does — verified in the captured response).
- [x] 5.3a **Stale-SPA-bundle guard (review Should-fix):** for a deprecation window, the server
  REJECTS a whole-object/`field_overlay` write body (a cached old bundle) with a clear "reload the app"
  error — not an obscure failure — so a user on a stale tab gets an intelligible prompt, not silent
  breakage.
- [x] 5.4 Frontend tests: no raw overlay shape sent/consumed; base-group edit persists via Change-Op;
  the blank-base-group-form + silent-no-op bugs are covered (fold in today's group-modal fixes here).

## Phase 6 — (ONLY IF R7 = B) separate application-form record + migration — ~2 days
- [x] 6.1 New `config#application_form` id (`projection_schema`), reader method, writable-set entry.
- [x] 6.2 Compose field defs + form selections at read (`get_public_field_config`), submit validator
  unchanged in behavior.
- [x] 6.3 Migration: lift inline `application_*` off `config#fields` → the new record per tenant; PROD
  as source; invariant-verify the lift. (Skip entirely if R7 = A.)

## Phase 7 — Remove the whole-object replace from the client path — ~1 day  (R1.5; the primary structural enforcement)
- [x] 7.1 Remove/forbid the client-reachable whole-object `config#fields` replace (R1.5 / R11.1); the
  repo `put_item` remains an internal primitive only the Change-Op service builds the item with. The
  write INTERFACE exposes only Change-Ops — the dangerous operation no longer exists to be misused.

## Phase 8 — MECHANICAL ENFORCEMENT (non-optional — so it can't recur) — ~1.5 days  (R11)
- [x] 8.1 **CI/pre-commit guard** (R11.2): committed `scripts/check_sam_config_crud.py` (modeled on the
  Flask DB-access guard) failing on (a) raw `put_item`/`update_item`/`delete_item` on the governance
  table outside the Change-Op write repository, and (b) a raw-shape key in an API response. Its own
  tests (planted violation fails; clean tree passes). Wire into `.githooks/pre-commit` + CI (steering
  43), report-only → blocking once baseline clean.
- [x] 8.2 **Gate the invariant E2E** (R11.3): wire the Phase-1 invariant suite into the REQUIRED gate
  (nightly full-suite at minimum; per-PR if the local-DynamoDB container is feasible). A test that is
  not gated is how the original regression reached `main` — this closes that.
- [x] 8.3 **Boundary/import test** (R11.4): extend `sam/tests/test_handler_repository_boundary.py` —
  assert no handler/domain imports the raw whole-record replace primitive; only the Change-Op service.
- [x] 8.4 **Runtime tripwire** (R11.5): the write repository refuses a `config#fields` whose resolved
  group/field count drops below base unless an explicit delete op was issued — last-line defense so a
  logic bug cannot silently truncate reaching DynamoDB. Test both directions (legit delete allowed;
  silent shrink refused).
- [x] 8.5 **Review detector consistency** (R11.6): confirm `prompt-code-quality.md` §4 foolproof-CRUD
  detectors (already added) match the 8.1 guard's patterns, so review and CI agree.
- [x] 8.6 **Deployed-stage smoke test (review harness gap):** local DynamoDB does NOT enforce IAM, so
  the `dynamodb:UpdateItem` grant (2.1) passes E2E and would only fail in AWS. Add a smoke test that
  runs a real Change-Op `update_item` against the TEST stack, so the IAM grant is actually exercised.
- [x] 8.7 **Harness gap cases (review R9 gaps):** add to the invariant suite — a randomized op-sequence
  run through `assert_change_op_isolated`; the LIST→MAP migration invariant; an orphaned-override case
  (a base field renamed/removed in code leaves a dangling tenant override → a harness/startup check
  surfaces it).

## Phase 9 — Verify live + docs — ~0.5 day
- [ ] 9.1 Full E2E invariant suite green (all op kinds + truncation tripwire); real h-dcn round-trip.
  Exercise live TEST (configurator: edit group order, add field, set choices — confirm NO truncation,
  confirm the write persists, confirm reload survives).
- [x] 9.2 Plant-a-violation check: a temp commit that adds a raw `put_item` on the governance table
  OUTSIDE the repo MUST fail the guard (8.1) AND the boundary test (8.3); revert it. Proves the
  enforcement actually blocks, not just exists.
- [x] 9.3 DoD (steering 40): ADR 0009 + steering 38/39 landed with the code; root-cause-analysis linked;
  the "do not edit groups on TEST" warning retired once the fix is verified live.

---

## Task Dependency Graph
```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2", "0.3"] },
    { "id": 1, "tasks": ["1.1", "1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4"] },
    { "id": 3, "tasks": ["2.0a", "2.0", "2.1"] },
    { "id": 4, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 5, "tasks": ["2.5", "2.6", "2.7"] },
    { "id": 6, "tasks": ["2.8", "3.1", "3.2", "3.3"] },
    { "id": 7, "tasks": ["4.1", "4.2", "4.3"] },
    { "id": 8, "tasks": ["5.1", "5.2", "5.3", "5.3a", "5.4"] },
    { "id": 9, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 10, "tasks": ["7.1"] },
    { "id": 11, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7"] },
    { "id": 12, "tasks": ["9.1", "9.2", "9.3"] }
  ]
}
```
Notes: Wave 0 (decision+ADR+steering) gates everything. Waves 1–2 build the RED invariant harness
BEFORE the fix. Waves 3–5 make it green (the service). Wave 6 concurrency. Wave 7 frontend. Wave 8 is
conditional on R7=B. Wave 9 removes the replace (structural enforcement). **Wave 10 is the MECHANICAL
enforcement (guard + gated test + boundary test + runtime tripwire + review-detector consistency) —
non-optional; it is what makes the fix survive future development.** Wave 11 verifies live (including
a planted-violation check that the guard actually blocks) + docs.

## Definition of Done (steering 40)
- Every Change-Op proven isolated against the REAL h-dcn row on local DynamoDB (R9); truncation
  tripwire green; no whole-record replace reachable from the client.
- Base definitions + the full `functional_groups` catalog survive every write (R1/R4).
- Enum/scope/reference handled, one shared choice authority (R5).
- Conditional write prevents lost updates (R6).
- Frontend writes by identity, reads the Flat_View, no raw shape crosses the boundary (R2/R3/39).
- ADR 0009 + steering 38/39 updated; root-cause-analysis linked; live TEST exercised (not just units).
- The reusable invariant harness is documented so `config#scope`/`config#mail`/member CRUD can adopt it.
- **Enforcement is MECHANICAL and proven (R11):** the whole-record replace does not exist in the
  client-reachable interface; the CI/pre-commit guard blocks a raw-write bypass + a raw-shape response
  (planted-violation test confirms it blocks); the invariant E2E is in the required gate; the
  boundary/import test and runtime truncation tripwire are green; the review prompt detects the same
  violations. The fix is structurally and mechanically unable to be reintroduced by future work.

## Notes
- **Why this spec exists:** `.kiro/specs/Members/root-cause-analysis.md` — the partial-overlay-
  overwrites-full-record defect, proven 3×. This spec makes correctness STRUCTURAL (Change-Op +
  merge-onto-resolved) and PROVEN (real-data E2E invariant), not best-effort.
- **Reusability:** the Change-Op + merge-onto-resolved + invariant-harness pattern is the template for
  all SAM-plane CRUD (steering 39). `config#fields` is the first and hardest case (base⊕overlay); the
  rest are simpler.
- **Today's group-modal fixes** (uncommitted: `MembersGroupModal`/`MembersGroupsTable`/`overlayModel`
  read-seed + materialize) fold into Phase 5 — they are the frontend half, and the write-side
  `editGroup` materialize must NOT ship before Phase 2's truncation fix (it exposes the truncation on
  PROD otherwise — see root-cause-analysis).
```
