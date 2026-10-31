# Bugfix Requirements Document

## Introduction

A single user action — editing a MEMBERS member user's `region` scope from a specific region
("Utrecht") to "all" (`["*"]`) — produces two observable defects for tenant `h-dcn`, user
`peter@pgeers.nl`, module `MEMBERS`, dimension `region`:

- **Symptom 1 — stale scope projection.** The widened scope has no effect: the member list
  stays filtered to the old narrow region. The Flask save landed in MySQL (source of truth) but
  the DynamoDB governance projection the SAM read edge consumes was never updated.
- **Symptom 2 — pagination undercount.** Rows-per-page returns roughly 10x too few rows, and the
  "Max" option returns exactly the OLD scope's member count: 50→5, 100→9, 250→20, Max→105
  (105 = the pre-change Utrecht member count).

Although one user action surfaces both, they have **two distinct root causes on two different
planes**, and this spec fixes each as its own bug condition:

- **Bug 1 (propagation miss, spans both planes).** The on-change projection sync is best-effort
  and swallows exceptions (`backend/src/services/user_tenant_scope_service.py::_fire_enqueue_sync`
  on the Flask/MySQL plane), so a drain failure is silent; and the periodic reconciliation
  backstop (`ProjectionSync.sync_all`) is evidently not running (a 5-week-old staleness
  survived). Result: the SAM-plane `governance_projection` `scopegrant#` row stays stale.
- **Bug 2 (latent paging defect, SAM plane).** The paged member read applies the DynamoDB Query
  `Limit` to the RAW partition BEFORE the domain-layer scope filter
  (`sam/members/repository/members_repository.py::list_members_page` passes `Limit`; then
  `sam/members/domain/_membership_reads.py::list_members_page` narrows by `allowed_scopes`), so a
  page of N raw rows is scope-shrunk and `page_size` no longer means "returned in-scope rows".
  This is latent even with a correct scope; it only became visible because of Bug 1.

### Confirmed evidence (real production data, read-only — see `.kiro/specs/myBacklog/findings.md`)

- MySQL `user_tenant_scope` (source of truth, h-dcn / MEMBERS): `peter@pgeers.nl` →
  `{"region": ["*"]}`, `updated_at` **2026-10-28 13:22:18** — the Flask save DID land.
- DynamoDB `governance_projection` (tenant_id=h-dcn):
  `scopegrant#peter@pgeers.nl#region` → `values = ["Utrecht"]`, version
  **2026-09-23T08:29:06** — **STALE**.
- Peers (`ledenadministratie`, `webmaster`) are MySQL `["*"]` == projected `["*"]` (in sync),
  so this is a **per-change propagation miss**, not a structural projector bug.
- The advanced MySQL `updated_at` (2026-10-28) is newer than the stale projection version
  (2026-09-23), so the version-guarded conditional put WOULD supersede the stale row **if the
  sync ran** — confirming the drain failed silently AND the periodic reconcile is not running.

### Plane constraints the fix MUST honor

- **Bug 1 write/trigger** is Flask/MySQL plane (steering 30/31): the scope write goes through
  the service layer and fires `enqueue_sync`; the projection writer (`ProjectionSync`) is the
  sole writer and version-guards every put.
- **Bug 1 projection + Bug 2** are SAM/DynamoDB plane (steering 35/39): tenant key is
  `tenant_id`; isolation is enforced at the partition key; the read edge resolves
  `allowed_scopes` from the `scopegrant#` projection.
- **Idempotent, version-guarded writes stay version-guarded.** A reconcile must never clobber a
  newer stored row with a staler source.

## Bug Analysis

This spec covers two bugs. Clause numbering: sections 1/2/3 belong to **Bug 1 (stale scope
projection)**; sections 4/5/6 belong to **Bug 2 (pagination undercount)**.

### Current Behavior (Defect)

#### Bug 1 — stale scope projection (propagation miss)

1.1 WHEN a member user's `region` scope is changed in Flask from a specific region to "all"
    (`["*"]`) and the on-change `enqueue_sync` drain fails THEN the system swallows the failure
    silently (`_fire_enqueue_sync` logs a warning and returns), so the DynamoDB
    `governance_projection` `scopegrant#<user>#region` row is NOT updated and stays at the old
    narrow value (`["Utrecht"]`)
