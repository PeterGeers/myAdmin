# Bugfix Requirements Document

## Introduction

This spec **fully retires the membership status/lifecycle state engine** on the SAM Members
plane ("Cut B"), turning `membership.status` into a plain, tenant-driven open enum field —
authored exactly like `gender` — and turning status CHANGES into ordinary field edits.

> **Direction note — this SUPERSEDES both earlier drafts.** Two prior directions are
> **withdrawn**: (1) the `member-status-open-enum` draft that opened the enum *and* retired
> the engine as one move, and (2) the `member-status-died-state` draft that proposed adding
> `died` as a 7th value to the CLOSED `MembershipStatus` set and wiring `→ died` edges into
> `HDCN_LIFECYCLE_CONFIG`. Both are gone. The folder is renamed to
> `retire-members-status-lifecycle-engine`; the `died`/"Overleden" value is now only a
> *side effect* of the retirement, not the subject of the spec.

### The decision (user-approved, final)

FULLY RETIRE the membership lifecycle state engine. **Rationale (recorded):** the state
engine is more complexity than the team can oversee in this phase, and its
closed-vocabulary + transition-graph GATEKEEPING repeatedly blocks a basic, legitimate need
— letting a tenant add its own status enum value (e.g. `died` / "Overleden") the same way it
adds `gender` values. The one genuinely-wanted engine feature — a welcome mail on activation
via the `on_transition` hook seam — is **DEFERRED** and will be re-built later the simple way
(a pivot over member keys → a welcome mail), NOT through the engine.

Target end-state:

- `membership.status` becomes a **plain, tenant-driven OPEN enum** field — authored like
  `gender` (`choices=None`; tenant supplies values/labels via `members.field_overlay`). Adding
  or relabelling any status value just works end-to-end (save → project → resolved config →
  set on a member), with **no code change**. `died` then works as a side effect.
- Status **changes** become ordinary field edits (any value → any value); **no transition
  graph, no guards, no transition modal gatekeeping**.
- **PRESERVED:** `status = application` as a plain DEFAULT literal on public-form create
  (independent of the engine); tenant isolation; the members CRUD / read / export / analytics
  / mail paths.
- **DELETE** the engine and everything that exists ONLY to serve it, and **RECONCILE** every
  spec/docstring that still asserts a live lifecycle. Leaving disabled-but-present code OR a
  spec that says "lifecycle … PASS" is exactly the bait that caused this recurring discussion
  (an agent/dev rediscovers it and treats it as load-bearing). Removing the code is not
  enough — the written record must match reality.

### The recurring bug this retirement fixes

A tenant admin added a new `membership.status` value (`died` →
`{"value":"died","label":{"en":"Passed Away","nl":"Overleden"}}`) in Tenant Admin. It saved
to MySQL `members.field_overlay` (`fixed_overrides["membership.status"]`) but was **silently
DROPPED at projection**, so the projected `config#fields` `membership.status` carried only
the 6 platform values (`application, pending, active, suspended, lapsed, left`). Because the
value never reached the resolved config, `died` could never be selected or validated on a
member, and (had it somehow been set) the transition engine would never offer it as a target.
The core "add attribute → save → project → use" capability is **broken for `status`**.

