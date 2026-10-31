# SES Sender Identity Pollution Cleanup Bugfix Design

## Overview

This spec's implementable scope is two forward-looking concerns on the SES sender-verification
path: **prevent recurrence** of junk SES identities (Concern B) and **sanitize raw AWS error
text** leaked to the client on both planes (Concern C). Every design item below maps to a
concrete code or infra change a task can implement.

Two items that the requirements reference are already resolved and are recorded only as status
notes (see Status / Background); they are NOT designed here as deliverables:
- the one-time SES identity cleanup that relieved the quota cap (operational, manual), and
- the IAM `ses:SendRawEmail` send-path widening (committed Terraform).

### Status / Background (already done — not shippable scope)

**Pollution event + one-time cleanup (operational, done).** The `personal`-account SES pool
(344561557829, eu-west-1, config set `myadmin-emails`) was polluted to its ~10,000 identity cap
by a `WebMaster` dev-credential fuzz run that fired `VerifyEmailIdentity` DIRECTLY at production
SES (CloudTrail ground truth), bypassing the app's `EmailVerificationService`; at the cap,
legitimate verify/resend failed with `Maximum number of verified identities exceeded`. A one-time
manual, crash-safe resumable delete script (operational scratch under `.agent-output`, with its
authoritative keep-list in `keep.json` where `webmaster@h-dcn.nl` is the critical must-keep)
removed the fuzz identities, brought the pool back under the cap, and restored verify/resend. That
script + `keep.json` are operational, not product code, and carry no design deliverable here.

**Send-path IAM `ses:SendRawEmail` widening (resolved, done + committed).** A separate root cause
from the cap — the `myadmin-ses-email-sending-production` policy granted send only on the
`jabaki.nl` DOMAIN identity, so a per-tenant verified From was denied. The `AllowSESSendEmail`
Resource was widened to `arn:aws:ses:eu-west-1:344561557829:identity/*` (plus the config-set ARN),
applied via CLI first because production was blocked, then synced into committed Terraform
`infrastructure/iam-railway-backend.tf` (commit `04770c7b2`); a live send confirmed it. Policy
version v1 is retained as a non-default version for rollback. The CLI-then-Terraform ordering is a
noted deviation from the plan-first runbook in `43-cicd-deploys`, taken because production email
was down; the committed `.tf` now matches the live policy. Not a deliverable here.

## Glossary

- **Bug_Condition (C)**: The condition that triggers a remaining bug — a non-production-wired
  construction reaching real SES or an abusive email passing validation (B), or a `ClientError`
  whose raw text reaches a client-facing path (C).
- **Property (P)**: The desired behavior — the real SES client unreachable off a production-wired
  path and junk rejected before any SES call (B); a generic client message with full detail logged
  server-side and a structured `error_code` retained internally (C).
- **Preservation**: Genuine-sender verification/resolution, the SAM projected-flag send path,
  successful send/verify shapes, internal `error_code` access, and the platform-fallback sender
  model all stay unchanged.
- **EmailVerificationService**: Flask service in `backend/src/services/email_verification_service.py`
  that calls SES `VerifyEmailIdentity` and is the ONLY identity-CREATING app code path.
- **SESEmailService**: Flask service in `backend/src/services/ses_email_service.py` that SENDS via
  `send_email` / `send_email_with_attachments` (`send_raw_email`), never verifies.
- **SesBotoSender**: SAM send port in `sam/members/repository/mail_send_adapters.py` — already
  lazy + injectable; only sends, never verifies.
- **`WebMaster`**: an AWS IAM USER (`arn:aws:iam::344561557829:user/WebMaster`) — the fuzz ACTOR;
  the broad legacy principal to lock down / retire. NEVER an email identity.
- **`webmaster@h-dcn.nl`**: a REAL SES email-address identity (verified sender), a must-keep
  sender. Distinct from the `WebMaster` IAM user by TYPE.

### Two-account scope (brief)

