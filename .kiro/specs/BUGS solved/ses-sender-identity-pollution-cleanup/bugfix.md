# Bugfix Requirements Document

## Introduction

Two independent, implementable problems remain on the SES sender-verification path: junk SES
identities can be (re)created (concern B), and raw AWS error text leaks to the client on both
planes (concern C). The one-time identity cleanup that relieved the quota cap is already done
as a manual operational run (see Background) and is NOT part of this spec's shippable scope.

### Background — the pollution event and the one-time manual cleanup (historical)

The `personal` SES account (344561557829, eu-west-1, config set `myadmin-emails`) was polluted
to its ~10,000 identity cap by a WebMaster dev-credential fuzz run that fired
`VerifyEmailIdentity` DIRECTLY at production SES (CloudTrail ground truth: direct
`ses.verify_email_identity(...)` calls for fuzz addresses from a WSL dev machine, hitting
`ThrottlingException: Rate exceeded` and the cap error), bypassing the app's
`EmailVerificationService`. At the cap, legitimate verify/resend failed with
`ValidationException: Maximum number of verified identities exceeded`. A one-time manual cleanup
(a throttled, resumable delete script the user ran against live SES) removed the ~9,900 fuzz
identities, brought the pool back under the cap to ~9 genuine senders, and restored verify/resend.
The cleanup preserved the genuine senders — assembled as the union of Flask `email_verifications`
rows (`verified`/`pending`), SAM `config#mail`-derived senders, the infra `jabaki.nl` domain
identity, and a named always-keep allow-list in which `webmaster@h-dcn.nl` is the critical
must-keep — and the authoritative live keep-list lives in the cleanup script's `keep.json`. That
cleanup is operational (script + `keep.json` under `.agent-output`), not shippable code, and
carries no requirement here.

### Current status

- **RESOLVED — send-path `AccessDenied` on `ses:SendRawEmail`.** A separate root cause from the
  cap: the IAM policy `myadmin-ses-email-sending-production` granted send only on the `jabaki.nl`
  DOMAIN identity, not per-address identities. It was widened to
  `arn:aws:ses:eu-west-1:344561557829:identity/*`, the committed Terraform
  `infrastructure/iam-railway-backend.tf` now matches (commit `04770c7b2`), and a live send
  confirmed success. Done + committed — not a concern to implement here.
- **PENDING — concern B (prevent recurrence):** scope / rate-limit the
  `AllowSESIdentityVerification` grant and lock down / retire the broad `WebMaster` principal
  (primary), make the Flask SES client injectable (secondary/latent), and tighten
  `_validate_email` (secondary).
- **PENDING — concern C (error sanitization):** two-plane (Flask + SAM) sanitization of the raw
  AWS `ClientError` text at the service boundary.

### Two-account scope (brief)

There are TWO SES accounts / TWO identity pools (SES identities + config sets are account+region
scoped):

- **Flask plane — `personal` account (344561557829, eu-west-1), config set `myadmin-emails`.**
  The only plane that creates per-address identities (`EmailVerificationService` calls
  `VerifyEmailIdentity`); the plane that was polluted.
- **SAM plane — `nonprofit-deploy` account (506221081911, eu-west-1), config set
  `members-emails`.** A separate, clean pool. `SesBotoSender` only SENDS from a verified DOMAIN
  identity and never verifies.

Error sanitization (concern C) applies on BOTH planes' CODE: Flask `SESEmailService` per
`30-backend-api-flask-mysql`; SAM `SesBotoSender` per `39`/`35`.

### Terminology — two different "webmaster" things, never conflate them

Distinguished by TYPE, not the shared word — still relevant for concern B:

- **`WebMaster`** — an AWS **IAM USER** (`arn:aws:iam::344561557829:user/WebMaster`). The ACTOR
  that fired the fuzz `VerifyEmailIdentity` calls; the broad legacy principal concern B locks
  down / retires. Never an email identity.
