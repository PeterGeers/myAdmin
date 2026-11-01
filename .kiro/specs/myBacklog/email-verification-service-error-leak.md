# SPEC CANDIDATE: Sanitize EmailVerificationService error returns (residual py/stack-trace-exposure)

**Found 2026-10-31 during a post-fix sweep after the SES sender-identity-pollution-cleanup spec.**
That spec's Concern C sanitized the caller-facing error on the Flask `SESEmailService` SEND paths
and the SAM `SesBotoSender`. It did NOT touch `EmailVerificationService`, which still echoes the raw
AWS `"<Code>: <Message>"` to the caller on two paths — the same `py/stack-trace-exposure` class of
leak, just lower severity (the verify/resend messages are typically "invalid address" / "Throttling"
rather than an IAM ARN).

## Evidence (code)

`backend/src/services/email_verification_service.py`:
- `initiate_verification` → on `ClientError`: `return {... "error": f"{error_code}: {error_msg}"}`
- `resend_verification`  → on `ClientError`: `return {"success": False, "error": f"{error_code}: {error_msg}"}`

Both already log the full `[{error_code}] {error_msg}` server-side, so sanitizing the RETURN loses
nothing for triage. (`check_status` does NOT return the raw string to the client — it logs and
returns a cached status — so it is already fine.)

## Goal

Consistent with the sanitized send paths: the caller-facing `error` is a generic, caller-safe
message; the non-sensitive SES CODE is retained internally on `error_code`; full detail only logged
server-side.

## Direction (to design in the spec)

- In `initiate_verification` and `resend_verification`, replace the returned
  `"error": f"{error_code}: {error_msg}"` with a generic message (e.g. the existing
  "Email verification failed. Please try again later." / "Resend failed. Please try again later.")
  and add `"error_code": error_code`. Keep the server-side `logger.error([{code}] {msg})`.
- Preserve the deliberate, caller-safe validation messages (`"Invalid email format"`,
  `"Please wait 60 seconds before resending"`, `"No verification record found"`) — only the
  caught-`ClientError` raw echo changes.
- **Change-with-tests:** update the two paired assertions that currently assert the OLD shape:
  `backend/tests/unit/test_email_verification_service.py` ~L148
  (`"InvalidParameterValue" in result["error"]`) and ~L454 (`"Throttling" in result["error"]`) to
  assert the generic message + `result["error_code"]`. Grep the `_props.py` too.

## Why it's a separate (small) spec, not folded into the cleanup PR

The cleanup spec's Concern C scope was explicitly the SEND paths + SAM adapter; this is an adjacent
path found afterwards. Small, self-contained, same pattern — a tidy follow-up bugfix.

## Pointers
- `backend/src/services/email_verification_service.py` (initiate_verification ~L179, resend ~L314).
- Paired tests: `backend/tests/unit/test_email_verification_service.py` (L148, L454),
  `test_email_verification_service_props.py`.
- Precedent: the sanitized `SESEmailService` / `SesBotoSender` in the
  ses-sender-identity-pollution-cleanup spec (generic error + error_code + server-side log).