**Root cause.** The `status` value set is a CLOSED code vocabulary
(`MembershipStatus` in `sam/members/domain/fixed_fields.py`, wired onto the `status`
`FixedField` as `choices=tuple(s.value for s in MembershipStatus)`), AND status change is
gatekept by a transition-graph state engine (`lifecycle_config.py` +
`_membership_lifecycle.py` + the transition routes) that fails fast on any state outside that
vocabulary. A tenant overlay cannot extend the code vocabulary, and the field resolver is
explicitly forbidden from touching the closed status enum (`field_resolver.py`: "NEVER touch
the closed `membership.status` enum"). The engine is complexity the team does not want to
oversee in this phase, so the fix is to retire it, not to extend it.

### EXTERNAL-CONSUMER / contract check (risk gate — E)

The transition routes are an HTTP API contract, so retiring them is a potential breaking
change. A whole-repo grep for `/transition` and `memberships/transition` (excluding the
vendored `sam/members/.aws-sam/build/` copies) shows the ONLY runtime caller is this SPA
(`frontend/src/services/members/membersResourceApi.ts` → `membersApiService.ts`). Every other
reference is one of: the module's own tests, the parity harness (`members_parity_harness.py`),
or spec/walkthrough markdown. **No other service, script, Postman collection, backfill, or
worker calls these routes.** This is the key risk-gate finding: within this repo the
retirement is NOT a cross-service breaking change. **Open question flagged for sign-off:** if
h-dcn (or any client) has an out-of-repo integration that posts to these routes, that caller
breaks — confirm before execution. (No evidence of one was found in-repo.)

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a tenant adds a new `membership.status` option (e.g. `died`) in Tenant Admin and Saves THEN the system stores it in MySQL `members.field_overlay` but DROPS it at projection, so the projected `config#fields` `membership.status` carries only the 6 platform values.

1.2 WHEN the tenant re-projects from current MySQL THEN the system deterministically drops the tenant-authored status value again (written, but the resolved `status` choices stay the closed 6) rather than carrying it through.

1.3 WHEN a member record is created or updated with a tenant-authored `membership.status` value (e.g. `"died"`) THEN domain validation rejects it as "must be one of: application, pending, active, suspended, lapsed, left", because the `status` `FixedField` carries `choices = MembershipStatus` and `validate_fixed_fields` checks the value against that CLOSED set.

1.4 WHEN a staff user wants to change a member's status THEN the system forces the change through the transition engine — the SPA offers only the targets the tenant `LifecycleConfig` declares as `from → to` edges, guards may deny the move (e.g. `application→pending` needs `context.approved`), and any value outside the closed graph is impossible to reach.

1.5 WHEN a tenant `LifecycleConfig` references a status value that is not in the `MembershipStatus` vocabulary THEN construction fails fast (`LifecycleConfigError`), so the closed code vocabulary gatekeeps the tenant's own value set.

### Expected Behavior (Correct)

2.1 WHEN a tenant adds a new `membership.status` option (e.g. `died` / "Overleden") in Tenant Admin and Saves THEN the system SHALL persist AND project it, so the resolved `config#fields` `membership.status` carries all the tenant-authored values exactly as it already does for `gender`.

2.2 WHEN the tenant re-projects from current MySQL THEN the system SHALL carry every tenant-authored `status` value through to the projected/resolved config (no silent drop).

2.3 WHEN a member record is created or updated with any tenant-authored `membership.status` value THEN the system SHALL accept it, because `status` is now an OPEN enum validated against the RESOLVED tenant choices (or, when the tenant authored none, any non-blank string) — never a closed code set.

2.4 WHEN a staff user changes a member's status THEN the system SHALL treat it as an ordinary field edit through the existing member edit path (any value → any value), with NO transition graph, NO guards, and NO transition modal gatekeeping.

2.5 WHEN a tenant has authored status values THEN the system SHALL need NO code change for those values to work end-to-end (save → project → resolved config → set on a member), matching the `gender` precedent.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a new public applicant record is created on the public form THEN the system SHALL CONTINUE TO default `membership.status = "application"` on create — now as a plain default literal independent of any lifecycle `initial_state`.

3.2 WHEN a member is created / read / updated / listed / searched / exported THEN the system SHALL CONTINUE TO behave exactly as today for every field other than the removed transition gatekeeping, and SHALL CONTINUE TO enforce tenant isolation (every read/write keyed by `tenant_id`).

3.3 WHEN a tenant authors `gender` (or any existing OPEN overlay enum) values THEN the system SHALL CONTINUE TO save, project, resolve, and validate them exactly as today — `status` simply joins them as another open enum.

3.4 WHEN the analytics-set / pivot / mail / send-run / template / schedule / catalog / delegate paths run THEN the system SHALL CONTINUE TO behave exactly as today (they never depended on the lifecycle engine).

3.5 WHEN the field resolver resolves a member's fixed + overlay config THEN the system SHALL CONTINUE TO enforce every OTHER platform invariant (cannot drop/rename a fixed field, cannot make a required fixed field optional, cannot change a fixed field's type, cannot collide keys) — ONLY the "NEVER touch the closed `membership.status` enum" invariant is removed.

### Deriving the Bug Condition

```pascal
FUNCTION isBugCondition(input)
  INPUT: input is either
           (a) a tenant field_overlay authoring a membership.status value NOT in the
               closed platform set (e.g. "died"), OR
           (b) a member create/update setting membership.status to such a value, OR
           (c) any attempt to CHANGE a member's status that the transition graph/guards
               do not declare/permit
  OUTPUT: boolean

  PLATFORM_STATUS := {application, pending, active, suspended, lapsed, left}  // UNFIXED closed set

  RETURN authors_or_sets_status(input)
         AND (
               status_value(input) NOT IN PLATFORM_STATUS      // tenant value the closed set rejects
               OR change_is_gatekept_by_graph_or_guards(input) // status change blocked by the engine
             )
END FUNCTION
```

```pascal
// Property 1: Fix Checking — status is a plain, tenant-driven open enum; changes are plain edits
FOR ALL input WHERE isBugCondition(input) DO
  // F' = status is an OPEN enum (choices=None), no transition engine
  ASSERT tenant_authored_status_value IN resolved_status_choices(tenant)        // survives save→project→resolve
  ASSERT project_then_read_config_fields(tenant).status.values CONTAINS value   // not dropped
  ASSERT validate_member({membership:{status: tenant_value, ...}}) succeeds     // open-enum validation
  ASSERT set_status_via_ordinary_edit(any_value -> any_value) succeeds          // no graph, no guard denial
END FOR
```

```pascal
// Property 2: Preservation Checking — everything NOT involving status gatekeeping is unchanged
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT F(input) = F'(input)
  // public-form create still defaults status=application; tenant isolation; member
  // CRUD/read/export/analytics/mail; gender + other open enums; every non-status field
END FOR
```

Where **F** is the current (unfixed) system (closed 6-value `MembershipStatus`, status
gatekept by the transition engine) and **F'** is the fixed system (status an OPEN enum like
`gender`, the engine fully retired, status changes as ordinary field edits).