- **`webmaster@h-dcn.nl`** — a REAL, IMPORTANT SES **email-address identity** (verified sender).
  A must-keep sender, not a deletion or remediation target.

### Non-goal

The tenant-only sender model — removing the silent `support@jabaki.nl` platform fallback and
failing closed when a tenant sender is unverified — is a deliberate, separate follow-up spec. It
is explicitly out of scope here and must not be changed by this bugfix.

## Bug Analysis

### Current Behavior (Defect)

**Concern B — ungated verify grant + broad `WebMaster` principal let junk be (re)created**

1.1 WHEN the `AllowSESIdentityVerification` IAM grant is evaluated THEN it permits `ses:VerifyEmailIdentity` on `Resource = "*"` with no rate/scope gate, so broad `WebMaster` credentials can fire arbitrary `verify_email_identity` calls DIRECTLY at production SES, bypassing `EmailVerificationService` — the confirmed mechanism behind the junk identities (see Background)
1.2 WHEN any FUTURE code path constructs `EmailVerificationService` without patching `boto3` (a script, integration test, REPL, or fuzz harness) THEN `__init__` builds a real `boto3.client("ses")` with no injection seam and `initiate_verification` / `update_email` / `resend_verification` WOULD call real SES `verify_email_identity`, creating permanent billable identities — a LATENT risk (defense-in-depth), NOT the demonstrated cause
1.3 WHEN an email whose local part contains prototype-pollution keys (e.g. `__proto__`, `constructor`, `prototype`) or exploit special characters (`| ^ # { } = ! ~` etc.) reaches `_validate_email` THEN the full RFC 5322 regex returns True, so even the legitimate app path would turn such a value into a permanent SES identity — guarding ONLY the app path, not the direct bypass

**Concern C — raw AWS error leaked to the client, on BOTH planes (carried over)**

1.4 WHEN Flask `SESEmailService.send_email_with_attachments` catches a `ClientError` (e.g. `AccessDenied ... ses:SendRawEmail ... identity/<addr>`) THEN the system returns `{'success': False, 'error': f"{error_code}: {error_msg}"}` and the route forwards the verbatim AWS message (including the ARN/identity detail) into the UI toast
1.5 WHEN Flask `SESEmailService.send_email` catches a `ClientError` THEN the system likewise returns the verbatim `f"{error_code}: {error_msg}"` to the caller
1.6 WHEN SAM `SesBotoSender.send` catches a `ClientError` THEN the system reports `ok=False` with the raw `"<Code>: <Message>"` string (`_client_error_string(exc)`) on the outcome, carrying AWS detail outward on the SAM plane

### Expected Behavior (Correct)

**Concern B — ungated verify grant + broad `WebMaster` principal let junk be (re)created**

2.1 WHEN the `AllowSESIdentityVerification` IAM grant and the `WebMaster` principal are remediated THEN the system SHALL scope / rate-limit `ses:VerifyEmailIdentity` rather than granting `Resource = "*"` ungated, AND SHALL lock down / retire the broad legacy `WebMaster` principal, so developer credentials can NO LONGER fire arbitrary `verify_email_identity` DIRECTLY at production SES (PRIMARY fix)
2.2 WHEN a developer/script attempts arbitrary `ses:VerifyEmailIdentity` against production SES under remediated credentials THEN the system SHALL NOT permit creation of arbitrary identities (the direct-verify bypass is no longer open)
2.3 WHEN `EmailVerificationService` is constructed THEN the SES client SHALL be an injectable, lazily-resolved, fail-safe seam (constructor-injected port, mirroring SAM `SesBotoSender`), so tests/scripts/fuzz inject a fake and the real SES client is reached only on an explicitly production-wired path (secondary/latent hardening)
2.4 WHEN an email with prototype-pollution keys, exploit special characters in the local part, an implausible/oversized local or domain part, or no sane domain is submitted THEN `_validate_email` SHALL reject it (return False) so SES `verify_email_identity` is never called for it on the app path (defense-in-depth on the app path only)