TWO SES accounts / TWO identity pools (SES identities + config sets are account+region scoped):
- **Flask plane — `personal` (344561557829, eu-west-1), config set `myadmin-emails`.** The only
  plane that creates per-address identities; the plane that was polluted.
- **SAM plane — `nonprofit-deploy` (506221081911, eu-west-1), config set `members-emails`.** A
  separate, clean pool; `SesBotoSender` only SENDS from a verified DOMAIN identity, never verifies.

Concern C error sanitization applies on BOTH planes' CODE: Flask `SESEmailService` per
`30-backend-api-flask-mysql`; SAM `SesBotoSender` per `39`/`35`.

## Bug Details

### Bug Condition

Formalized for the two implementable concerns only.

**Concern B — un-mockable SES client (PRIMARY) + permissive validation (SECONDARY):**

```
FUNCTION isBugCondition_B_client(constructionContext)
  INPUT: constructionContext of type ServiceConstruction
  OUTPUT: boolean

  // A construction path (script / test / REPL / fuzz) NOT explicitly production-wired
  // that nonetheless reaches a REAL boto3 SES client under the unfixed eager __init__.
  RETURN NOT explicitlyProductionWired(constructionContext)
END FUNCTION

FUNCTION isBugCondition_B_email(email)
  INPUT: email of type String
  OUTPUT: boolean

  // Non-deliverable / abusive addresses the loose RFC 5322 regex accepted.
  RETURN hasPrototypeKey(localPart(email))         // __proto__, constructor, prototype
      OR hasExploitSpecialChars(localPart(email))   // | ^ # { } = ! ~ and similar
      OR NOT hasSaneDomain(email)
      OR exceedsLengthCap(email)
END FUNCTION
```

**Concern C — raw AWS error leaked to client (BOTH planes):**

```
FUNCTION isBugCondition_C(sendOutcome)
  INPUT: sendOutcome of type SendResult   // Flask dict OR SAM SesSendOutcome
  OUTPUT: boolean

  // Buggy: a ClientError failure whose verbatim AWS "<Code>: <Message>" reaches a
  // client-facing path (Flask response body, or SAM outcome error on a client-facing path).
  RETURN sendOutcome.isClientError
END FUNCTION
```

### Examples

- **B client (fixed path):** a fuzz/property run constructs `EmailVerificationService` without
  patching `boto3`. Expected: with the injectable seam, NO real SES client is resolved and NO real
  `verify_email_identity` is called — the identity burst cannot recur.
- **B email (fixed path):** `_validate_email("__proto__@DA.BeauTy")` / `"a|b@x.y"` / `"%4@A.PAGe"`
  currently returns True. Expected: returns False, so SES is never asked to verify it.
- **C (Flask):** `send_email_with_attachments` hits `AccessDenied ... ses:SendRawEmail ...
  identity/<addr>`; today the ARN/identity detail lands in the UI toast. Expected: a generic
  message to the client, full detail logged server-side.
- **C (SAM):** `SesBotoSender.send` returns `ok=False` with the raw `"<Code>: <Message>"`.
  Expected: a structured/generic error outward; full detail logged; the worker still classifies
  retryable-vs-permanent from a retained structured code.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Flask verification of a genuine, deliverable sender still calls SES `verify_email_identity`,
  stores the pending/verified record, and resolves via `get_verified_sender` (req 3.1).
- The SAM send path still uses the projected `mail_certified` flag (Option B, no live SES call on
  send); `SesBotoSender` still only sends, never verifies (req 3.2).
- Successful send/verify shapes (`{'success': True, 'message_id': ...}` /
  `SesSendOutcome(ok=True, ...)`) and their logging are unchanged (req 3.3).
- Internal fallback / SAM worker logic still sees the structured `error_code` for classification
  (req 3.4).
- The resend cooldown (60s) and DB status transitions behave as before for valid addresses
  (req 3.5).
- The existing platform-fallback sender behavior (`support@jabaki.nl`) is unchanged (req 3.6).

**Scope:**
All inputs that are NOT a non-production-wired construction, NOT an abusive email, and NOT a
`ClientError` client-facing leak are completely unaffected. The expected correct behavior for
buggy inputs is defined in the Correctness Properties section below.

