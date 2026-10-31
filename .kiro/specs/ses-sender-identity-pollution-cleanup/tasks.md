# Implementation Plan

## Overview

Scope note: the one-time SES identity cleanup and the IAM `ses:SendRawEmail` send-path widening
are ALREADY DONE (see design Status / Background) and carry no implementation task here. The work
below is the two forward-looking concerns: prevent recurrence (Concern B) and sanitize raw AWS
error text on both planes (Concern C). Each product-code change carries its paired test(s) in the
SAME task group per the change-with-tests contract (`30-backend-api-flask-mysql`) — tests are NOT
batched at the end.

Task 6 (IAM / `WebMaster`) is the ONE task that touches LIVE IAM. It is manual, plan-first
Terraform per `43-cicd-deploys`; the `WebMaster` retirement follows the committed cleanup steps in
the `.tf`'s output block. Do not agent-apply it.

## Tasks

- [x] 1. Write bug-condition exploration tests (Concern B + C) — BEFORE any fix
  - **Property 1: Bug Condition** - Un-injectable client, permissive validation, leaked AWS error
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: These tests encode the expected behavior - they will validate the fix once they pass
  - **GOAL**: Surface counterexamples demonstrating each remaining bug on the UNFIXED code
  - **Scoped PBT Approach**: the bugs are deterministic — scope each property to concrete failing cases for reproducibility
  - B-client (PRIMARY, `test_email_verification_service.py`): construct `EmailVerificationService()` WITHOUT patching `boto3` and assert the UNFIXED `__init__` resolves a real `boto3.client("ses", ...)` (the leak seam) — from Bug Condition `isBugCondition_B_seam`
  - B-email (SECONDARY, `test_email_verification_service.py`): assert `_validate_email("__proto__@DA.BeauTy")`, `_validate_email("%4@A.PAGe")`, `_validate_email("a|b@x.y")` all return `True` on the UNFIXED regex — from Bug Condition `isBugCondition_B_email`
  - C-Flask (`test_ses_email_service.py`): force a `ClientError` (`AccessDenied ... ses:SendRawEmail ... identity/<addr>`) in `send_email` and `send_email_with_attachments`; assert the returned `error` contains the verbatim `"{error_code}: {error_msg}"` / ARN detail on the UNFIXED code — from Bug Condition `isBugCondition_C`
  - C-SAM (SAM `mail_send_adapters` tests): force a `ClientError` in `SesBotoSender.send`; assert the outcome `error` equals the raw `"<Code>: <Message>"` (`_client_error_string`) on the UNFIXED adapter — from Bug Condition `isBugCondition_C`
  - Run all four on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL / confirm the leak (this is correct - it proves the bugs exist)
  - Document counterexamples found (e.g. `_validate_email("a|b@x.y") == True`; Flask `error` carries `identity/<addr>`; SAM `error == "AccessDenied: ..."`)
  - Mark complete when the tests are written, run, and the buggy outcomes are documented
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Write preservation property tests (BEFORE implementing fixes)
  - **Property 2: Preservation** - Genuine senders verify/resolve, success shapes, projected-flag path, internal error_code
  - **IMPORTANT**: Follow observation-first methodology — observe UNFIXED behavior, then capture it
  - Observe + capture (Flask verify): a genuine deliverable sender (plausible local part, real domain) still calls SES `verify_email_identity`, stores the pending/verified record, and resolves via `get_verified_sender` (req 3.1); the existing `service` fixture that patches `boto3` keeps passing
  - Observe + capture (resend/DB): the 60s resend cooldown and DB status transitions behave as before for valid addresses (req 3.5)
  - Observe + capture (`test_email_verification_service_props.py`): property — a GENERATED genuine/deliverable address still passes `_validate_email` (True) and reaches the verify call (patched boto3), while generated abusive inputs will flip to rejected after the fix
  - Observe + capture (Flask success): `send_email` / `send_email_with_attachments` success still returns `{'success': True, 'message_id': ...}` and logs as before (req 3.3)
  - Observe + capture (SAM): `SesBotoSender.send` still uses the projected `mail_certified` flag (Option B, no live SES call on send), never verifies (req 3.2); `ok=True` success shape and the no-resolved-sender `MessageRejected` refusal unchanged (req 3.3)
  - Observe + capture (internal `error_code`): fallback / worker logic still sees the structured `error_code` on failure (req 3.4); platform-fallback sender (`support@jabaki.nl`) behavior unchanged (req 3.6)
  - **Testing Approach**: property-based where it generates many inputs across the domain (validation, success/preservation) for stronger guarantees
  - Run on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Concern B PRIMARY — Injectable, lazy Flask SES client (true root-cause fix) + paired tests

  - [x] 3.1 Make `EmailVerificationService` SES client injectable + lazy
    - File: `backend/src/services/email_verification_service.py`
    - `__init__`: add keyword `ses_client=None`; store `self._ses_client = ses_client`; REMOVE the eager `self.ses_client = boto3.client("ses", region_name=self.region)`
    - Add a lazy `ses_client` property that resolves the real `boto3.client("ses", region_name=self.region)` ONLY when `self._ses_client is None` (explicitly production-wired path); return the injected/fake otherwise
    - Internal callers (`initiate_verification`, `resend_verification`, `check_status`) keep using `self.ses_client` unchanged — no call-site churn
    - Mirror the SAM `SesBotoSender` lazy + injectable pattern
    - _Bug_Condition: isBugCondition_B_seam(ctx) — NOT explicitlyProductionWired(ctx)_
    - _Expected_Behavior: Property 1 — injectable/fake seam so no real boto3 SES client resolved and no real `verify_email_identity` called off a non-wired path_
    - _Preservation: genuine-sender verify/resolve, resend cooldown, DB transitions unchanged_
    - _Requirements: 2.3_

  - [x] 3.2 Update paired tests (`test_email_verification_service.py` + `_props.py`) in the SAME change
    - **Property 1: Expected Behavior** - No real SES client off a non-production-wired path
    - **IMPORTANT**: re-run / extend the B-client test from task 1 — construct with no injected client AND no patched `boto3`, assert NO real client is resolved and `verify_email_identity` is never called
    - Keep the existing `service` fixture (patches `boto3` / injects a fake) passing
    - `test_email_verification_service_props.py`: assert generated non-production-wired constructions never resolve a real client before any SES call
    - **EXPECTED OUTCOME**: tests PASS (bug seam closed)
    - Run: `python -m pytest backend/tests/unit/test_email_verification_service.py backend/tests/unit/test_email_verification_service_props.py -q`
    - _Requirements: 2.3, 3.1_

