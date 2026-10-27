# AWS Accounts Strategy — S6 "What's Left" Audit

> **Status: authoritative consolidation (2026-10-23).** This file replaces an earlier
> draft that contradicted the settled model (it framed the move as "h-dcn → nonprofit,
> myAdmin stays on personal unchanged, one shared pool"). The settled model is the
> opposite framing and is recorded in the sources below; this document consolidates the
> scattered fragments into one "what is the end-state, and what is still left to reach it"
> view.
>
> **Sources of truth (this file summarizes them; it does not supersede them):**
> - Active rules: steering `23-aws-accounts.md` (account model, guardrails, pool inventory).
> - Roadmap index + live step statuses: `Common/Serverless-applications/multi-tenant/Analysis/overall_roadmap.md`.
> - The move runbook: `.../multi-tenant/Analysis/migration_plan.md` (= roadmap step **S6**; its Phase 6 = **S10**).
> - Identity reasoning: `.../multi-tenant/Analysis/second_thoughts.md`.
> - Decisions of record: **ADR 0003** (`docs/decisions/0003-...`, myAdmin is the platform base),
>   **ADR 0005** (two-pool identity + MySQL system-of-record + MySQL→DynamoDB projection).
> - The one executable slice specced so far: `.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit/design.md`.

---

## 1. The end-state in one line

**Everything AWS-resident moves to the nonprofit / deploy account (`506221081911`, eu-west-1)
EXCEPT Cognito, which deliberately stays in the identity / personal account (`344561557829`).**
Railway (Flask + MySQL) stays external and is the tenant system-of-record; only its AWS
resources repoint. This is roadmap **S6** ("move myAdmin's AWS footprint to nonprofit"), with
final teardown as **S10**.

This is a decision of record, not an open idea — see steering `23-aws-accounts.md` and ADR
0003/0005. Most of the platform is *already* born in nonprofit (DynamoDB, API Gateway, Lambda,
the SAM modules). What remains is the myAdmin/Flask-plane AWS footprint plus the `jabaki.nl`
public-pages hosting slice.

### Why Cognito is the exception (not an oversight)

From `second_thoughts.md`: identity is hosted in a tenant-neutral account that is *yours*, not a
tenant's; the incoming portal is greenfield (one real user, `webmaster@h-dcn.nl`), so there is no
painful live-user/passkey migration to force the pool to move. Generic services consolidate in
nonprofit; identity is the single intentional cross-account exception. The model is **two
audience-split pools**:

- **Pool A — admin/staff** = the existing pool `eu-west-1_Hdp40eWmu` (`myAdmin`), stays in the
  identity account. Rich claims (`cognito:groups`, `custom:tenants`, `custom:entitlements`).
- **Pool B — end-users** = a NEW Essentials pool, **deferred** (addable config-only later); simple
  single-`tenant_id` claim. A *per-tenant option*, not a platform given (finance tenants have no
  end-users).

Guardrail: split identity by **audience only**, never per-tenant/per-app.

---

## 2. Roadmap position (where S6 sits)

Per `overall_roadmap.md` (the leading index; if it and this file ever disagree, the roadmap
wins):

| Step | What | Status |
| --- | --- | --- |
| S1 | Prepare myAdmin to host SAM-backed modules (module contract, ADR 0003) | ✅ Done |
| S2 | Verify JWT signatures on both planes (ADR 0004) | ✅ Done |
| S3 | Two-pool claims + MySQL system-of-record + →DynamoDB projection (ADR 0005) | ✅ Done |
| S4 | Project entitlement into the token (Pre-Token-Gen; ADR 0006) | ✅ Functions built; live Pool A trigger lands with the first migration |
| S5 | First app migration — **Members** (h-dcn) → platform, then Go/No-Go | 🚧 In progress (spec 12 is part of this) |
| **S6** | **Move myAdmin's AWS footprint to nonprofit** | **◻ Not started — this audit** |
| S7–S9 | Frontend track (React19+Vite, shared login/nav, unified SPA) | Parallel / later |
| S10 | Decommission old account resources (migration_plan Phase 6) | ◻ Last; needs S6 stable |

S6's only hard prerequisite is the **Pool A / Pool B decision from S3** — which is ✅ settled
(Pool A stays as-is; Pool B deferred). So S6 is unblocked whenever you choose to run it; the
user decision on record is to do it **after** the Members pilot (S5) proves the pattern.

---

## 3. What actually has to move (the S6 scope, verified-small)

myAdmin's AWS footprint is small and entirely `.env`-driven — no hardcoded account IDs in code —
so repointing Railway is mostly config, not a rewrite (`migration_plan.md` "Scope"):

| Service | What moves | Difficulty | Env var(s) to repoint |
| --- | --- | --- | --- |
| **Cognito** | **Nothing — stays in identity account (Pool A)** | n/a | `COGNITO_USER_POOL_ID` / `COGNITO_CLIENT_ID` / `COGNITO_CLIENT_SECRET` stay pointed at `eu-west-1_Hdp40eWmu` |
| **S3 (shared bucket)** | invoices, branding, templates | Medium — real tenant data, copy-verify | `S3_SHARED_BUCKET` |
| **DynamoDB (Flask-plane)** | landing pages, tenant slugs, media assets (small tables) | Medium — copy/recreate | (table-name vars) |
| **SNS** | one topic `myadmin-notifications` | Trivial — recreate | `SNS_TOPIC_ARN` |
| **Region** | already `eu-west-1` | None | `AWS_REGION` (already correct) |

Plus the **jabaki.nl public-pages hosting slice** (the "EXTRA" S6 explicitly calls out): the
landing-page function reads/writes a **personal-account DynamoDB table directly (no SAM API)** and
pushes **static HTML to a personal-account S3 bucket fronted by `*.jabaki.nl` CloudFront**. This
slice is entangled with live DNS + production email on the shared `jabaki.nl` zone, so it has its
**own** gated runbook — see §5.

---

## 4. "What's still on personal (`344561557829`) besides Cognito" — checklist

The concrete S6 worklist. Items below are the known personal-account residents; **re-verify live
with the `personal` profile before any apply** (sanity-check `sts get-caller-identity` first,
steering 41 — the override-ranking trap can point you at the wrong account):

- [ ] **S3 shared bucket** (`S3_SHARED_BUCKET`) — invoices/branding/templates. Copy→verify→cutover, keep old.
- [ ] **S3 public-pages bucket** `myadmin-public-pages-production` — 7 live landing-page tenant prefixes (jabaki slice; see §5).
- [ ] **CloudFront** `E28OSWC7A9O9K2` — alias `*.jabaki.nl` (jabaki slice).
- [ ] **ACM cert + CloudFront functions + KeyValueStores** backing `*.jabaki.nl` (jabaki slice, `us-east-1` control plane).
- [ ] **DynamoDB (Flask-plane)** — landing pages, tenant slugs, media-asset tables. Copy/recreate in nonprofit (PAY_PER_REQUEST, `DeletionPolicy: Retain`).
- [ ] **SNS topic** `myadmin-notifications` — recreate in nonprofit, note new ARN.
- [ ] **Railway IAM identity** — a least-privilege role/user in nonprofit scoped to only myAdmin's bucket/topic/tables (replaces the old personal-account creds).
- [ ] **KEEP on personal (do NOT move):** Cognito Pool A `eu-west-1_Hdp40eWmu`, the standing test pool `eu-west-1_xyrlzfqbl`, and `eu-west-1_fcUkvwjH5` (nonprofit H-DCN pool, kept while h-dcn runs).
- [ ] **Route53 `jabaki.nl` zone** — stays on personal; only the `*.jabaki.nl` wildcard ALIAS flips (moving the whole zone is rejected — it also carries production MX/DKIM/DMARC; see §5).

Once these are moved/repointed and soaked, the personal account is down to **Cognito only** —
the intended steady state. Final teardown of the old resources is **S10**.

---

## 5. The jabaki.nl hosting slice (already specced)

The one S6 sub-slice with an executable runbook today:
`.kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit/` (design-first; `design.md` only,
**no `tasks.md` yet**). Scope: consolidate S3 + CloudFront + ACM + CloudFront functions + KVS +
backend IAM for `jabaki.nl` from personal → nonprofit. Guiding principle: build the new stack
fully in nonprofit, verify on a non-production hostname, **flip only the `*.jabaki.nl` wildcard
alias**, keep the old personal stack as a rollback target until post-cutover verification passes.

**Why not move the whole Route53 zone:** the zone also carries production email (MX→ImprovMX,
Stripe DKIM ×6, SES DKIM ×3, SPF/DMARC); migrating the zone means recreating every record and
switching registrar nameservers — heavier and riskier. So the zone stays; only the wildcard alias
moves.

**This slice is the Phase-0.1 prerequisite** of the Members application-form-serving redesign
(spec 12): the live publish path (S3 write + CloudFront invalidation) is gated on this cutover so
SAM→S3 publish IAM is plain same-account in nonprofit (design D2, "migration-first"). Spec 12's
account-agnostic work (~85%) is done and does not wait on it.

---

## 6. Guardrails for the whole move (from `second_thoughts.md` / `migration_plan.md` / steering 23)

- **Copy → verify → cut over → keep old until proven → decommission.** Never move-in-place. This is production data.
- **Never** put a Cognito pool, DynamoDB table, or S3 **data** bucket under CloudFormation without `DeletionPolicy: Retain` (a prior deploy deleted prod data this way).
- **Never** `--delete` / `rm --recursive` a data bucket; back up before any move.
- **One-directional projection only** — MySQL is truth; the DynamoDB copy is read-only, written by the sync, never edited independently (split-brain = security incident).
- Keep myAdmin's bucket **separate** from `h-dcn-data-506221081911` — two distinct buckets, never crossed.
- Critical env vars **fail fast** (throw on missing) — no dangerous fallbacks.
- Use the `nonprofit-deploy` profile for ops in `506221081911`; verify `sts get-caller-identity` before anything that matters.

---

## 7. What this audit does NOT cover

- Standing up **Pool B** (end-user pool) — a separate roadmap workstream (S3 follow-on), not part of the AWS-footprint move.
- Moving/changing **Railway Flask + MySQL** — they stay put; only AWS endpoints repoint.
- Merging datastores — admin/finance stays MySQL, SAM modules stay DynamoDB (deliberate two-plane design).
- The **webshop** build-out — tracked separately; not a blocker for S6.

---

## 8. Suggested first concrete action

Run **Gate 1** of `migration_plan.md` only (read-only, no infra change): inventory the exact
personal-account resource names (bucket, SNS ARN, the Flask-plane table names) and confirm the
two-pool mapping. With the pool question already retired (S3), the rest of S6 is the routine
S3/SNS/DynamoDB copy + a Railway `.env` repoint, plus the separately-gated jabaki hosting slice.
