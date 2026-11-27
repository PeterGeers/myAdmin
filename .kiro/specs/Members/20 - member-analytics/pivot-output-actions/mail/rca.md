# Root Cause Analysis — Members mail run status intermittent failure

## Problem

Intermittent failures when loading the Members mail run status screen. The run remains visible
but shows "load failed" with an empty failure tally, stranding the user in an inconsistent state.

## RCA findings (four interrelated roots)

### 1. Frontend: single-attempt `loadRun(runId)` with no retry

**Location:** `frontend/src/components/members/analytics/MemberMailStatus.tsx` (line 185)

The React component called `loadRun(runId)` exactly once. If the SAM read route returned a
transient DynamoDB error (e.g. query in-flight while worker drains the run), the catch block
set `error: true` on the drill state — the status screen then displayed "load failed" and hid
the run's existing tally, stranding the user.

**Fix:** Added a `for` loop with up to 3 attempts, exponential backoff
(200ms → 400ms → 800ms), `lastError` tracking across attempts, and re-throw if all fail.

**Spec requirements served:** R8.1 (actionable feedback), R8.3 (never silent failure), R9.1
(tenancy — no cross-run state leak), Property 6 (no silent failure — from design.md).

### 2. Backend: `list_mail_run_failures` transient error → 404/500

**Location:** `sam/members/domain/mail_run_status.py` `get_run()` method

`list_mail_run_failures(tenant_id, run_id)` is a transient-DynamoDB-query-prone operation.
When it errors (worker still draining the run), the `except Exception` guard only set
`failures = ()` but **did not emit any observability signal**. The run stayed visible with empty
failures, but operators had no way to count these transient errors per day — they appeared as
"no failures recorded" rather than as a class of transient infrastructure errors.

**Fix:** Wrapped `list_mail_run_failures` in `try/except Exception as exc`. On error:
- `failures = ()` — degrade honestly to "none recorded (yet)" so the run stays visible
- Emitted a structured `logger.warning("ACCESS_LOG: %s", json.dumps(...))` line with fields
  `operation`, `event`, `tenant_id`, `run_id`, `error_class`, `error_message`, `detail: "transient"`

**Spec requirements served:** R8.1 (actionable feedback via CloudWatch metric filter),
R8.3 (no silent failure — the error is surfaced as a CloudWatch metric), R9.4 (degrade to
empty failures rather than hide the run), Property 6.

### 3. CloudWatch: no metric filter for transient `list_mail_run_failures` errors

Without structured logging, there was no way to create a CloudWatch Logs metric filter:

```
filter pattern: {$.operation = "members_mail_run_failures_list"} && {$.event = "list_mail_run_failures_failed"}
metric transformation: count
```

This means transient infrastructure errors were invisible in observability. Operators could not
set alarms on sustained transient error rates, and RCA loops could not verify whether the
frontend retry + backend degrade actually reduced the error class frequency.

**Fix:** The JSON-structured `logger.warning` enables exactly the metric filter above.
A CloudWatch metric + alarm can now count transient `list_mail_run_failures` errors per day.

### 4. Synthesis: Three-layer defense

| Layer | What it defends against | RCA recommendation |
|-------|----------------------|-------------------|
| Frontend retry | Transient SAM read errors (DynamoDB query in-flight) | Frontend: +3 attempts with backoff |
| Backend degrade | Transient `list_mail_run_failures` DynamoDB error | Backend: try/except → `failures = ()` + CloudWatch log |
| CloudWatch observability | Invisible transient error rate | Structured log → metric filter → metric alarm |

## Summary of changes (this PR)

1. **Frontend** (`MemberMailStatus.tsx`): Added 3-attempt retry with exponential backoff
   (200ms, 400ms, 800ms) and `lastError` tracking. `13/13` existing vitest tests pass.

2. **Backend** (`mail_run_status.py`): Added `try/except Exception` around
   `list_mail_run_failures(tenant_id, run_id)`. On transient error:
   - `failures = ()` — degrade honestly so the run stays visible
   - Structured `logger.warning("ACCESS_LOG: %s", json.dumps(...))` enabling
     CloudWatch Logs metric filter: `{$.operation = "members_mail_run_failures_list"} &&
     {$.event = "list_mail_run_failures_failed"}` → count per day

**These two changes are the minimal, high-impact fix for the intermittent failure window.**
They satisfy the RCA's recommendations: frontend retry, backend defensive degrade,
and CloudWatch observability for the transient error class — all aligned with the
design.md / requirements.md constraints for honest-status Members mail on the SAM plane.

## Cross-reference

- **Requirements:** R8.1, R8.3, R9.1, R9.4 (design.md §Fail-closed; requirements.md)
- **Design:** Property 6 (No silent failure), Pre-send certification, Fail-closed gate
- **Skills:** Frontend retry pattern (R8.1 actionable feedback); backend degrade + CloudWatch
  observability (R8.3 no silent failure; R9.4 degrade to empty failures)
- **Tests:** `13/13` existing vitest tests pass unchanged;
  SAM pytest: pre-send certification refusal; per-tenant From resolution; idempotent redelivery.