- [x] 4. Concern B SECONDARY — Tighten `_validate_email` (defense-in-depth) + paired tests

  - [x] 4.1 Harden `_validate_email`
    - File / function: `backend/src/services/email_verification_service.py`, `_validate_email`
    - Reject local parts containing prototype-pollution keys (`__proto__`, `constructor`, `prototype`)
    - Reject exploit special characters in the local part (`| ^ # { } = ! ~` and similar) — narrow the accepted local-part class below the full RFC 5322 set
    - Enforce a sane domain (at least one dot, plausible TLD) and an overall / per-part length cap (reject oversized local or domain parts)
    - Keep returning `False` (never raise) so `initiate_verification` / `update_email` short-circuit before any SES call, preserving the `{'success': False, 'status': 'failed', 'error': 'Invalid email format'}` shape
    - _Bug_Condition: isBugCondition_B_email(email) — prototype key / exploit chars / no sane domain / oversized_
    - _Expected_Behavior: Property 2 — `_validate_email` returns False so SES `verify_email_identity` is never called on the app path_
    - _Preservation: genuine deliverable addresses still pass and reach the verify call_
    - _Requirements: 2.4_

  - [x] 4.2 Update paired tests (`test_email_verification_service.py` + `_props.py`) in the SAME change
    - **Property 2: Expected Behavior** - Abusive addresses rejected before any SES call
    - **IMPORTANT**: re-run the B-email cases from task 1 — `__proto__@DA.BeauTy`, `%4@A.PAGe`, `a|b@x.y`, plus bad + oversized domains now return `False`
    - `test_email_verification_service_props.py`: extend the validation property so abusive GENERATED inputs are rejected before any SES call (verify is never invoked for them)
    - Keep genuine-address preservation assertions green (True + verify reached)
    - **EXPECTED OUTCOME**: tests PASS (junk rejected, genuine preserved)
    - Run: `python -m pytest backend/tests/unit/test_email_verification_service.py backend/tests/unit/test_email_verification_service_props.py -q`
    - _Requirements: 2.4, 3.1, 3.5_