**Non-goal (deliberate, separate follow-up spec):** the tenant-only sender model — removing the
silent `support@jabaki.nl` platform fallback and failing closed when a tenant sender is
unverified. Explicitly OUT OF SCOPE here and must not be changed by this bugfix.

## Hypothesized Root Cause

Ordered by importance, confirmed from CloudTrail ground truth and code inspection:

1. **B PRIMARY — the Flask SES client is not injectable.** `EmailVerificationService.__init__`
   eagerly does `self.ses_client = boto3.client("ses", region_name=self.region)` (verified), with
   no seam. Any construction that does not patch `boto3` (script, integration test, REPL,
   fuzz/property harness) talks to REAL SES. The SAM plane already does this right (`SesBotoSender`
   resolves boto3 lazily and is injectable, with a `FakeSesClient` in tests); the Flask verify
   service must gain the same seam. This is what actually closes the recreation hole.

2. **B SECONDARY — permissive validation.** `_validate_email` uses the full RFC 5322 local-part
   class, so it accepts prototype-pollution keys, exploit special characters, and oversized/bad
   domains. Defense-in-depth on the app path: the tighter regex stops junk on the one path that
   legitimately calls SES.

3. **B SECONDARY — the IAM grant is broad (hardening).** `AllowSESIdentityVerification` is
   `Resource = "*"` and ungated, and the `WebMaster` developer credential can reach production SES.
   Scope / rate-limit the grant and lock down / retire the `WebMaster` principal. Implementable
   infra work (produces a task), but secondary to the seam.

4. **RESOLVED / BACKGROUND (not a deliverable).** The send-path `AccessDenied` on
   `ses:SendRawEmail` and the one-time cap cleanup are both done — see Status / Background.

## Correctness Properties

Property 1: Bug Condition (B-client, PRIMARY) - No real SES off a production-wired path

_For any_ construction context where the bug condition holds (isBugCondition_B_client returns
true — not explicitly production-wired), the fixed `EmailVerificationService` SHALL use the
injected/fake SES seam, so NO real boto3 SES client is resolved and NO real `verify_email_identity`
is called, making the fuzz-identity burst unreproducible.

**Validates: Requirements 2.2, 2.3**

Property 2: Bug Condition (B-email, SECONDARY) - Abusive addresses rejected before any SES call

_For any_ email where the bug condition holds (isBugCondition_B_email returns true — prototype
keys, exploit special characters, no sane domain, or oversized), the fixed `_validate_email` SHALL
return False so SES `verify_email_identity` is never called for it on the app path.

**Validates: Requirements 2.4**

Property 3: Bug Condition (C) - Client never sees raw AWS detail; server/worker keeps it

_For any_ send outcome where the bug condition holds (isBugCondition_C returns true — a
`ClientError` failure), the fixed code (Flask `SESEmailService.send_email` /
`send_email_with_attachments` and SAM `SesBotoSender.send`) SHALL surface a generic, caller-safe
message with NO AWS ARN/identity/raw `code:msg` detail, log the full AWS error server-side, and
retain a structured `error_code` internally for Flask fallback / the SAM worker's
retryable-vs-permanent classification.

**Validates: Requirements 2.5, 2.6, 2.7**

Property 4: Preservation - Non-buggy inputs behave identically

_For any_ input where NO bug condition holds (not isBugCondition_B_client, not
isBugCondition_B_email, not isBugCondition_C), the fixed code SHALL produce the same result as the
original code, preserving genuine-sender verification/resolution, the SAM projected-flag send path
(never verify), successful send/verify shapes and logging, internal `error_code` access, the
resend cooldown / DB transitions, and the platform-fallback sender model.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### 1. Concern B PRIMARY — Injectable Flask SES client (the true root-cause fix)

**File:** `backend/src/services/email_verification_service.py`
**Function:** `EmailVerificationService.__init__` + a lazy `ses_client` seam.

