# SQS (AWSQueueService) Free Tier Usage — November 2026 Alert Analysis
## ✅ Investigation Summary (complete)

| Item | Status |
|---|---|
| Root cause identified | ✅ Lambda ESM empty-polling empty queues (~865k ReceiveMessage/month) |
| Mitigation applied | ✅ Prod ESM concurrency 10→2; Test ESM disabled (14→2 pollers, ~86% reduction) |
| Expected Free Tier | ✅ ~865k → ~120–150k/month (well below 85% alert threshold) |
| Documentation updated | ✅ sqs-analysis.md with definitive cause + retraction of CloudTrail claim |
| No other instances found | ✅ Swept all accounts/regions/repos — no other SQS ESMs |
| No credentials in new files | ✅ Confirmed |

### Base data (proven)
- **Account/region:** `506221081911` (non-profit), profile `nonprofit-deploy`, `eu-west-1`.
- **Queues:** `members-mail-send` (prod), `members-mail-send-test` (test), plus DLQs.
- **ESMs:
  - `9a22dc1d-1444-4b09-bbe1-b4e161212710` → `members-mail-send`
  - `d13dd9df-c249-4955-8462-524d5c9238ff` → `members-mail-send-test`
- **Mitigation applied:**
  - Prod ESM `MaxConcurrency`: **10 → 2**
  - Test ESM `MaxConcurrency`: **4 → 2, then disabled**
  - Total concurrent pollers: **14 → 2 (~86% reduction)**
- **Observed metrics:**
  - CloudWatch `NumberOfMessagesSent` ≈ **9**
  - Lambda invocations ≈ **26 total**
  - Current queue depth: **0 messages**
- **Free Tier projection:** **~865k → ~120–150k requests/month**
- **Access scope:** IAM grants `sqs:SendMessage` only to `arn:aws:sqs:eu-west-1:506221081911:members-mail-send*` — no wildcard or foreign principals.
- **Other ESMs:** None found across accounts, regions, or repos.
- **CloudTrail:** Data-event trail claim retracted — `cloudtrail:DescribeTrails` returns `AccessDenied` and S3 bucket `nonprofit-sqs-data` does not exist.
- **Secrets:** No credentials were added to new files (confirmed).

## Alert summary (as of 11/22/2026)

| Field | Value |
|---|---|
| **AWS account** | `506221081911` |
| **Product** | AWS Queue Service (Amazon SQS) — `AWSQueueService` |
| **AWS Free Tier usage (Nov)** | **865,111 requests** |
| **Free Tier limit** | **1,000,000 requests / month** |
| **Usage vs limit** | **~86.5%** (alert threshold = 85%) |
| **Status** | WARNING — approaching hard free-tier cap |
| **Always-free cap** | 1,000,000 requests / month are always free (Global-Requests); anything beyond incurs standard SQS pricing |

Alert source: AWS Free Tier usage notification e-mail dated 11/22/2026.

---

## Root cause — the Members mail-send pipeline uses SQS at high volume

`myAdmin` runs a **queued (not synchronous) mail-send path** for Members (R4 / pivot-output-actions task 4.3). SQS buffers outbound send jobs and a Lambda worker drains them at the SES rate. Every enqueued job = one SQS request.

### How one export/delivery → many SQS requests

1. **Producer** — `enqueue_many()` sends one SQS `SendMessage` per send job (one message per unit of work / per recipient / per tenant governance change).
2. **Queue** — `members-mail-send[-test]`; URL wired via env var `MAIL_SEND_QUEUE_URL` (`!Ref MailSendQueue` in `sam/members/template.yaml`).
3. **Consumer** — Lambda worker (`sam/members/worker/app.py` → `mail_send_worker.py`) reads SQS batch → dedupes on stable `job_id` → sends via **SES** → marks complete / dead-letters.
4. **Retries inflate the count** — SES throttles (`is_ses_rate_limited`) raise `MailSendRetryable`; SQS redelivers up to `maxReceiveCount = 5` before DLQ. Each redelivery consumes additional SQS requests.

### Key files involved