- [x] 5. Concern C — Error sanitization on BOTH planes + paired tests

  - [x] 5.1 Flask `SESEmailService` — sanitize `ClientError` in both send paths
    - File: `backend/src/services/ses_email_service.py`
    - In both `send_email` and `send_email_with_attachments` `except ClientError` paths: return a GENERIC caller-safe message (no ARN / identity / raw `code:msg`) instead of `{'success': False, 'error': f"{error_code}: {error_msg}"}`
    - Log the full AWS error (code + message) server-side and keep passing full detail to `log_failed`
    - Retain the structured `error_code` INTERNALLY (not in the client body) for existing fallback logic
    - Leave the success path and the `except Exception` generic-message path unchanged
    - _Bug_Condition: isBugCondition_C(outcome) — a ClientError reaching the client-facing path_
    - _Expected_Behavior: Property 3 — generic client message, full detail logged server-side, structured `error_code` retained internally_
    - _Preservation: success shape + logging unchanged; internal `error_code` still available to fallback_
    - _Requirements: 2.5, 2.6_

  - [x] 5.2 Update Flask paired test (`test_ses_email_service.py`) in the SAME change
    - **Property 3: Expected Behavior** - Flask client never sees raw AWS detail; server keeps it
    - **IMPORTANT**: re-run the C-Flask test from task 1 — assert `send_email` and `send_email_with_attachments` return a GENERIC `error` (no ARN / `code:msg`) on `ClientError`
    - Assert the full detail is logged + passed to `log_failed` server-side, and the success shape is unchanged
    - **EXPECTED OUTCOME**: tests PASS (sanitized, success preserved)
    - Run: `python -m pytest backend/tests/unit/test_ses_email_service.py -q`
    - _Requirements: 2.5, 2.6, 3.3, 3.4_

  - [x] 5.3 SAM `SesBotoSender.send` — carry structured/generic error, not raw AWS text
    - File: `sam/members/repository/mail_send_adapters.py`, `SesBotoSender.send`
    - On any client-facing path, carry a structured / generic error instead of the raw `_client_error_string(exc)` `"<Code>: <Message>"`
    - Log the full AWS detail server-side; retain enough structure for the worker's retryable-vs-permanent classification
    - Keep the `ok=True` success outcome and the no-resolved-sender `MessageRejected` refusal unchanged
    - _Bug_Condition: isBugCondition_C(outcome) — a ClientError reaching the client-facing path on the SAM plane_
    - _Expected_Behavior: Property 3 — generic/structured outward error, full detail logged, structured code retained for worker classification_
    - _Preservation: `ok=True` success shape + `MessageRejected` no-sender refusal unchanged; projected-flag path untouched_
    - _Requirements: 2.7_

  - [x] 5.4 Update SAM paired tests (`mail_send_adapters` tests) in the SAME change
    - **Property 3: Expected Behavior** - SAM outcome never carries raw AWS text; worker still classifies
    - **IMPORTANT**: re-run the C-SAM test from task 1 — assert `SesBotoSender.send` no longer carries the raw `"<Code>: <Message>"` on the client-facing path
    - Assert the worker still classifies retryable-vs-permanent from the retained structured code
    - Assert `ok=True` success and the `MessageRejected` no-sender refusal are unchanged
    - **EXPECTED OUTCOME**: tests PASS (sanitized, classification + success preserved)
    - Run the SAM members test suite for the adapter
    - _Requirements: 2.7, 3.2, 3.3, 3.4_

- [x] 6. Concern B SECONDARY (SENSITIVE — LIVE IAM, manual) — Scope the verify grant + retire `WebMaster`
  - **⚠ This is the ONE task that touches LIVE IAM. Manual, plan-first Terraform per `43-cicd-deploys`. Do NOT agent-apply.**
  - File: `infrastructure/iam-railway-backend.tf`
  - Scope / rate-limit the `AllowSESIdentityVerification` grant off `Resource = "*"` and ungated (narrow to the needed identity scope / add a condition gate)
  - Lock down / retire the broad `WebMaster` IAM principal (`arn:aws:iam::344561557829:user/WebMaster`) — the `WebMaster` retirement follows the committed cleanup steps in this `.tf`'s output block
  - **Plan-first runbook**: `terraform plan -out=tf.plan`, READ it, confirm NO destroy / `# forces replacement` on stateful/shared resources (Cognito pools, buckets) and that the SES policy change is add/update-in-place; owner runs `terraform apply tf.plan` in the release window
  - Sanity-check `aws sts get-caller-identity` is the intended account before any apply (override-ranking trap, `41-shell-environment`)
  - Validation is OPERATIONAL: after remediation, a broad-cred direct `verify_email_identity` against production SES is no longer permitted; genuine app-path verify (3.1) still works
  - Commit the `.tf` edit through the same reviewed PR as the dependent code
  - _Bug_Condition: isBugCondition_B_client(verifyCall) — broad legacy principal, targets production SES, not scoped/rate-gated_
  - _Expected_Behavior: Property (PRIMARY) — broad creds can no longer directly verify arbitrary production identities_
  - _Preservation: genuine app-path verify/resolve unchanged (3.1)_
  - _Requirements: 2.1, 2.2_