Mirror the SAM `SesBotoSender` pattern (lazy + injectable):
1. **Constructor-injected port.** Add a keyword `ses_client=None`. Store it as
   `self._ses_client = ses_client`. Do NOT build a real client in `__init__` (remove the eager
   `self.ses_client = boto3.client("ses", ...)`).
2. **Lazy, fail-safe property.** Add a `ses_client` property that resolves the real
   `boto3.client("ses", region_name=self.region)` ONLY when `self._ses_client is None` and only on
   an explicitly production-wired path. Internal callers (`initiate_verification`,
   `resend_verification`, `check_status`) keep using `self.ses_client` unchanged — no call-site
   churn.
3. **Off-production default is the fake.** Tests/scripts/fuzz pass a fake (the existing mocks). The
   real client is reached only when explicitly production-wired, making the identity burst
   unreproducible from a non-wired path.

### 2. Concern B SECONDARY — Tighten `_validate_email` (defense-in-depth)

**File / function:** same service, `_validate_email`.
1. Reject local parts containing prototype-pollution keys (`__proto__`, `constructor`,
   `prototype`).
2. Reject exploit special characters in the local part (`| ^ # { } = ! ~` and similar) — narrow
   the accepted local-part class below the full RFC 5322 set.
3. Enforce a sane domain (at least one dot, plausible TLD) and an overall/part length cap (reject
   oversized local/domain parts).
4. Keep returning `False` (never raise) so `initiate_verification` / `update_email` short-circuit
   before any SES call, preserving the existing `{'success': False, 'status': 'failed', 'error':
   'Invalid email format'}` shape for invalid input.

### 3. Concern B SECONDARY — IAM scoping (noted hardening)

Implementable infra work, secondary to the seam:
1. Scope / rate-limit the `AllowSESIdentityVerification` grant away from `Resource = "*"` and
   ungated.
2. Lock down / retire the broad `WebMaster` IAM principal — developer credentials should not be
   able to verify arbitrary identities against production SES.

### 4. Concern C — Error sanitization on BOTH planes

**Flask** (`backend/src/services/ses_email_service.py`, per `30-backend-api-flask-mysql`): both
`send_email` and `send_email_with_attachments` currently return
`{'success': False, 'error': f"{error_code}: {error_msg}"}` on the `except ClientError` path.
1. Log the full AWS error server-side (keyed so triage can find it).
2. Return a GENERIC caller-safe message to the client (no ARN/identity/raw `code:msg`).
3. Retain the structured `error_code` INTERNALLY (not in the client body) for existing fallback
   logic, and keep passing the full detail to `log_failed` server-side.
4. Leave the success path and the `except Exception` generic-message path unchanged.

**SAM** (`sam/members/repository/mail_send_adapters.py`, per `39`/`35`): `SesBotoSender.send`
reports `ok=False` with `_client_error_string(exc)` (the raw `"<Code>: <Message>"`).
1. Log the full AWS detail server-side.
2. Carry a structured/generic error (not the raw concatenated AWS message) on any client-facing
   path, while retaining enough structure for the worker SERVICE to classify
   retryable-vs-permanent.
3. Keep the `ok=True` success outcome and the no-resolved-sender `MessageRejected` refusal
   unchanged.

## Testing Strategy

### Validation Approach

Two-phase: first surface counterexamples that demonstrate each bug on the UNFIXED code, then verify
the fix works and preserves existing behavior. Per the change-with-tests contract
(`30-backend-api-flask-mysql` / `34-backend-testing`), the paired tests are updated in the SAME
change as the product code.

### Exploratory Bug Condition Checking

**Goal:** Surface counterexamples before/independent of the fix; confirm or refute the root-cause
analysis.

**Test Plan & Cases:**
1. **B-client (PRIMARY):** construct `EmailVerificationService()` WITHOUT patching `boto3` and
   assert a real client would be built on the UNFIXED code (demonstrates the leak path).
2. **B-email (SECONDARY):** assert `_validate_email("__proto__@DA.BeauTy")`, `"%4@A.PAGe"`,
   `"a|b@x.y"` return True on the UNFIXED regex (will flip to False on fixed code).