1.2 WHEN the on-change drain has failed and time passes THEN no periodic reconciliation
    (`ProjectionSync.sync_all`) rewrites the stale row, so a stale projection can survive
    indefinitely (confirmed: 5 weeks, 2026-09-23 → 2026-10-28)
1.3 WHEN the SAM read edge subsequently resolves `allowed_scopes` for that user THEN it reads the
    stale `["Utrecht"]` grant and filters the member list to the old region, so the widened "all"
    scope has no observable effect

#### Bug 2 — pagination undercount (Limit before scope filter)

4.1 WHEN a scope-narrowed caller requests a page with `page_size = N` THEN
    `members_repository.list_members_page` passes `Limit = N` to the DynamoDB Query, returning up
    to N RAW rows BEFORE any scope filtering
4.2 WHEN `_membership_reads.list_members_page` then narrows that raw page by `allowed_scopes`
    THEN the returned in-scope row count is the scope-shrunk subset of N, so `page_size` no longer
    means "returned in-scope rows" (observed 50→5, 100→9, 250→20)
4.3 WHEN the "Max" option is used (no `Limit`, one ~1 MB Query page) THEN the returned count is
    the scope-shrunk subset of that one raw page (observed Max→105, exactly the old Utrecht
    member count), not the full in-scope set
4.4 WHEN the caller is all-access (`["*"]`) THEN the raw page is still post-filtered row-by-row
    even though every row is in scope — unnecessary work and the same undercount shape whenever a
    raw page contains non-member child items

### Expected Behavior (Correct)

#### Bug 1 — stale scope projection (propagation miss)

2.1 WHEN a member user's `region` scope is changed from a specific region to "all" (`["*"]`) THEN
    the system SHALL propagate the change to the DynamoDB `governance_projection`
    `scopegrant#<user>#region` row so the projected `values` become `["*"]`, version-guarded by
    the source's advanced timestamp (the newer MySQL `updated_at` supersedes the stale
    projection version)
2.2 WHEN the on-change `enqueue_sync` drain fails THEN the system SHALL make that failure
    observable and/or retried rather than silently swallowed, so a propagation miss is surfaced
    (and/or a periodic reconcile reliably backstops it) instead of leaving the projection stale
    indefinitely
2.3 WHEN a reconcile runs for the tenant THEN the system SHALL rewrite the stale `scopegrant#`
    row idempotently and version-guarded (a newer source supersedes an older projection; a staler
    source never clobbers a newer projection)
2.4 WHEN the projection is current THEN the SAM read edge SHALL resolve `allowed_scopes` to
    `["*"]` and the member list SHALL reflect the widened "all" scope

#### Bug 2 — pagination undercount (Limit before scope filter)

5.1 WHEN a caller requests a page with `page_size = N` THEN the system SHALL return up to N
    **in-scope** rows for that page (not up to N raw rows that are then scope-shrunk), so
    `page_size` means returned in-scope rows
5.2 WHEN an all-access caller (`["*"]`) requests `page_size = 50` THEN the system SHALL return up
    to 50 in-scope member rows for the page (the post-filter must not drop in-scope rows)
5.3 WHEN scope narrowing is required THEN the system SHALL resolve scope into the Query (e.g. a
    `FilterExpression`) and/or page via `LastEvaluatedKey` until `limit` in-scope rows are
    collected, rather than applying `Limit` to the raw partition and post-filtering a single page
5.4 WHEN a page is produced THEN the system SHALL CONTINUE TO enforce tenant isolation at the
    partition key and SHALL return an honest next-page cursor so prev/next paging stays correct

### Unchanged Behavior (Regression Prevention)

#### Bug 1 — stale scope projection (propagation miss)

3.1 WHEN a scope write succeeds in MySQL THEN the system SHALL CONTINUE TO treat MySQL
    `user_tenant_scope` as the source of truth and SHALL NOT break the write if projection
    propagation fails (the write remains committed; propagation is decoupled)
3.2 WHEN peers are already in sync (MySQL value == projected value) THEN the system SHALL
    CONTINUE TO leave their `scopegrant#` rows unchanged (a reconcile is a no-op for already-
    consistent users — `ledenadministratie`, `webmaster`)
3.3 WHEN a stored projection row is NEWER than the source THEN the system SHALL CONTINUE TO
    version-guard and NOT overwrite it with a staler source value
