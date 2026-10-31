# Member Scope Stale Projection & Pagination Undercount Bugfix Design

## Overview

One user action (widening a MEMBERS member user's `region` scope from a region to "all") exposes
two independent defects with two root causes on two planes. This design treats them as two bug
conditions under one spec because they share the triggering action, the confirmed evidence, and
the member-read surface.

- **Bug 1 — stale scope projection (propagation miss).** MySQL `user_tenant_scope` (source of
  truth, Flask/MySQL plane) correctly recorded `{"region": ["*"]}` at `updated_at`
  2026-10-28 13:22:18. The DynamoDB `governance_projection` `scopegrant#peter@pgeers.nl#region`
  row (SAM/DynamoDB plane) still reads `values = ["Utrecht"]` at version 2026-09-23T08:29:06.
  The on-change sync is best-effort and swallows exceptions
  (`user_tenant_scope_service._fire_enqueue_sync`), so a drain failure is silent; and the
  periodic reconcile (`ProjectionSync.sync_all`) is evidently not running, so nothing backstopped
  it for five weeks. The fix direction: make the on-change drain failure **observable/retried**
  instead of silently swallowed and/or ensure a periodic reconcile runs; the immediate
  operational unblock is a version-guarded `ProjectionSync.sync_administration('h-dcn')`.

- **Bug 2 — pagination undercount (Limit before scope filter).** The paged read passes the
  DynamoDB Query `Limit` to the RAW partition (`members_repository.list_members_page`) and only
  then narrows by `allowed_scopes` (`_membership_reads.list_members_page`). A page of N raw rows
  is scope-shrunk, so `page_size` stops meaning "returned in-scope rows". This is latent even
  with a correct scope; Bug 1 just made it visible. The fix direction: resolve scope into the
  Query (a `FilterExpression`) and/or page via `LastEvaluatedKey` until `limit` in-scope rows are
  collected, and/or skip the post-filter for an all-access (`["*"]`) caller.

The two fixes are independent and can land separately; the spec keeps them together so the paired
tests and the shared evidence stay in one place.

## Glossary

- **Bug_Condition (C)**: For Bug 1, a scope change newer in MySQL than the projection while the
  projected `scopegrant#` row still holds the old values. For Bug 2, a page request whose returned
  in-scope row count is below `min(page_size, total_in_scope)` purely because `Limit` was applied
  to the raw partition before the scope filter.
- **Property (P)**: For Bug 1, the projection ends at the widened values (version-guarded) and the
  drain failure is observable/retried. For Bug 2, `page_size` means returned in-scope rows.
- **Preservation**: Committed MySQL writes, already-in-sync peers, newer-wins version guarding,
  non-scope-grant projection rows (Bug 1); guaranteed-deny scopes, cursor tenant isolation,
  per-dimension AND rule, child-item exclusion, the non-paged `list_members` path (Bug 2).
- **source of truth**: MySQL `user_tenant_scope` (Flask/MySQL plane); tenant key `administration`.
- **projection**: DynamoDB `governance_projection` (SAM plane); tenant key `tenant_id`; the
  `scopegrant#<user>#<dimension>` record the SAM read edge resolves `allowed_scopes` from.
- **`_fire_enqueue_sync`**: `backend/src/services/user_tenant_scope_service.py` — fires the
  best-effort on-change projection sync after a scope write; today it catches and logs any
  exception and returns (R2.4 "never break the write").
- **`ProjectionSync`**: `backend/src/services/projection_sync.py` — the sole projection WRITER;
  `sync_administration(admin)` syncs one tenant, `sync_all()` sweeps every tenant,
  `_reconcile_scopegrants(admin, desired)` reconciles the `scopegrant#` SK space; every put is
  version-guarded (a lower/equal source version does not overwrite).
- **`list_members_page` (repository)**: `sam/members/repository/members_repository.py` — issues a
  single tenant-pinned Query; `limit` → Query `Limit`; `limit None` → one ~1 MB page ("Max").
- **`list_members_page` (domain)**: `sam/members/domain/_membership_reads.py` — narrows the raw
  page by `allowed_scopes`, enriches, and re-encodes the cursor.

## Bug Details

### Bug Condition — Bug 1 (stale scope projection)

The bug manifests when a scope change is committed in MySQL but the on-change projection drain
fails silently and no periodic reconcile runs, leaving the projected `scopegrant#` row at the old
values even though the source is strictly newer.

**Formal Specification:**
```
FUNCTION isBugCondition_projection(X)
  INPUT: X of type ScopeChange { tenant, user, dimension, old_values, new_values,
                                 mysql_updated_at, projected_version, projected_values }
  OUTPUT: boolean

  RETURN X.new_values != X.old_values
     AND X.mysql_updated_at > X.projected_version      // source strictly newer
     AND X.projected_values = X.old_values             // projection never advanced
END FUNCTION
```

### Bug Condition — Bug 2 (pagination undercount)

The bug manifests when a page request returns fewer in-scope rows than `min(page_size,
total_in_scope)` because `Limit` was applied to the raw partition before the scope filter while
more in-scope rows remain available.

**Formal Specification:**
```
FUNCTION isBugCondition_paging(X)
  INPUT: X of type PageRequest { tenant, allowed_scopes, page_size }
  OUTPUT: boolean

  RETURN NOT is_guaranteed_deny(X.allowed_scopes)
     AND more_in_scope_rows_available(X.tenant, X.allowed_scopes, X.page_size)
     AND returned_in_scope_count(F, X) < min(X.page_size, total_in_scope(X))
END FUNCTION
```

### Examples

- **Bug 1:** MySQL `peter@pgeers.nl` = `{"region":["*"]}` @ 2026-10-28 13:22:18;
  projection `scopegrant#peter@pgeers.nl#region` = `["Utrecht"]` @ 2026-09-23T08:29:06.
  Expected: projection reconciles to `["*"]`. Actual: stays `["Utrecht"]` for 5 weeks.
- **Bug 1 (preserved):** peers `ledenadministratie` / `webmaster` MySQL `["*"]` == projection
  `["*"]` → a reconcile is a no-op (unchanged).
- **Bug 2:** scope-narrowed caller asks `page_size=50`, gets 5 rows; `100`→9; `250`→20;
  `Max`→105 (the whole old-scope count). Expected: up to `page_size` in-scope rows per page.
- **Bug 2 (all-access):** `["*"]` caller asks `page_size=50` → expected up to 50 member rows;
  today still post-filtered row-by-row and can under-return when a raw page holds child items.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors — Bug 1:**
- A committed MySQL scope write stays committed even if projection propagation fails (the write is
  never rolled back for a propagation error).
- Already-in-sync users (`ledenadministratie`, `webmaster`) keep their `scopegrant#` rows — a
  reconcile is a no-op for them.
- Version guarding: a stored projection row NEWER than the source is never overwritten by a staler
  source value.
- `config#*`, `module#*`, and other dimensions' grants are untouched by this fix.

**Unchanged Behaviors — Bug 2:**
- A guaranteed-deny scope (empty map or `[]` dimension) returns `([], None)` without paging.
- Cursor tenant isolation: a tampered/stale cursor naming another tenant raises and never
  resumes there.
- The per-dimension AND scope rule, calculated-field enrichment, and child-item exclusion are
  unchanged.
- The non-paged `list_members` read path and all other members reads are unchanged.

**Scope:**
Inputs that do NOT satisfy either bug condition must be completely unaffected:
- Bug 1: already-consistent users, newer-projection-than-source rows, non-scope-grant records,
  the MySQL write itself.
- Bug 2: guaranteed-deny callers, cursor-isolation checks, the non-paged read, other reads.

## Hypothesized Root Cause

**Bug 1 — propagation miss (two cooperating causes):**
1. **Silent on-change drain failure.** `user_tenant_scope_service._fire_enqueue_sync` wraps
   `_enqueue_sync` in a broad `except Exception` that logs a warning and returns. By design it
   must not break the write (R2.4), but the failure is not surfaced to any alert or retried, so a
   propagation miss is invisible in production.
2. **Reconcile backstop not running.** `ProjectionSync.sync_all` is the intended periodic
   backstop; a 5-week-old staleness proves it did not run (or did not cover this tenant). The
   version-guarded conditional put would have superseded the 2026-09-23 row given the 2026-10-28
   source, so the write path itself is correct — only the trigger/backstop is missing.

**Bug 2 — Limit applied before scope filter.** `members_repository.list_members_page` sets the
Query `Limit` to `page_size` and returns one raw page; `_membership_reads.list_members_page` then
narrows by `allowed_scopes`. Because the `Limit` bounds RAW rows, a scope-narrowed (or
child-item-containing) page yields fewer in-scope rows than `page_size`. The docstrings currently
describe this as "the honest DynamoDB-native page", but the product requirement (R25) is that
`page_size` means returned in-scope rows, so the current behavior is a defect, not a contract.

## Correctness Properties

Property 1: Bug Condition — Stale scope projection is propagated / reconciled

_For any_ scope change where the bug condition holds (isBugCondition_projection returns true: the
MySQL source is strictly newer than the projection yet the projected `scopegrant#` row still holds
the old values), the fixed system SHALL end with the projected `values` equal to the new source
values (version-guarded, newer-wins) and SHALL make an on-change drain failure observable or
retried rather than silently swallowed.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation — Already-consistent projection state is unchanged

_For any_ input where the bug condition does NOT hold (isBugCondition_projection returns false),
the fixed system SHALL produce the same projection state as the original, preserving: a committed
MySQL write survives a propagation failure, already-in-sync peers are untouched, a newer stored
projection is not clobbered by a staler source, and non-scope-grant records are unaffected.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

Property 3: Bug Condition — page_size means returned in-scope rows

_For any_ page request where the bug condition holds (isBugCondition_paging returns true: more
in-scope rows are available yet the returned in-scope count is below `min(page_size,
total_in_scope)`), the fixed `list_members_page` SHALL return `min(page_size, total_in_scope)`
in-scope, tenant-isolated rows for the page.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

Property 4: Preservation — Deny, isolation, and non-paged behavior are unchanged

_For any_ page request where the bug condition does NOT hold (isBugCondition_paging returns
false), the fixed `list_members_page` SHALL produce the same result as the original, preserving:
guaranteed-deny `([], None)`, cursor tenant-isolation raises, the per-dimension AND rule, child-
item exclusion, and the non-paged `list_members` path.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

## Fix Implementation

### Immediate / operational unblock (NOT the code fix — note only)

Run a version-guarded reconcile for the affected tenant to rewrite the stale row to `["*"]`:
`ProjectionSync.sync_administration('h-dcn')`. It is idempotent and version-guarded, so it is safe
and leaves already-consistent users untouched. This unblocks the user but does NOT prevent
recurrence — the durable fixes below do.

### Durable fix 1 — observable/retried propagation + reliable reconcile (spans both planes)

**Files:**
- `backend/src/services/user_tenant_scope_service.py` (`_fire_enqueue_sync` / `_enqueue_sync`) —
  Flask/MySQL plane trigger.
- `backend/src/services/projection_sync.py` (`sync_all` / `sync_administration` /
  `_reconcile_scopegrants`) — the sole projection WRITER (SAM-plane target).

**Changes required:**
1. **Surface the drain failure.** Keep the write decoupled (R2.4 — never break the write), but
   make an `enqueue_sync` failure observable: elevate from a swallowed warning to a surfaced/
   retried outcome (e.g. a metric/alert signal and/or a bounded retry), so a propagation miss is
   not invisible.
2. **Ensure a periodic reconcile runs** (`ProjectionSync.sync_all`) so a missed on-change drain is
   backstopped within a bounded window instead of surviving for weeks. Keep every put
   version-guarded via `_reconcile_scopegrants` (newer-wins; a staler source never clobbers).
3. Preserve the existing decoupling contract: the MySQL write commits regardless of propagation
   outcome.

### Durable fix 2 — resolve scope into the paged read (SAM plane)

**Files:**
- `sam/members/repository/members_repository.py` (`list_members_page` — `MembersRepository` and
  `DynamoDbMembersRepository`).
- `sam/members/domain/_membership_reads.py` (`list_members_page`).

**Changes required:**
1. Make `page_size` mean **returned in-scope rows**: either push scope into the Query as a
   `FilterExpression` and page via `LastEvaluatedKey` until `limit` in-scope rows are collected,
   OR, for an all-access (`["*"]`) caller, skip the post-filter so the raw member page is returned
   directly (still excluding non-member child items).
2. Keep tenant isolation at the partition key and keep returning an honest next-page cursor so
   prev/next paging stays correct across the (possibly multi-Query) page assembly.
3. Keep the guaranteed-deny short-circuit (`([], None)` without paging the repository) and the
   per-dimension AND scope rule and enrichment unchanged.

## Testing Strategy

### Validation Approach

Two-phase, per bug: first surface counterexamples on the UNFIXED code (exploration), then verify
the fix works and preserves existing behavior. Follow the change-with-tests contract — update the
allocated tests in the same change. Paired/allocated tests:
- Bug 1: `backend/tests/unit/test_projection_sync.py` (extend near the `_reconcile_scopegrants`
  coverage and the `sync_administration`/`sync_all` tests) and
  `backend/tests/unit/test_user_tenant_scope_service.py` (for the enqueue-drain-failure behavior).
- Bug 2: `sam/tests/test_members_read_dispatch.py` and `sam/tests/test_members_repository.py`
  (the repository paging test).

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate each bug on UNFIXED code, confirming the root
cause. If a test unexpectedly passes, re-hypothesize.

**Test Plan**:
- **Bug 1:** With a projection row older than the source (projected `["Utrecht"]` @ 2026-09-23 vs
  source `["*"]` @ 2026-10-28) and the on-change drain forced to fail, assert the projection ends
  at `["*"]` and the drain failure is surfaced/retried. On unfixed code the drain failure is
  swallowed and (absent a reconcile) the projection stays `["Utrecht"]` → FAIL.
- **Bug 2:** With an all-access caller and a partition holding more in-scope rows than
  `page_size`, assert `list_members_page(page_size=50)` returns up to 50 in-scope rows. On unfixed
  code the raw `Limit`-then-filter path under-returns when a raw page holds child items / when
  scope narrows → FAIL.

**Test Cases**:
1. **Stale scopegrant reconcile** — source newer than projection, projected old values; after
   reconcile the row supersedes to `["*"]` (will fail on unfixed code if the drain is the only
   trigger and it failed).
2. **Enqueue drain failure surfaced** — a forced `enqueue_sync` failure is observable/retried, not
   silently swallowed (will fail on unfixed code — `_fire_enqueue_sync` logs and returns).
3. **All-access page fill** — `["*"]` caller, `page_size=50`, ≥50 in-scope rows available →
   expect 50 returned (may fail on unfixed code when the raw page includes child items / fewer
   in-scope rows survive the post-filter).

**Expected Counterexamples**:
- Bug 1: projection remains `["Utrecht"]`; the drain failure leaves no surfaced/retried signal.
- Bug 2: returned in-scope count < `min(page_size, total_in_scope)` for a scope-narrowed/
  child-item-containing page.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed behavior produces the expected
result.

**Pseudocode:**
```
FOR ALL X WHERE isBugCondition_projection(X) DO
  run_propagation_or_reconcile'(X.tenant)
  ASSERT projected_values_after(X) = X.new_values AND drain_failure_observable_or_retried(X)
END FOR

FOR ALL X WHERE isBugCondition_paging(X) DO
  rows, cursor := list_members_page'(X.tenant, X.allowed_scopes, X.page_size)
  ASSERT count(rows) = min(X.page_size, total_in_scope(X)) AND all_in_scope(rows) AND tenant_isolated(rows)
END FOR
```

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed behavior equals the
original.

**Pseudocode:**
```
FOR ALL X WHERE NOT isBugCondition_projection(X) DO
  ASSERT projection_state(F, X) = projection_state(F', X)
END FOR

FOR ALL X WHERE NOT isBugCondition_paging(X) DO
  ASSERT list_members_page(F, X) = list_members_page(F', X)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation because preservation
is a universal claim over the non-buggy input domain; it generates many cases and catches edge
cases a handful of unit tests would miss. Observe behavior on UNFIXED code first, then encode it.

**Test Plan**: On unfixed code, observe: already-in-sync peers unchanged by a reconcile; a newer
projection not clobbered by a staler source; a committed MySQL write surviving a propagation
failure; guaranteed-deny `([], None)`; cursor-isolation raises; the non-paged `list_members`
result. Encode those as preservation tests.

**Test Cases**:
1. **In-sync peer preserved** — a reconcile is a no-op for `ledenadministratie`/`webmaster`.
2. **Newer-wins preserved** — a staler source does not overwrite a newer projection row.
3. **Write-survives-propagation-failure** — the MySQL scope write stays committed when the drain
   fails.
4. **Deny / isolation / non-paged preserved** — guaranteed-deny returns `([], None)`; a tampered
   cursor raises; `list_members` is unchanged.

### Unit Tests

- Bug 1: reconcile writes the superseding `scopegrant#` row; drain-failure surfaced/retried;
  version guard rejects a staler source.
- Bug 2: `list_members_page` returns up to `page_size` in-scope rows for all-access and
  scope-narrowed callers; guaranteed-deny short-circuit; child-item exclusion.

### Property-Based Tests

- Bug 1 (Property 2): across random in-sync / newer-projection / non-scope-grant inputs, projection
  state is unchanged by the fix.
- Bug 2 (Property 4): across random scopes, page sizes, and partitions, deny/isolation/AND-rule/
  child-exclusion behavior is unchanged; and (Property 3) returned in-scope count equals
  `min(page_size, total_in_scope)`.

### Integration Tests

- Bug 1: a Flask scope write whose drain fails is backstopped by a reconcile so the SAM read edge
  resolves `["*"]`.
- Bug 2: the SAM read dispatch returns a full `page_size` page of in-scope rows end-to-end, with
  prev/next cursor paging intact.