- [x] 7. Checkpoint — all tests pass + cleanup closeout
  - Run the paired suites for all changed files:
    - `python -m pytest backend/tests/unit/test_email_verification_service.py backend/tests/unit/test_email_verification_service_props.py backend/tests/unit/test_ses_email_service.py -q`
    - the SAM `mail_send_adapters` tests
  - Confirm every exploration test from task 1 now PASSES and every preservation test from task 2 still PASSES (no regressions)
  - Optional operational closeout (cleanup already done): re-run the operational delete/keep script so the pool settles at FINAL_REMAINING ~9 genuine senders, preserving `keep.json` must-keeps (incl. `webmaster@h-dcn.nl`). This is operational verification, not product code
  - Ensure all tests pass; ask the user if questions arise
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

## Task Dependency Graph

```
1 (bug-condition exploration tests: B-client, B-email, C-Flask, C-SAM)
2 (preservation property tests — baseline on UNFIXED code)

        1 ─┐
           ├─▶ 3.1 ──▶ 3.2        (B PRIMARY: injectable lazy client + paired tests)
        2 ─┘
        1 ─┐
           ├─▶ 4.1 ──▶ 4.2        (B SECONDARY: _validate_email + paired tests)
        2 ─┘
        1 ─┐
           ├─▶ 5.1 ──▶ 5.2        (C Flask: sanitize + paired test)
        2 ─┘
        1 ─┐
           ├─▶ 5.3 ──▶ 5.4        (C SAM: sanitize + paired tests)
        2 ─┘

6  (SENSITIVE live IAM, manual) — depends on 1,2 for behavioral baseline; independent of 3/4/5 code

7  (checkpoint) ◀── 3.2, 4.2, 5.2, 5.4, 6
```

Rules:
- Tasks 1 and 2 (write exploration + preservation tests on UNFIXED code) come first and gate every fix.
- Each fix task (`.1`) is immediately followed by its paired test task (`.2`/`.4`) in the SAME change — never batched.
- Task 6 is the sole live-IAM task: manual, plan-first, owner-applied.
- Task 7 is the final checkpoint and depends on all fix+test pairs and task 6.

### Wave Execution Plan (JSON)

```json
{
  "waves": [
    {
      "wave": 1,
      "parallel": true,
      "tasks": ["1", "2"],
      "rationale": "Write bug-condition exploration tests (fail on unfixed) and preservation baseline tests (pass on unfixed) before any fix. Independent of each other."
    },
    {
      "wave": 2,
      "parallel": true,
      "tasks": ["3.1", "4.1", "5.1", "5.3", "6"],
      "rationale": "Independent code fixes across four files (Flask verify service injectable seam, Flask validation, Flask send sanitization, SAM send sanitization) plus the independent manual live-IAM task. 3.1 and 4.1 edit the same file so serialize if one agent; otherwise independent by concern.",
      "notes": "Task 6 is SENSITIVE live IAM — manual, plan-first, owner-applied; it runs in this wave only in the sense of being unblocked, not auto-executed."
    },
    {
      "wave": 3,
      "parallel": true,
      "tasks": ["3.2", "4.2", "5.2", "5.4"],
      "rationale": "Paired tests for each fix, updated in the same change as their product code. 3.2 and 4.2 both touch the email-verification test files — serialize those two."
    },
    {
      "wave": 4,
      "parallel": false,
      "tasks": ["7"],
      "rationale": "Final checkpoint: run all paired suites, confirm exploration tests now pass and preservation tests still pass; optional operational cleanup closeout to FINAL_REMAINING ~9."
    }
  ],
  "sensitive_tasks": ["6"],
  "notes": "Task 6 touches LIVE IAM (infrastructure/iam-railway-backend.tf): manual plan-first Terraform per 43-cicd-deploys, owner-applied, never agent-applied. 3.1 and 4.1 share email_verification_service.py; 3.2 and 4.2 share the email-verification test files — serialize within-file edits."
}
```

## Notes

- **Out of scope (already done):** the one-time SES identity cleanup and the IAM `ses:SendRawEmail` send-path widening are complete (see design Status / Background); no task implements them. The cleanup finishes operationally by re-running its script to `FINAL_REMAINING` ~9 (task 7 closeout).
- **Change-with-tests:** each product-code change carries its paired test(s) in the SAME task group per `30-backend-api-flask-mysql` / `34-backend-testing` — tests are never batched at the end.
- **Sensitive live-IAM task:** task 6 (`infrastructure/iam-railway-backend.tf` — scope the `AllowSESIdentityVerification` grant + retire the `WebMaster` principal) is the ONE task that touches live IAM. It is manual, plan-first Terraform per `43-cicd-deploys`, owner-applied — never agent-applied. The `WebMaster` retirement follows the committed cleanup steps in that `.tf`'s output block.
- **Shared-file serialization:** tasks 3.1 and 4.1 both edit `email_verification_service.py`; 3.2 and 4.2 both edit the email-verification test files — serialize those within-file edits.