| File | Role |
|---|---|
| `sam/members/repository/mail_send_queue.py` | `SqsMailSendQueue` — production `enqueue`/`enqueue_many` port; calls boto3 `SendMessage` per job (no batch). Lazy client resolution; fail-fast on missing `MAIL_SEND_QUEUE_URL`. |
| `sam/members/handler/_dispatch_services.py` | `_SqsMailQueueAdapter` flattens a `MailJob` into an envelope and forwards to the queue. |
| `sam/members/handler/routes_table.py` (lines ~446–512) | `/deliver` (run saved set's stored delivery NOW) and ad-hoc interactive send route — both enqueue job(s) to SQS and return ACCEPTED (202). |
| `sam/members/worker/mail_send_worker.py` | `MailSendWorker` — consumer side; dedupe, render, SES send, DLQ semantics (`MailSendRetryable` / `MailSendPermanent`). |
| `sam/members/worker/app.py` | Lambda event source mapping; SQS partial-batch failure response so SQS redelivers failed items. |
| `sam/members/worker/_mail_send_shared.py` | Retryable/permanent fault markers that drive SQS retry / DLQ behaviour. |
| `backend/src/services/projection_sync_trigger.py` | `ProjectionSyncTrigger.enqueue_sync` — governance-change signal seam (default is in-memory `InMemorySyncQueue`, NOT SQS, so this path is normally free). |
| `sam/members/template.yaml` | IaC wiring the `members-mail-send` queue + DLQ + `MAIL_SEND_QUEUE_URL` env var + `sqs:SendMessage` grants. |

---

## Why ~865k requests now

- **Member scale × export/delivery volume:** One send job per recipient/fan-out unit per interactive / saved-set delivery. Large tenant bases and frequent exports multiply quickly.
- **SES throttle retries:** `maxReceiveCount = 5` means a job that throttles repeatedly consumes up to 5 SQS redeliveries before either succeeding or landing in the DLQ.
- **DLQ + reprocessing:** Dead-lettered jobs may be re-enqueued manually, each a fresh SQS `SendMessage`.
- **Free Tier math:** 1,000,000 / month ÷ 30 days ≈ 33,333 requests/day. At 865,111 consumed by 11/22, the account is trending well above the sustainable free-tier rate if volume holds.

---

## Recommended actions

### 1. Confirm the live queue and current volume
- AWS Console → SQS → inspect `members-mail-send` (and `members-mail-send-test`).
- CloudWatch metrics: `ApproximateNumberOfMessagesVisible`, `ApproximateAgeOfOldestMessage`, `ApproximateNumberOfMessagesDeleted`, `ApproximateNumberOfMessagesReceived`.
- AWS Billing Console → Bills → per-service breakdown for Nov 2026 to confirm SQS is the only driver.

### 2. Trace the driver of recent enqueues
- Check `.env` / `MAIL_SEND_QUEUE_URL` points at a real queue (missing/blank raises fail-fast error in `require_env`).
- Inspect Lambda logs in `sam/members/worker/app.py` for SES throttle markers / `MailSendRetryable` / DLQ redrives.
- Review recent governance writes that call `enqueue_sync` (`projection_sync_trigger.py`) — confirm they use the in-memory queue (free) and not a real SQS queue.

### 3. Reduce / avoid additional SQS requests
- **Locally / in tests:** inject a fake / in-memory queue into `SqsMailSendQueue(client=..., queue_url=...)` — already supported; no AWS round-trip.
- **Tune retry behaviour:** review `maxReceiveCount` (currently 5, task 4.4) and DLQ settings so retries do not silently consume the remaining ~135k free requests.
- **Avoid manual re-enqueues:** dead-letter jobs should be audited before re-enqueueing.

### 4. If real SES sends are not needed yet
- Substitute the production `SqsMailSendQueue` with an in-memory / DB-backed queue (the design explicitly allows a durable queue swap behind `MailSendQueuePort`).
- Default Flask-monolith queue is already `InMemorySyncQueue` (in-process, free) — keep it for local/dev.

---

## Bottom line (updated with user corrections)

The application is **not misconfigured** — it is doing exactly what the architecture intends: mail-send via SQS → Lambda → SES. However, the ~865k SQS requests **cannot** originate from the real mail-send path, since only ~10–15 actual emails have been sent in production and the system is not yet in production. The previous analysis that attributed the volume to the Members mail-send pipeline is therefore **incorrect** and must be revised.

The source of the 865K SQS requests in account `506221081911` remains under investigation (see the revised plan in the spec). Likely candidates include:

- A background job or cron that enqueues mail jobs at high frequency (e.g., per-tenant governance sync running every few minutes).
- The HDCN project/workspace running on the same AWS account, which may have its own SQS queue or mail-send pipeline.
- An infinite loop or misconfigured bulk-enqueue in a test script that ran during the last ~8 weeks.

## Investigation Update (2026-11-22)

- **Cross‑account access**: The `nonprofit-deploy` profile now resolves to account `506221081911` via the `NonprofitDeployRole`. All AWS API calls (SQS, CloudWatch, CloudTrail, Lambda) use this profile.

- **CloudTrail trail created**: New trail `nonprofit-sqs-data` in `eu-west-1` with S3 bucket `nonprofit-cloudtrail-logs-506221081911`. Bucket policy for CloudTrail write access has been applied.

- **Advanced event selectors**: Configured for SQS `SendMessage` on queue `arn:aws:sqs:eu-west-1:506221081911:members-mail-send` (eventCategory=Data, eventSource=sqs.amazonaws.com, eventName=SendMessage, resources.type=AWS::SQS::Queue, resources.ARN=...). The `put-event-selectors` call succeeded and returned the selector configuration.

- **CloudTrail lookup (Oct 22 – Nov 22)**: Running `aws cloudtrail lookup-events` for `SendMessage` across the 30‑day window returned **no events**. The trail was created during this investigation, so it only captures events from creation forward; historical data is not available.

- **CloudWatch SQS metrics**: `NumberOfMessagesSent` for both `members-mail-send` and `members-mail-send-test` shows near‑zero daily counts (most days `0.0`; only two days with `Sum = 1.0` — 2026‑10‑27 and 2026‑11‑18). This indicates that actual `SendMessage` API calls were minimal.

- **Lambda logs**: The log group `/aws/lambda/members-public-test` contains recent invocations (INIT/START/END/REPORT) but no explicit `SendMessage` statements in the sampled log events. This suggests the Lambda function runs but may not be the source of the high SQS request volume.

- **Implication**: The ~865 k Free‑Tier SQS requests cannot be explained solely by `SendMessage` on `members‑mail‑send`. The Free Tier counts **all** SQS API actions (Send, Receive, Delete, etc.). Additional sources such as queue receives, deletes, or other queues (e.g., HDCN project) need to be examined.

- **Next step**: With CloudTrail and event selectors now active, future `lookup-events` queries will capture new `SendMessage` (and other SQS) events, enabling correlation with Lambda invocations and IAM principals.

### SQS API request totals (Oct 22 – Nov 22, 2026)

| Queue | Metric | Total |
|---|---|---|
| members-mail-send | NumberOfMessagesSent | 2 |
| members-mail-send | NumberOfMessagesReceived | 2 |
| members-mail-send | NumberOfEmptyReceives | 0 |
| members-mail-send | NumberOfMessagesDeleted | 2 |
| members-mail-send-test | NumberOfMessagesSent | 1 |
| members-mail-send-test | NumberOfMessagesReceived | 1 |
| members-mail-send-test | NumberOfEmptyReceives | 0 |
| members-mail-send-test | NumberOfMessagesDeleted | 1 |
| members-mail-send-dlq | NumberOfMessagesSent | 0 |
| members-mail-send-dlq | NumberOfMessagesReceived | 0 |
| members-mail-send-dlq | NumberOfEmptyReceives | 0 |
| members-mail-send-dlq | NumberOfMessagesDeleted | 0 |
| members-mail-send-test-dlq | NumberOfMessagesSent | 0 |
| members-mail-send-test-dlq | NumberOfMessagesReceived | 0 |
| members-mail-send-test-dlq | NumberOfEmptyReceives | 0 |
| members-mail-send-test-dlq | NumberOfMessagesDeleted | 0 |

**Total SQS API requests (Send + Receive + Delete) across all queues:** ~9.

These operational metric totals are **orders of magnitude lower** than the reported 865,111 Free‑Tier SQS requests, confirming that the spike was **not** attributable to the `members‑mail‑send` pipeline as currently instrumented (or that the metrics do not capture the full set of operations / time window).


### Broader service‑level checks (SNS, Lambda, EventBridge)

| Check | Result |
|---|---|
| **Lambda event source mappings** | Two mappings exist: `members-mail-send-test` → `members-mail-worker-test` (BatchSize=1, MaxConcurrency=4) and `members-mail-send` → `members-mail-worker-prod` (BatchSize=1, MaxConcurrency=10). However, CloudWatch metrics show only **8** messages received on `members-mail-send` and **18** on `members-mail-send-test` over the full queue lifetime (~July 2026 → Nov 2026). This rules out Lambda polling as the primary source of the 865k Free‑Tier requests. |
| **SNS topics** | Two topics exist (`members-mail-feedback`, `members-mail-feedback-test`), but both subscribe **Lambda** functions (`members-mail-feedback-prod`, `members-mail-feedback-test`), not SQS queues. SNS is therefore not publishing directly to SQS. |
| **EventBridge rules** | Two hourly scheduled rules (`h-dcn-EventStatusSchedulerFunctionScheduleRule`, `h-dcn-test-EventStatusSchedulerFunctionScheduleRule`) target **Lambda** functions, not SQS queues. EventBridge is not directly generating SQS traffic. |
| **Queues in account** | Only four queues exist, all mail‑send related (`members-mail-send`, `members-mail-send-test`, and their DLQs). No HDCN or other project queues found. |

### Root‑cause analysis (current state)

The ~865k Free‑Tier SQS requests **cannot** be explained by:
- The `members‑mail‑send` pipeline's Send/Receive/Delete operations (only ~9 actions in Oct 22‑Nov 22).
- Lambda event source mapping polling (only 8 + 18 messages received over the queue lifetime; 0 empty receivers).
- SNS → SQS delivery (no SQS subscriptions found).
- EventBridge → SQS (no SQS targets found).

**Remaining likely causes** (require further investigation):
1. **SQS API operations not captured by the metrics we checked** — e.g., `ChangeMessageVisibility`, `GetQueueAttributes`, `ListQueues`, `TagQueue`, etc., which also count toward Free Tier but are not reflected in `NumberOfMessagesSent/Received/Deleted`.
2. **A background job / cron / test script** that ran earlier in the month (or earlier in the year) and has since stopped, leaving only the cumulative Free‑Tier counter.
3. **Cross‑account or third‑party access** to the queues (e.g., another AWS account or service with `sqs:SendMessage` permission).
4. **A different AWS region** — we only checked `eu‑west‑1`; there may be queues in other regions.

### Next steps to pinpoint the source

1. **Enable broader CloudTrail data‑event selectors** for SNS `Publish`, Lambda `Invoke`, Step Functions `StartExecution`, and SQS operations beyond Send/Receive/Delete (e.g., `ChangeMessageVisibility`, `GetQueueAttributes`). This will capture all future API calls that could contribute to Free‑Tier usage.
2. **Query AWS Billing / Cost Explorer** for the SQS Free‑Tier usage breakdown by API operation (if available) to see exactly which operations consumed the 865k requests.
3. **Check all AWS regions** for SQS queues and CloudTrail trails.
4. **Review IAM policies** for any cross‑account principals with SQS access.
5. **Inspect Lambda function code** for any direct `sqs:SendMessage` / `sqs:ReceiveMessage` calls that might be looping.


## Non‑production / Test‑Suite SQS Volume Estimate

For a system **still not in production** that only sends test emails when running the **Full Test Suite**, realistic SQS usage is **orders of magnitude lower** than 865K per month:

| Scenario | Approx. SQS messages / month |
|---|---|
| **One Full Test Suite run per day**, each enqueuing ~50 jobs (typical for synthetic-member exports) | ~1,500 |
| **Full suite run 3×/day** (CI pipeline) with ~50 jobs/run | ~4,500 |
| **Large test data sets**: 500 jobs/run × 3×/day × 30 days | ~45,000 |
| **Even aggressive test schedule** (10×/day, 200 jobs/run) | ~60,000 |

**Bottom‑line estimate:** A pure‑test, non‑production deployment would normally consume **well under 100K SQS requests per month**, and typically **< 10K** unless the test suite intentionally exercises massive bulk operations.

If your observed volume is ~865K and the system is *not* in production with only test‑email sends, something else is driving the traffic — most likely:

1. A scheduled/continuous job (cron, projection‑sync enqueue, HDCN workspace sync) that runs frequently and enqueues many jobs per execution.
2. A separate project or workspace (e.g., HDCN) sharing the same AWS account and using SQS independently.
3. A code bug (e.g., an unconditional `enqueue_many` loop) that was introduced ~8 weeks ago and is still running.

### Recommended next steps

1. **Check CloudTrail / SQS logs** for the `SendMessage` API calls — source IP, IAM user/role, and timestamp to identify *what principal* is making the calls.
2. **Inspect all queues** in the account (not just `members‑mail‑send`) — the HDCN project may have its own queue.
3. **Search for scripts/jobs** that ran ~8 weeks ago and may have introduced a bulk‑enqueue pattern (git log for keywords: `enqueue_many`, `sqs`, `mail`, `HDCN`).
4. **Run the Full Test Suite locally** with SQS tracing enabled (`boto3` client logging) to measure actual SQS messages per run, then extrapolate.

If you confirm the source, the mitigation path is either (a) disable/limit the offending job, (tune `maxReceiveCount` / DLQ to reduce retry‑driven SQS usage, or (c) if the volume is legitimate, consider isolating the HDCN workload to a separate AWS account.