3.4 WHEN other projected records exist (`config#*`, `module#*`, other dimensions' grants) THEN
    the system SHALL CONTINUE TO leave them unaffected — the fix is scoped to scope-grant
    propagation/observability

#### Bug 2 — pagination undercount (Limit before scope filter)

6.1 WHEN a caller has a guaranteed-deny scope (empty map or a `[]` dimension) THEN the system
    SHALL CONTINUE TO return `([], None)` without paging the repository
6.2 WHEN a cursor is supplied THEN the system SHALL CONTINUE TO enforce tenant isolation via the
    cursor codec (a tampered/stale cursor naming another tenant raises and never resumes there)
6.3 WHEN rows are returned THEN the system SHALL CONTINUE TO apply the per-dimension AND scope
    rule and enrich calculated fields exactly as the non-paged `list_members` read does
6.4 WHEN the non-paged read path (`list_members`) and other members reads are used THEN the
    system SHALL CONTINUE TO behave exactly as before — the fix is scoped to the paged
    `list_members_page` path
6.5 WHEN child items (non-member records sharing the `member#` prefix) appear in a raw page THEN
    the system SHALL CONTINUE TO exclude them from the returned member rows

## Deriving the Bug Conditions

Two distinct bug conditions, one per bug. `F` is the current (unfixed) behavior; `F'` is the
fixed behavior.

### Bug 1 — stale scope projection

```pascal
FUNCTION isBugCondition_projection(X)
  INPUT: X of type ScopeChange { tenant, user, dimension, old_values, new_values,
                                 mysql_updated_at, projected_version, projected_values }
  OUTPUT: boolean

  // A scope change landed in MySQL (source newer than projection) but the
  // projected scopegrant row still holds the OLD values.
  RETURN X.new_values != X.old_values
     AND X.mysql_updated_at > X.projected_version      // source is newer
     AND X.projected_values = X.old_values             // projection never advanced
END FUNCTION
```

```pascal
// Property: Fix Checking — a newer source change is propagated / reconciled
FOR ALL X WHERE isBugCondition_projection(X) DO
  run_propagation_or_reconcile'(X.tenant)
  ASSERT projected_values_after(X.tenant, X.user, X.dimension) = X.new_values
     AND drain_failure_is_observable_or_retried(X)
END FOR
```

```pascal
// Property: Preservation Checking — non-buggy inputs behave identically
FOR ALL X WHERE NOT isBugCondition_projection(X) DO
  ASSERT projection_state(F, X) = projection_state(F', X)
  // e.g. already-in-sync peers -> unchanged; a NEWER projection -> not clobbered
  //      by a staler source; config#/module# rows -> untouched;
  //      a committed MySQL write -> still committed even if propagation fails.
END FOR
```

### Bug 2 — pagination undercount

```pascal
FUNCTION isBugCondition_paging(X)
  INPUT: X of type PageRequest { tenant, allowed_scopes, page_size }
  OUTPUT: boolean

  // A page request whose returned in-scope rows are fewer than page_size purely
  // because Limit was applied to the raw partition before the scope filter, while
  // more in-scope rows remain available in the partition.
  RETURN NOT is_guaranteed_deny(X.allowed_scopes)
     AND more_in_scope_rows_available(X.tenant, X.allowed_scopes, X.page_size)
     AND returned_in_scope_count(F, X) < min(X.page_size, total_in_scope(X))
END FUNCTION
```

```pascal
// Property: Fix Checking — page_size means returned in-scope rows
FOR ALL X WHERE isBugCondition_paging(X) DO
  rows, cursor ← list_members_page'(X.tenant, X.allowed_scopes, X.page_size)
  ASSERT count(rows) = min(X.page_size, total_in_scope(X))
     AND all_in_scope(rows, X.allowed_scopes)
     AND tenant_isolated(rows, X.tenant)
END FOR
```

```pascal
// Property: Preservation Checking — non-buggy inputs behave identically
FOR ALL X WHERE NOT isBugCondition_paging(X) DO
  ASSERT list_members_page(F, X) = list_members_page(F', X)
  // e.g. guaranteed-deny scope -> ([], None); tampered cursor -> raises;
  //      child-item exclusion and per-dimension AND rule unchanged;
  //      the non-paged list_members path unchanged.
END FOR
```
