# Task 7.2 — ADR 0003 + ADR 0005 consistency review (platform framing)

> **VERIFICATION / RECORD TASK** (R8.2, part of Task 7 — ADR + governance). Acceptance
> criterion R8.2: *"ADR 0003 (platform base) and ADR 0005 (MySQL system-of-record +
> projection) SHALL be REVIEWED for consistency with the platform framing."* This is the
> explicit record of that review. No product code, no Flask landing-module change — a
> documentation review only.

## Documents reviewed (read in full)

- `docs/decisions/0003-myadmin-is-platform-base-modules-as-sam-apps.md` — platform base;
  apps imported as SAM-backed modules on the module contract.
- `docs/decisions/0005-two-pool-identity-mysql-system-of-record-one-directional-projection.md`
  — MySQL system-of-record + one-directional MySQL→DynamoDB projection (single writer).
- `docs/decisions/0010-sam-public-pages-platform.md` — the ADR authored in Task 7.1 (the
  platform framing being checked against).

## Verdict

**CONSISTENT.** ADR 0003 and ADR 0005 do NOT contradict or drift from the platform framing in
ADR 0010. No amendment to 0003 or 0005 is warranted. ADR 0010's existing cross-links to 0003
and 0005 are accurate. No doc edit to any ADR was required; this review record is the outcome
artifact.

## Specific consistency points checked

### 1. 0010 "no shared DB — share the mechanism, not the store" vs 0003's module model — CONSISTENT

- **0003 establishes:** modules register in `MODULE_REGISTRY`; each module "scopes its data by
  `tenant_id`"; each domain keeps "its optimal stack" (the portal "stays serverless/DynamoDB
  rather than being dragged toward MySQL/Flask"); the two-plane design is deliberate.
- **0010 §3 / §5 says:** each producer "owns its data under its plane's own tenancy," "no
  producer reads another plane's store," and the ONLY cross-plane surface is the `_slugs/{slug}`
  S3 marker (an S3 control-plane object, never a shared DB) — steering 35 rule 5a.
- **Finding:** 0010's producers are the public-page face of a SAM-backed module, each scoping
  data by `tenant_id` on its own stack — a faithful EXTENSION of 0003's module model, not a
  contradiction. The marker shares a *mechanism* (slug namespace), never a store.

### 2. `public_prefix` riding the one-directional MySQL→DynamoDB projection READ-ONLY vs 0005's single-writer posture — CONSISTENT

- **0005 establishes (Decision, D3):** the projection is "write-only, single writer... makes
  zero MySQL writes. Data flows MySQL→DynamoDB only, never back"; items validated/versioned/
  idempotent; tenant-scoped by `tenant_id`; the module plane "reads only its own `tenant_id`
  partition and never writes the projection or MySQL"; "the `sam/` plane has no MySQL client at
  all."
- **0010 §5 + Consequences says:** `public_prefix` is "authored in MySQL on the tenant record
  and projected read-only onto the existing `tenant` row; SAM validates slugs against its own
  projected copy, never by calling Flask. No new table, no new projection mechanism, no second
  writer."
- **Finding:** an ADDITIVE attribute riding the EXISTING one-directional projection, introducing
  no second writer and no request-time Flask call — matches 0005's single-writer / one-directional
  invariant exactly. (Corroborated by spec requirements R2.2: additive field on the already-
  projected `tenant` row, `SK="tenant"`, NOT a new table or new projection mechanism.) No new
  writer against MySQL; no SAM→Flask request-time hop.

### 3. "Page-as-unit per plane" vs invariants 0003/0005 establish — CONSISTENT (no invariant violated)

- The invariant most at risk would be inventing a shared cross-plane registry/store (forbidden by
  0003's per-stack data ownership and 0005's no-writable-copy posture).
- **0010 §1 explicitly realizes page-as-unit PER PLANE:** SAM page identity lives on the SAM-owned
  `config#fields` row under `tenant_id`, with "no single shared page-registry database"; the only
  shared surface is the slug namespace via the S3 marker. The Flask landing plane keeps its 1:1
  shape UNTOUCHED (future producer, migrates in later).
- **Finding:** the framing UPHOLDS rather than violates both ADRs — no shared store is invented,
  no existing plane's store is disturbed.

## Cross-link accuracy (what 0010 already states about 0003 / 0005)

ADR 0010 already carries accurate cross-references, which this review confirms:

- Header `Relates to:` cites ADR 0003 ("this platform is the public-page face of a SAM module")
  and ADR 0005 ("the tenant `public_prefix` rides that projection, read-only, no new writer").
- `Related` section has a dedicated bullet for each, both annotated "reviewed for consistency with
  the platform framing (spec 14 task 7.2)" / "Reviewed for consistency (task 7.2)."

Both claims are correct against the source ADR text (points 1 and 2 above). The task-7.2 review
annotations 0010 already contains are therefore accurate — no correction needed.

## Disposition — no doc edit to 0003 / 0005 / 0010

- **0003 / 0005 NOT amended.** Their invariants are upheld by 0010; a one-line back-reference into
  0003/0005 pointing forward to 0010 was CONSIDERED and judged unnecessary — 0010 already links
  back to them, the ADR log reads forward (newer ADRs cite older), and adding forward-pointers to
  settled older ADRs would be churn for no coherence gain. Per the task: "do NOT rewrite 0003/0005
  wholesale; prefer a small clarifying cross-link or a note" — and here even the small cross-link
  is not warranted, because 0010's existing links already make the relationship explicit and
  accurate.
- **0010 NOT edited.** It already records the review (the task-7.2 annotations) and its cross-links
  are accurate; re-asserting the finding inside 0010 would duplicate this record.
- **This file IS the recorded outcome**, matching the spec-folder decision-record convention
  (`task-1.1-slug-marker-decision.md`, `task-2.1-page-shell-decision.md`).

---

**Reviewed 0003 + 0005 against the ADR 0010 platform framing; found CONSISTENT on all three
checked points; recorded here per R8.2.**