**Concern C — raw AWS error leaked to the client, on BOTH planes (carried over)**

2.5 WHEN Flask `send_email_with_attachments` catches a `ClientError` THEN the system SHALL return a generic caller-safe message to the client, log the full AWS error (code + message) server-side, and retain a structured `error_code` internally for fallback logic (not echoed to the client), per `30-backend-api-flask-mysql`
2.6 WHEN Flask `send_email` catches a `ClientError` THEN the system SHALL apply the same sanitization: generic client message, full detail logged server-side, structured `error_code` retained internally
2.7 WHEN SAM `SesBotoSender.send` catches a `ClientError` THEN the outcome SHALL carry a generic/structured error (full AWS detail logged server-side, a structured code retained internally for the worker's retryable-vs-permanent classification) rather than the raw `"<Code>: <Message>"` string on any client-facing path, per `39`/`35`

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the Flask app verifies a genuine, deliverable sender address (plausible local part, real domain) THEN the system SHALL CONTINUE TO call SES `verify_email_identity`, store the pending/verified record, and resolve it via `get_verified_sender`
3.2 WHEN the SAM send path resolves a sender THEN it SHALL CONTINUE TO use the projected `mail_certified` flag (Option B, no live SES call on send) and `SesBotoSender` SHALL CONTINUE TO only SEND, never verify an identity
3.3 WHEN `send_email` / `send_email_with_attachments` (Flask) or `SesBotoSender.send` (SAM) succeeds THEN the system SHALL CONTINUE TO return its success shape (`{'success': True, 'message_id': ...}` / `SesSendOutcome(ok=True, ...)`) and log exactly as before
3.4 WHEN internal fallback / worker logic inspects a send/verify failure THEN it SHALL CONTINUE TO have access to the structured `error_code` (the sanitization removes raw AWS detail from the client body / client-facing path, not from server-side handling or the SAM worker's classification)
3.5 WHEN the resend cooldown (60s) and DB status transitions apply THEN the system SHALL CONTINUE TO behave as before for valid addresses
3.6 WHEN a tenant has no verified sender THEN the system SHALL CONTINUE TO use the existing platform-fallback behavior unchanged (the tenant-only / fail-closed sender model is a deliberate non-goal of this bugfix)

## Bug Condition and Properties

**Key definitions:**
- **F**: the original (unfixed) state — the ungated `AllowSESIdentityVerification`
  (`Resource = "*"`) grant and broad `WebMaster` principal that allowed DIRECT production
  verify, the hard-wired `EmailVerificationService` SES client (no injection seam),
  `_validate_email`, and the Flask/SAM send error strings.
- **F'**: the fixed state — the scoped/rate-limited `VerifyEmailIdentity` grant and
  locked-down/retired `WebMaster` principal (primary), the injectable Flask SES seam
  (secondary/latent hardening), tightened validation, and sanitized send errors on both planes.

### Concern B — ungated verify grant + un-injectable client + validation (pollution hole)

```pascal
FUNCTION isBugCondition_B_client(verifyCall)
  INPUT: verifyCall of type SesVerifyAttempt   // {principal, resourceScope, rateGated, ...}
  OUTPUT: boolean

  // PRIMARY (evidence-backed): a broad principal (e.g. the WebMaster IAM user) can fire
  // ses:VerifyEmailIdentity DIRECTLY at production SES because the grant is Resource="*"
  // and ungated, bypassing EmailVerificationService. Confirmed mechanism (see Background).
  RETURN isBroadLegacyPrincipal(verifyCall.principal)        // e.g. WebMaster
      AND targetsProductionSes(verifyCall)
      AND NOT scopedOrRateGated(verifyCall)                  // AllowSESIdentityVerification Resource="*", ungated
END FUNCTION

FUNCTION isBugCondition_B_seam(constructionContext)
  INPUT: constructionContext of type ServiceConstruction
  OUTPUT: boolean

  // SECONDARY / LATENT (defense-in-depth, NOT the demonstrated cause): a FUTURE construction
  // path (script / test / REPL / fuzz) that is NOT explicitly production-wired yet reaches a
  // REAL boto3 SES client because EmailVerificationService.__init__ has no injection seam under F.
  RETURN NOT explicitlyProductionWired(constructionContext)
END FUNCTION

FUNCTION isBugCondition_B_email(email)
  INPUT: email of type String
  OUTPUT: boolean

  // SECONDARY: non-deliverable / abusive addresses the old _validate_email accepted. Guards
  // ONLY the app path — it would NOT have stopped the direct verify calls that bypassed the
  // service (which is what happened).
  RETURN hasPrototypeKey(localPart(email))          // __proto__, constructor, prototype
      OR hasExploitSpecialChars(localPart(email))    // | ^ # { } = ! ~ and similar
      OR NOT hasSaneDomain(email)
      OR exceedsLengthCap(email)
END FUNCTION
```

```pascal
// Property (PRIMARY): broad creds can no longer directly verify arbitrary production identities
FOR ALL verifyCall WHERE isBugCondition_B_client(verifyCall) DO
  // F' scopes/rate-limits AllowSESIdentityVerification and locks down / retires WebMaster
  ASSERT NOT permittedToVerify'(verifyCall)
     AND NOT arbitraryIdentityCreated'(verifyCall)
END FOR

// Property (SECONDARY/LATENT): a non-production-wired construction never reaches real SES
FOR ALL ctx WHERE isBugCondition_B_seam(ctx) DO
  service ← EmailVerificationService'(ctx)        // injectable seam; fake by default off-prod
  ASSERT NOT realSesClientResolved(service)
     AND NOT realSesVerifyEmailIdentityCalled(service)
END FOR

// Property (SECONDARY): junk is rejected before any SES call on the real app path
FOR ALL email WHERE isBugCondition_B_email(email) DO
  result ← validateEmail'(email)
  ASSERT result = False AND NOT sesVerifyEmailIdentityCalled(email)
END FOR
```

### Concern C — error sanitization (BOTH planes)

```pascal
FUNCTION isBugCondition_C(sendOutcome)
  INPUT: sendOutcome of type SendResult   // Flask dict OR SAM SesSendOutcome
  OUTPUT: boolean

  // Buggy outcomes are ClientError failures whose verbatim AWS "<Code>: <Message>"
  // text reaches a client-facing path (Flask response body, or SAM outcome error).
  RETURN sendOutcome.isClientError
END FUNCTION
```

```pascal
// Property: Fix Checking — client never sees raw AWS detail; server/worker keeps it (both planes)
FOR ALL sendOutcome WHERE isBugCondition_C(sendOutcome) DO
  result ← send'(sendOutcome)                        // Flask SESEmailService OR SAM SesBotoSender
  ASSERT isGenericMessage(result.clientFacingError)
     AND NOT containsAwsDetail(result.clientFacingError)   // no ARN / identity / raw code:msg
     AND fullAwsErrorLoggedServerSide(sendOutcome)
     AND structuredErrorCodeRetainedInternally(result)     // Flask fallback / SAM worker classify
END FOR
```

### Preservation (all concerns)

```pascal
// Property: Preservation Checking — non-buggy inputs behave identically
FOR ALL x WHERE NOT (isBugCondition_B_client(x)
                     OR isBugCondition_B_seam(x)
                     OR isBugCondition_B_email(x)
                     OR isBugCondition_C(x)) DO
  ASSERT F(x) = F'(x)
END FOR
```

This ensures genuine senders are preserved across BOTH planes (3.1), the SAM send path keeps
Option B's projected-flag behavior and never verifies (3.2), deliverable addresses still verify
and resolve (3.1, 3.5), successful sends behave unchanged on both planes (3.3), internal
fallback / worker logic still sees `error_code` (3.4), and the platform-fallback sender behavior
is untouched (3.6).
