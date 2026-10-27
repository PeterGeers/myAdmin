# Design Review — pressure-testing the foolproof-CRUD mechanism (spec 03)

> **`design.md` is the authoritative design and is now fully consistent with this review's
> conclusions — you do NOT need to reconcile the two.** This file is the AUDIT TRAIL: the
> mechanism-level questions, the verified facts behind each answer, and WHY the mechanism was chosen
> (`update_item` paths, groups-as-map, the IAM change, the version-conditional). Read it for the
> "why" and the evidence; read `design.md` for the design itself.

- Status: **Review record.** Written because a single basic question ("what's the value of upsert if
  it deletes unlisted data?") changed the design — which meant the design was at the right *principle*
  but had not been pressure-tested down to the *mechanism*. That is the exact failure mode the
  root-cause analysis names (specs written at principle level, bug lives in the unexamined mechanism).
  This document pressure-tests every mechanism-level assumption, with VERIFIED facts (file:line), so
  the next basic question finds its answer already here.
- Method: a skeptical reviewer's questions, each answered from the live code (verified 2026-10-26),
  each resolved into a design decision. Facts that CONTRADICT my earlier recommendations are flagged.

---

## Q1 — What is the actual write primitive? Is "upsert" meaningful?
**Verified:** `MembersConfigWriteRepository.put_config` (`projection_config_write_repository.py:117-139`)
does ONE thing: `put_item(Item={**attributes, **key, version})` — a **full-row REPLACE**. `update_item`
is used NOWHERE in `sam/members/repository/`. The frontend `upsertField` is a JS-object upsert; the
*storage* op underneath is replace-whole.
**Decision:** "upsert" is a misnomer here and carries no safety value — the write deletes any attribute
not in the object sent. The design must stop describing the write as an upsert/merge and name the real
verb. See Q2.

## Q2 — Should writes be `update_item` path expressions instead of `put_item` replace?
**Verified (corrects my earlier recommendation):**
- `fields` IS a map keyed by bare field key; `overrides` IS a map keyed by dotted `{group}.{key}`
  (fixture + reader). So `SET fields.#k.attr = :v` / `SET overrides.#dotted.attr = :v` path updates ARE
  mechanically viable for those two — **but** the dotted override key contains `.`, so the key segment
  MUST be bound via `ExpressionAttributeNames` (`#dotted`), never inline, or DynamoDB parses the dot as
  a nested path. Creating a new key needs the parent map seeded (`SET fields = if_not_exists(fields, :empty)`).
- **IAM does NOT allow it today.** `template.yaml` Sid `MembersWriteGovernanceProjectionConfig`
  grants `dynamodb:PutItem` ONLY (explicit comment: "No UpdateItem/DeleteItem/BatchWriteItem"). An
  `update_item` design REQUIRES adding `dynamodb:UpdateItem` to that statement — a reviewed Terraform/
  template change.
- `functional_groups` is an ordered **LIST**, not a map (verified in the real fixture + reader). Path-
  level `update_item` on a list is index-fragile; it does NOT work cleanly.
**Decision:** `update_item` by path is the *mechanically strongest* write for `fields`/`overrides`
(it never writes what it doesn't name, so it CAN'T truncate — stronger than read-merge-put, which is
"safe only if the merge is perfect"). BUT it is NOT free: it needs (a) an IAM grant change, (b)
`ExpressionAttributeNames` for dotted keys + parent seeding, (c) a storage decision for
`functional_groups` (Q3). The design adopts `update_item` for `fields`/`overrides` Change-Ops, and
resolves `functional_groups` separately (Q3). My earlier "just use update_item" was under-specified on
all three counts — corrected here.

## Q3 — How is `functional_groups` written without truncation, given it's a LIST?
**Verified:** stored as an ordered LIST `[{key,label,order}, …]`; the reader does
`for g in raw_groups` and the empty contract is `[]`. "Model it as a map keyed by key" (my earlier
suggestion) is a **storage migration** (list→map), touching the reader, the raw-reader, the empty-is-`[]`
contract, and re-homing `order` into the entry — NOT a drop-in.
**Options, honestly:**
- **(3a) Migrate `functional_groups` to a MAP keyed by group key** (`{personal: {label,order}, …}`).
  Then group Change-Ops become `SET functional_groups.#gkey = :g` / `REMOVE functional_groups.#gkey`
  — truncation-proof, same per-path model as fields/overrides. Cost: migrate reader + raw-reader +
  empty contract (now `{}`) + every test/fixture in ONE change; `order` already lives in the entry, so
  that part is clean.
- **(3b) Keep the LIST, mutate it via read-modify-CONDITIONAL-write** (version-guarded put of the whole
  list), plus the runtime truncation tripwire (R11.5) as the backstop.
**Decision:** prefer **(3a) migrate to a map** — it makes the catalog truncation STRUCTURALLY
impossible (same guarantee as fields/overrides), which is the whole point of the spec; occurrence-3 was
a list-truncation. (3b) keeps a residual "safe only if the read-modify-write is perfect" risk — the
exact thing we're eliminating. The migration is small (6 groups, tiny data, PITR + backup in place)
and is a Phase-1 task, gated by the invariant test. This is a STORAGE-SHAPE decision and belongs in
ADR 0009.

## Q4 — Concurrency: is there any lost-update protection today?
**Verified:** `VERSION_ATTR = "version"` is stamped on every put, but there is **NO `ConditionExpression`
on the config write** — it is last-writer-wins. Conditional-write machinery exists elsewhere (members
table idempotency puts) but is NOT applied to `config#fields`.
**Decision:** a concurrent edit silently clobbering another is a latent corruption vector. The design
adds an optimistic-concurrency guard: the write carries the version it read; the repository does a
**conditional** write (`ConditionExpression` on `version` = base, or `attribute_not_exists` for first
write). Stale base → caller-safe 409, NO partial change. This pairs naturally with `update_item`
(Q2). (R6 already requires this; this confirms it's net-new, not present.)

## Q5 — Doesn't the existing service-side merge (`_merge_fields_slices`) already solve it?
**Verified:** yes, `ConfigWriteService._merge_fields_slices` already does a read-modify-write per-key
merge on top of `put_item`, specifically to stop a partial body wiping slices. So the current model is
"whole-body PUT on the wire, per-key merge server-side, full-row put to storage."
**Honest assessment:** this is a *mitigation*, not the structural fix. It is "safe only if the merge is
perfect" — and occurrence-3 proved it isn't: `functional_groups` is "replace-if-non-empty", so a
partial non-empty groups list STILL truncates; and a stale cached read in the merge can lose a
concurrent change. The design REPLACES "merge-then-put-whole" with "update_item by path" (Q2) +
version-conditional (Q4) + groups-as-map (Q3), so correctness stops depending on a flawless in-memory
merge. **This is the key upgrade your question surfaced: not a better merge, the right verb.**

## Q6 — Who else writes the governance table? Can a bypass exist?
**Verified:** `MembersConfigWriteRepository.put_config` is the SOLE writer to governance_projection in
`sam/`. All other `put_item`s target the MEMBERS table. The Flask `ProjectionSync` plane owns the
non-SAM rows (split-ownership, outside `sam/`).
**Decision:** the single-writer fact is what makes the enforcement guard (R11.2) tractable: the guard
allow-lists exactly this one repository file for governance-table writes; any other `put_item`/
`update_item` on that table is a bypass → fail the build. Confirms the enforcement design is sound.

## Q7 — Does the Change-Op API slot into the existing edge, or need a new route?
**Verified:** today `PUT /members/config/{configId}` (admin-gated) passes the WHOLE body to
`put_config`. A Change-Op API is finer-grained than "whole config body".
**Options:**
- **(7a)** Keep `PUT /members/config/fields` but change the BODY contract from "whole overlay" to "a
  list of Change-Ops" (`{ops: [{op:"set_field", key, attrs}, …]}`); the edge stays one route.
- **(7b)** Add sub-routes (`PUT /members/config/fields/field/{key}`, `/group/{key}`, etc.).
**Decision:** **(7a)** — one route, body carries Change-Ops. Less routing surface, keeps the existing
admin gate + tenant-from-token wiring, and the whole-overlay body is simply no longer an accepted
shape (R1.5: the dangerous "replace whole" body is removed). Sub-routes (7b) add surface without
benefit here. The edge change is: `_write_body` → a Change-Op list the service applies.

## Q8 — What does "merge onto the Resolved_Record" mean, byte-for-byte, with update_item?
**Refined by Q2:** with `update_item` by path, there is NO "merge onto resolved" at write time — the op
addresses ONE path (`SET fields.motor_brand.functional_group = :g`) and DynamoDB leaves every other
attribute physically untouched. The "resolved record" matters for two things only: (1) VALIDATION
(is this field a base field → does it go in `overrides`; is the subset ⊆ resolved choices) and (2)
computing the dotted placement key. The write itself is a single named path, not a whole-object merge.
**Decision:** state this precisely in the design — "server resolves to decide placement + validate,
then issues a single path `update_item`; it does NOT read-merge-write the whole record." This removes
the last "safe only if merge is perfect" dependency.

## Q9 — Deletes: how, without ambiguity?
**Decision:** an explicit Change-Op → `REMOVE fields.#k` / `REMOVE overrides.#dotted` /
`REMOVE functional_groups.#gkey` (post-Q3a). Never inferred from omission (R2.5). A base field is
never REMOVEd (it lives in code) — "deleting" a base-field override is `REMOVE overrides.#dotted`
(reverts to base), which is correct. Delete-non-empty-group stays guarded.

## Q10 — First-write / empty-parent seeding?
**Verified:** a brand-new tenant has no `config#fields` row; a path `SET fields.#k...` fails if the
`fields` map (or the item) doesn't exist.
**Decision:** the repository seeds with `SET #attr = if_not_exists(#attr, :empty_map)` for parent maps,
and uses `attribute_not_exists(sk)` as the first-write condition path. Covered by an invariant test
case (first write onto a never-authored tenant).

## Q11 — Migration & rollback for the groups-as-map change (Q3a)?
**Decision:** a one-time migration converts each tenant's `functional_groups` LIST → MAP, reader +
raw-reader + empty contract updated in the SAME change, verified by the invariant harness against the
real h-dcn row; PROD as source; PITR + on-demand backup already in place. Atomic per tenant
(conditional put). Rollback = restore from PITR/backup (the catalog is tiny).

---

## Net changes to the spec from this review
1. **Verb:** Change-Ops use `update_item` path expressions (not `put_item` replace, not read-merge-put).
   → requirements R1/R2 reworded; design C1/C2 rewritten; **ADR 0009** records "update_item by path".
2. **IAM:** add `dynamodb:UpdateItem` to `template.yaml` Sid `MembersWriteGovernanceProjectionConfig`
   (reviewed, least-privilege) — a NEW task.
3. **`functional_groups` → MAP keyed by key** (storage migration) so the catalog gets the same
   truncation-proof per-path updates — a NEW Phase-1 task + ADR 0009 entry + migration (Q11).
4. **Conditional write on `version`** confirmed net-new (Q4) — keep R6, note it's absent today.
5. **ExpressionAttributeNames for dotted override keys + parent seeding** (Q2/Q10) — design detail +
   invariant cases.
6. **Edge:** body contract becomes a Change-Op list on the existing route (Q7a) — design C3 refined.
7. **"Merge onto resolved" reframed** (Q8): resolve to VALIDATE + place, then single path update — not
   a whole-record merge. Removes the residual "safe only if merge perfect" risk.

## Meta-lesson (for the root-cause file / way of working)
A design that shifts under the first basic question was not finished being reviewed. The fix is not to
celebrate the improvement but to pressure-test the REST of the design the same way — which this
document does. Mechanism-level questions (which verb? which IAM? what's the real stored shape? is there
concurrency control?) must be answered IN THE DESIGN before build, with verified facts, not discovered
live. This review is now that gate for spec 03.


---

## External review (second, independent pass) — incorporated

A second reviewer approved the direction and found issues my own pressure-test (above) missed —
including a FIRST-WRITE-BREAKING bug. All are now folded into `design.md`/`tasks.md`. Recorded here as
the trail.

**Must-fix (correctness / coherence):**
1. **`if_not_exists` seeding does NOT work.** DynamoDB rejects seeding a parent and setting a child
   path in one expression ("Two document paths overlap") and rejects `SET a.b.c` when `a.b` is absent.
   → Fixed: guarantee the row skeleton at create + migration (C6), and placement chooses CREATE-entry
   (`SET #o.#k = :whole_map`) vs UPDATE-aspect (`SET #o.#k.#attr = :v`). **This would have failed on
   the first override / first variable field / first group on a fresh row** — the showstopper my
   design-review missed.
2. **Legacy rows may have no `version`** → `version = :base` fails on a missing attribute. Fixed:
   migration backfills `version`; the condition has an `attribute_not_exists(version)` branch (C1 step 4).
3. **`set_field` and `set_field_application` overlapped** (names `visible`/`required`/`choices` collide;
   listing `application_*` inside `set_field` defeated D3(A)'s narrow-surface argument). Fixed: the two
   ops are disjoint — `set_field` = definition only, `set_field_application` = the four app attrs only.
4. **The LIST→MAP migration is itself a whole-row write** + readers must handle both shapes during
   rollout. Fixed: run it through the harness against a PROD COPY with a PITR/backup restore point
   first (C6); the migration is in Slice 1.

**Should-fix (adopted):** `ConsistentRead=True` on the validate-and-place read (avoid spurious 409s);
one-shot auto-retry on 409 **with a guardrail** (only non-overlapping/idempotent ops; surface the
conflict if the retry also fails — do not loop or mask a real concurrent edit); multi-op all-or-nothing
with up-front overlap rejection; absent = untouched / `null` = remove semantics; a `reset_field` op;
`delete_field` usage-safety guard (refuse if it would orphan member data; prefer hide); orphaned-override
check when a base field is renamed/removed in code; `client_op_id` idempotency for lost-response retries;
a stale-SPA-bundle deprecation rejection at rollout.

**Harness gaps (adopted into C5/R9):** a DEPLOYED-STAGE smoke test (local DynamoDB does NOT enforce
IAM, so the missing `UpdateItem` grant passes E2E and only fails in AWS); a stale-writer test; a
randomized op-sequence invariant run; a migration (LIST→MAP) invariant test.

**Doc hygiene:** the header said R1–R10 but the body cited R11 → corrected to R1–R11.

**Phasing (adopted):** shippable slices 1–5 (harness+skeleton+migration → ops+version guard → frontend
→ retire whole-object → R7(B) if needed); slices 1–2 deliver the safety even if the frontend slips.

**One nuance held, not blindly applied:** the reviewer's "auto-retry once on 409" is adopted WITH a
guardrail (non-overlapping/idempotent only; surface on second failure). The reviewer's own "row-level
version is coarse under a shared row" point is, quietly, an argument for D3(B) — recorded as the
trigger that would justify the separate application-form record.

**Meta:** this second independent review caught a first-write-breaking bug my single pressure-test
missed. The lesson (consistent with `root-cause-analysis.md`): one review pass is not enough — a design
should survive SEVERAL skeptical passes before build, and "a review changed the design" is the system
working, expected until the design has been hammered.
