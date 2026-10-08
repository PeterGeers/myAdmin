# SES Production Access (nonprofit-deploy) — Runbook (Task 0.1)

Goal: move the **nonprofit-deploy** account (`506221081911`, `eu-west-1`) SES out of
sandbox into **production**, after a prior request was **denied** (case `178525018600435`).

Why this is not IaC / not dry-runnable: production access is an **AWS human review**, not a
resource you declare. The only API is `aws sesv2 put-account-details`, which *submits an
application* — there is no CloudFormation resource and no `--dry-run`. The safe read-only
calls below (`get-caller-identity`, `get-account`) are the closest thing to a dry run: they
show the current state before you change anything. The *infra* around SES (config set, SNS
bounce/complaint, verified senders, queue/worker, IAM) IS IaC — that is tasks 0.2–0.5 / 4.x
in `template.yaml`, NOT this file.

---

## Live account state (read by Kiro — read-only, already run)

From `aws sesv2 get-account` on `506221081911` / `eu-west-1`:

| Field | Value |
|---|---|
| Identity | `506221081911` / `NonprofitDeployRole` (correct account) |
| `ProductionAccessEnabled` | **false** (still sandbox) |
| Quota | 200 / 24h, 1 msg/sec (sandbox default) |
| `EnforcementStatus` | HEALTHY |
| Suppression | BOUNCE + COMPLAINT already enabled |
| Prior review | **DENIED**, case `178525018600435` |

**Why it was denied (now visible in the account):** the prior request declared
`MailType: TRANSACTIONAL` and literally said *"We do not send marketing emails."* But R0's
whole point is the bulk *clubblad* newsletter — that IS marketing/bulk. The denied request
contradicted the real use case. The re-request fixes exactly this: declare `MARKETING`,
state real bulk volume, describe opt-out.

---

## PART A — What Kiro has already done (no action needed from you)

- [x] Verified identity resolves to `506221081911` (not the personal account).
- [x] Read current SES state (`get-account`) — confirmed still sandbox + saw the denial reason.
- [x] Generated + filled the request payload: `ses-production-request.input.json`
      (valid JSON, `MARKETING`, honest correction note referencing the denied case).

## PART B — What Kiro CAN still do if you want (ask me)

These are safe/mechanical and I'll do them on request:

- [ ] Fill the `[BRACKETED]` placeholders in `ses-production-request.input.json` once you
      give me the numbers (avg/day, peak/day, largest batch, cadence, unsubscribe mechanism).
- [ ] Build the SES *infra* in `template.yaml` (configuration set + SNS bounce/complaint
      destination) so Part B of the use-case ("event-driven suppression") is actually true
      before you claim it — this is really tasks 0.2–0.5 and I can start them now.
- [ ] Re-run the read-only `get-account` after you submit, to confirm the status flipped
      to `UnderReview` / `GRANTED`.

## PART C — What ONLY you can do (manual, needs console/account login)

Kiro will **not** run step C2 — submitting an application against the real account is your
call. Do these in order.

### C1 — (optional) sanity-check identity + state yourself
```bash
cd /home/peter/projects/myAdmin
env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json
# MUST print Account 506221081911. If it prints 344561557829, STOP — wrong account.

env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws sesv2 get-account --profile nonprofit-deploy --region eu-west-1 --output json
# Confirm "ProductionAccessEnabled": false before submitting.
```

### C2 — submit the application (THE real step — reviewed by AWS)
First finish the placeholders (or ask Kiro to, Part B). Then:
```bash
cd /home/peter/projects/myAdmin
env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws sesv2 put-account-details \
    --cli-input-json file://.kiro/specs/Members/pivot-output-actions/ses-production-request.input.json \
    --profile nonprofit-deploy --region eu-west-1
```
Notes:
- There is no dry-run; this opens the review. It is safe to re-run to UPDATE the pending
  application if you got a field wrong.
- You can instead paste the same fields into the console: **SES → Account dashboard →
  Request production access**. Use whichever you prefer; the CLI is reproducible.

### C3 — after submit
- Re-run the `get-account` from C1 — `ReviewDetails.Status` should read `PENDING` /
  `UnderReview`. Ask Kiro to run it if you like (Part B).
- AWS replies by email/Support, usually within 24h. On **GRANTED**, quota rises and the
  remaining R0 infra (0.2–0.5) + the queue/worker (4.x) can be deployed and used for real.

---

## Pre-submit checklist (tick before running C2)
- [ ] Identity check (C1) printed `506221081911`.
- [ ] `MailType` is `MARKETING` (the clubblad is bulk — do NOT repeat the TRANSACTIONAL-only mistake).
- [ ] Volume numbers are real estimates (no `[BRACKETED]` placeholders left).
- [ ] Unsubscribe mechanism described concretely AND actually present in bulk sends.
- [ ] Bounce/complaint handling describes only what is implemented.
- [ ] Use-case references the prior denied case `178525018600435` and what changed.

## Files
- `ses-production-request.input.json` — the `put-account-details` payload (edit the brackets).
- this runbook — the ordered steps.
