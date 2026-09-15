# Migration Plan — Move myAdmin's AWS Footprint to the Nonprofit Account

> Scope: bring the AWS-resident parts of **myAdmin** into the H-DCN **nonprofit
> account (506221081911, eu-west-1)**. The **Railway backend (Flask) and its MySQL
> database stay exactly where they are** — only its AWS resources move and its config
> is repointed. Companion to `myadmin_as_base.md`. This is a plan, not an execution;
> no infrastructure has been changed.
>
> **Settled model:** myAdmin is the platform base, evolved in place; additional apps
> (e.g. the h-dcn domain — the `members`, `events`, `webshop` modules on one shared
> SAM stack) are imported as SAM-backed **modules**. This document is
> **one step** of that evolution — the AWS-footprint move — and its Cognito parts
> follow the two-pool identity decision:
>
> 1. **Identity is two audience-split pools, and identity does NOT live in the
>    nonprofit account.** Generic services (S3, SNS, DynamoDB, SES, Secrets) move to
>    the nonprofit account as planned. **Cognito is the deliberate exception** — it
>    lives in the tenant-neutral **identity account** (the repurposed personal
>    account). So "move myAdmin's pool into the nonprofit pool" does not apply.
> 2. **myAdmin's existing pool `eu-west-1_Hdp40eWmu` is Pool A** (admin/staff),
>    staying where it is. There is **no myAdmin→H-DCN user migration** and no forced
>    reset/re-registration of myAdmin users. **Pool B** (end-users) is a new, clean
>    pool created fresh. See `second_thoughts.md`, "Identity model rethink" and
>    "Mapping onto current pools".
>
> The S3 / SNS / DynamoDB / Railway-repoint phases are standard infra work.

## Place in the roadmap (the roadmap leads)

`overall_roadmap.md` is the leading index of all workstreams; this document is the
full detail for **one** of its steps. The mapping is explicit:

- **This whole plan = roadmap step S6** ("Move myAdmin's AWS footprint to the
  nonprofit account"), on the roadmap's **infra track**.
- **Phase 6 of this plan = roadmap step S10** ("Decommission the old AWS account
  resources"), the roadmap's last step, whose prereq is "S6 stable."

**Related roadmap steps this plan depends on or touches:**

- **S3 — Define + populate the shared tenant/role claims (two-pool,
  audience-split).** The two-pool identity decision (Pool A = existing myAdmin pool;
  Pool B = new end-user pool) must land before this plan's Cognito-touching gates
  (Gate 1, Phase 4). S3 owns that decision; this plan only *confirms and applies* it.
- **S2 — Verify JWT signatures on both planes.** This plan assumes myAdmin's side of
  S2 is already true — myAdmin verifies signatures via
  `backend/src/auth/jwt_verifier.py` (issuer + app-client-ID checks). The move must
  not regress that: after repointing, Pool A's issuer/JWKS must still verify. The
  SAM-module side of S2 is separate roadmap work, not part of this move.

Each gate/phase below is tagged with the roadmap step it belongs to or depends on. If
the roadmap and this plan ever disagree, the roadmap wins and this plan is updated to
match (per the roadmap's keep-governance-current rule).

## Guiding rules (from the H-DCN guardrails)

- Never put the Cognito pool, DynamoDB tables, or S3 **data** bucket under
  CloudFormation without `DeletionPolicy: Retain` — a prior deploy deleted prod data
  this way.
- Never use `--delete` or `rm --recursive` against a data bucket. Back up before any
  data move.
- Every data move is **copy → verify → cut over → keep old until proven →
  decommission**. Never move-in-place.
- Use the `nonprofit-deploy` profile for automated ops in 506221081911.

## Scope: what actually has to move (verified)

myAdmin's AWS footprint is small and entirely env-var driven (no hardcoded account
IDs in code — values live in `.env`):

| Service | What | Difficulty |
| --- | --- | --- |
| **Cognito** | User pool + app client | **Does not move** — the pool stays in the identity account and is Pool A; no user/password/passkey migration |
| **S3** | One shared bucket (`S3_SHARED_BUCKET`) — invoices, branding, templates | Medium — real tenant data, copy carefully |
| **DynamoDB** | Landing pages, tenant slugs, media assets (small tables) | Medium — copy or recreate + migrate |
| **SNS** | One topic (`myadmin-notifications`) | Trivial — recreate |
| Region | Already `eu-west-1` | None — same region, no cross-region work |

Two facts that make this easier:
- **All AWS resources are `.env`-driven** (`COGNITO_USER_POOL_ID`,
  `COGNITO_CLIENT_ID/SECRET`, `SNS_TOPIC_ARN`, `S3_SHARED_BUCKET`, `AWS_REGION`).
  Repointing Railway is mostly a config change, not a code rewrite.
- **myAdmin already verifies JWT signatures** (`backend/src/auth/jwt_verifier.py`
  checks issuer + app client ID) — it is already close to the verified-token ideal.
  *(Roadmap **S2** — myAdmin's half is already satisfied; the move must not regress
  it: Pool A's issuer/JWKS must still verify after Phase 5.)*

## The one hard part: Cognito (largely dissolved by the two-pool decision)

Everything except Cognito is "create in nonprofit, copy data, flip the env var."
Cognito used to be the hard part because user pools cannot be exported with passwords
(hashes do not come out) and passkeys/WebAuthn are bound to the pool (RP ID + pool)
and do not transfer — so any plan that *moved* myAdmin's users into another pool
implied a forced reset/re-registration.

**Settled position: don't move myAdmin's users at all.** *(This follows directly from
roadmap **S3** — the two-pool, audience-split identity decision.)* myAdmin's existing
pool `eu-west-1_Hdp40eWmu` **is Pool A** (admin/staff) and stays in place in the
identity account. No export, no password/passkey migration, no forced reset for
myAdmin users. Pool B (end-users) is created fresh and clean. This retires the
migration's single biggest risk.

Gate 1 below is therefore not a "which pool survives" decision; it is inventory +
confirming the two-pool mapping.

---

## Phases and gates

Each gate must be satisfied before the next phase starts. You can stop between any two
phases in a working state.

### Gate 1 — Inventory + confirm the two-pool mapping (do first, no infra changes)

> **Roadmap:** part of S6; **depends on roadmap S3** (two-pool identity decision).

- [ ] Confirm exact resource names in myAdmin's **current** account: bucket name, SNS
      topic ARN, and the DynamoDB table names (landing pages, tenant slugs, media
      assets).
- [ ] **Confirm the identity mapping (no migration):** myAdmin's pool
      `eu-west-1_Hdp40eWmu` stays in place and is **Pool A** (admin/staff); it is NOT
      moved into the nonprofit account. Pool B (end-users) will be a new, clean pool
      created separately.
- [ ] Confirm the Cognito account boundary: identity (Pool A, Pool B) lives in the
      tenant-neutral **identity account**; only S3/SNS/DynamoDB/generic services move
      to nonprofit.
- [ ] Confirm/define the Railway→nonprofit access identity (least-privilege IAM
      role/user scoped to just myAdmin's bucket, topic, and tables), plus Railway's
      access to the Pool A pool in the identity account.

### Phase 2 — Recreate the easy resources in nonprofit (low risk)

> **Roadmap:** S6 (infra track).

- [ ] **SNS**: create `myadmin-notifications` topic in 506221081911; note new ARN.
- [ ] **S3**: create the shared bucket in nonprofit (versioning on). Do NOT reuse the
      H-DCN data bucket `h-dcn-data-506221081911` — keep myAdmin's bucket separate
      (bucket-separation guardrail).
- [ ] **DynamoDB**: create the myAdmin tables in nonprofit (PAY_PER_REQUEST), managed
      outside CloudFormation or with `DeletionPolicy: Retain`.
- [ ] Verify each resource exists and is reachable with the `nonprofit-deploy`
      profile.

### Phase 3 — Copy the data (copy-verify, keep originals)

> **Roadmap:** S6 (infra track).

- [ ] **S3**: copy bucket contents old→new (`aws s3 cp`/`sync` **without**
      `--delete`). Back up first. Verify object counts and a sample of files.
- [ ] **DynamoDB**: copy items old→new (scan-and-write script, or on-demand
      backup/restore). Verify item counts per table.
- [ ] Keep all originals intact — no deletion in this phase.

### Phase 4 — Cognito (no migration; keep Pool A in place)

> **Roadmap:** S6, resting on the **S3** identity decision (two-pool) and assuming
> **S2** (myAdmin verifies signatures) holds; Pool B is separate roadmap work (S3),
> not part of this move.

Under the two-pool model there is no myAdmin user migration and no pool recreation.
Pool A is myAdmin's existing pool `eu-west-1_Hdp40eWmu`, staying in the identity
account.

- [ ] Confirm Pool A (`eu-west-1_Hdp40eWmu`) is left in place — no export, no user
      migration, no forced password/passkey reset.
- [ ] (Ties into `myadmin_as_base.md`) confirm the Pool A token claims myAdmin needs
      (`cognito:groups`, `custom:tenants`, entitlement projection) are present and
      correct in this pool. *(S3 claim contract.)*
- [ ] (S2) Confirm the JWT verifier still validates Pool A tokens against the pool's
      issuer/JWKS after any app-client change — no regression of signature
      verification.
- [ ] Note Pool B (end-users) as a separate, later workstream — a new clean pool, not
      part of this AWS-footprint move. (See roadmap S3.)
- [ ] Decommission only the genuinely legacy pools (`eu-west-1_OAT3oPCIm`,
      `eu-west-1_VtKQHhXGN`, `eu-west-1_fcUkvwjH5`) — never Pool A.

### Phase 5 — Repoint Railway (config only, Railway stays put)

> **Roadmap:** S6 (infra track) — the cutover that makes S6 "done."

- [ ] Update myAdmin's Railway `.env`: `SNS_TOPIC_ARN`, `S3_SHARED_BUCKET`,
      `AWS_REGION`, and the nonprofit AWS credentials/role. The Cognito vars
      (`COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_CLIENT_SECRET`) point at
      Pool A `eu-west-1_Hdp40eWmu` and are **unchanged** — identity stays in the
      identity account, so only the generic-service endpoints repoint to nonprofit.
- [ ] Deploy on Railway; run smoke tests: login (S2 — a verified Pool A token still
      passes signature/issuer checks), an S3 read/write, an SNS send, and a
      DynamoDB-backed feature (landing page / tenant slug / media asset).
- [ ] Verify no code still points at the old account.

### Phase 6 — Soak, then decommission (final, irreversible)

> **Roadmap: this is step S10** ("Decommission the old AWS account resources"), not
> S6 — its prereq is "S6 stable in production." Kept here because it operates on the
> same resources.

- [ ] Run on nonprofit resources for a defined soak period; watch logs/errors.
- [ ] Only after stable: decommission the old account's bucket/topic/tables. **Not the
      Cognito pool** — Pool A (`eu-west-1_Hdp40eWmu`) stays live in the identity
      account and is never torn down here.
- [ ] Final backup of old data before deletion.

---

## Risk flags

1. **Cognito user migration is not a risk for this plan.** Because Pool A =
   myAdmin's existing pool stays in place, there is no export, no password/passkey
   migration, and no forced reset. The moving parts here are just S3/SNS/DynamoDB,
   which are routine. (Standing up Pool B is a separate roadmap workstream, not this
   AWS-footprint move.)
2. **Railway → nonprofit credentials.** Railway uses the old account today. It needs a
   least-privilege identity in nonprofit scoped to only myAdmin's resources. Follow
   H-DCN profile conventions.
3. **The data-bucket guardrail applies to myAdmin's bucket once in nonprofit** — no
   `--delete`, back up before moves.
4. **Keep myAdmin's bucket separate** from `h-dcn-data-506221081911`. Two distinct
   data buckets in one account; never cross them.
5. **This is production data.** Copy-verify-cutover-keep-old for every resource; never
   move-in-place.

## What this plan explicitly does NOT do

- Does not move or change the Railway Flask backend or MySQL — they stay put.
- Does not merge datastores (admin/finance stays MySQL, SAM modules stay DynamoDB).
- Does not change how myAdmin hosts modules — that is S1 (the SAM-module contract), a
  separate step.
- Does not implement the unified token/entitlement projection — that is the
  architectural work in `myadmin_as_base.md`, which can proceed independently on Pool
  A (`eu-west-1_Hdp40eWmu`).
- Does not stand up Pool B (the end-user pool) — that is a separate roadmap workstream
  (S3), not part of this AWS-footprint move.

## Suggested first concrete action

Complete **Gate 1** only: inventory the exact resource names in myAdmin's current
account and confirm the two-pool mapping (Pool A = existing pool stays put; only
generic services move to nonprofit). With the pool-migration question retired, the
rest of the plan is the routine S3/SNS/DynamoDB move plus a Railway config repoint.