3. **C-Flask:** force a `ClientError` (`AccessDenied ... ses:SendRawEmail`) and assert the returned
   `error` contains the verbatim ARN/`code:msg` on the UNFIXED code.
4. **C-SAM:** force a `ClientError` and assert the outcome `error` is the raw `"<Code>: <Message>"`
   on the UNFIXED adapter.

### Fix Checking

**Goal:** For all inputs where the bug condition holds, the fixed code produces the expected
behavior.
```
FOR ALL ctx WHERE isBugCondition_B_client(ctx) DO
  service := EmailVerificationService'(ctx)          // injectable seam; fake by default off-prod
  ASSERT NOT realSesClientResolved(service) AND NOT realSesVerifyEmailIdentityCalled(service)
END FOR
FOR ALL email WHERE isBugCondition_B_email(email) DO
  ASSERT validateEmail'(email) = False AND NOT sesVerifyEmailIdentityCalled(email)
END FOR
FOR ALL outcome WHERE isBugCondition_C(outcome) DO
  r := send'(outcome)
  ASSERT isGenericMessage(r.clientFacingError) AND NOT containsAwsDetail(r.clientFacingError)
     AND fullAwsErrorLoggedServerSide(outcome) AND structuredErrorCodeRetainedInternally(r)
END FOR
```

### Preservation Checking

**Goal:** For all inputs where NO bug condition holds, the fixed code equals the original.
```
FOR ALL x WHERE NOT (isBugCondition_B_client(x)
                     OR isBugCondition_B_email(x) OR isBugCondition_C(x)) DO
  ASSERT F(x) = F'(x)
END FOR
```

**Testing Approach:** Property-based testing for preservation — it generates many inputs across
the domain and catches edge cases manual tests miss, giving strong guarantees that non-buggy
behavior is unchanged. Observe behavior on UNFIXED code first (genuine senders verify, successful
sends, SAM projected-flag path), then capture it in property tests.

**Test Cases:**
1. **Genuine sender verify/resolve** still works (Flask) — observe then assert unchanged.
2. **SAM send path** still uses the projected flag and never verifies.
3. **Successful send/verify shapes** and logging unchanged on both planes.
4. **Internal `error_code`** still available to fallback/worker after sanitization.

### Unit Tests

- `backend/tests/unit/test_email_verification_service.py`: ADD a test asserting the service NEVER
  constructs a real boto3 client without explicit production wiring (construct with no injected
  client + no patched `boto3`, assert no real client is resolved); the existing `service` fixture
  already injects a fake via `patch("...boto3")` and must keep passing. ADD `_validate_email` cases
  for prototype keys / exploit chars / bad + oversized domains (now False).
- `backend/tests/unit/test_email_verification_service_props.py`: already patches `boto3`; extend
  the validation property to assert abusive generated inputs are rejected before any SES call.
- `backend/tests/unit/test_ses_email_service.py`: assert `send_email` and
  `send_email_with_attachments` return a GENERIC `error` (no ARN/`code:msg`) on `ClientError`, that
  the full detail is logged + passed to `log_failed` server-side, and that the success shape is
  unchanged.
- SAM `mail_send_adapters` tests: assert `SesBotoSender.send` no longer carries the raw
  `"<Code>: <Message>"` on the client-facing path, that the worker still classifies from a retained
  structured code, and that `ok=True` + the `MessageRejected` no-sender refusal are unchanged.

### Property-Based Tests

- Generate random non-production-wired constructions and assert the real SES client is never
  resolved (Property 1).
- Generate abusive local parts/domains and assert `_validate_email` rejects them with no SES call
  (Property 2).
- Generate `ClientError` shapes and assert no raw AWS detail reaches the client while the structured
  code is retained internally on both planes (Property 3).

### Integration Tests

- Flask verify end-to-end for a genuine sender (mocked SES) still stores pending/verified and
  resolves via `get_verified_sender`.
- SAM send path for a resolved sender still uses the projected `mail_certified` flag and never
  verifies, with the success outcome shape unchanged.
