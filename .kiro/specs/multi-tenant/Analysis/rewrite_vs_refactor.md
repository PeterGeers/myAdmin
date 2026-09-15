# Rewrite vs Refactor — Multi-Tenancy Decision Analysis

> Companion to `first_thoughts.md`. That document assessed how hard it is to make
> the existing H-DCN system multi-tenant. This document weighs a different
> question: would it be easier to redevelop a similar solution as multi-tenant
> from scratch, instead of retrofitting the current one? This is analysis to
> support a decision — no code has been changed.

## The core tension

A rewrite feels easier because it compares a clean mental model of the new
system against the messy reality of the old one. But those are not equivalent
things. The existing H-DCN system is not just code — it is years of accumulated
domain knowledge encoded in places that do not survive a rewrite:

- The `regio`-based regional permission model with its specific Dutch regions and
  the exact role vocabulary.
- The DynamoDB field registries (Members, Producten, Events, Orders) that are the
  single source of truth — every quirk in those field names reflects a real
  business rule or a legacy data reality.
- The DynamoDB field-safety patterns (fields absent / null / wrong-type) that
  exist because production data is genuinely messy.
- Cognito passkey/WebAuthn + Google SSO integration, the FORCE_CHANGE_PASSWORD
  edge cases, and the Google identity-linking race condition.
- Stripe/Mollie payment flows, PDF generation, and the 8-language i18n.
- The migration scars — "a previous deploy deleted production data" is a lesson
  now encoded in guardrails, not something a fresh system starts knowing.

That knowledge is the expensive part. The code is comparatively cheap.

## What actually makes a rewrite hard here

The single-tenant coupling mapped in `first_thoughts.md` is real, but the *kind*
of coupling matters: hardcoded pool IDs, table-name fallbacks, hardcoded buckets
and logos, a flat group namespace. That is overwhelmingly **configuration and
parameterization debt**, not deep architectural rot.

The domain logic — orders, members, events, permissions — is not tangled up with
single-tenancy. It lives in ~100 small, single-purpose Lambdas.

That distinction is decisive:

- Refactoring config coupling is tedious but mechanical and low-risk.
- Re-deriving domain logic from scratch is where rewrites bleed months and
  reintroduce bugs that were already fixed.

## When a rewrite is genuinely worth it

A from-scratch multi-tenant build is worth serious consideration only if **all**
of these hold:

- The target is true pooled SaaS (Option B in `first_thoughts.md`) with many
  self-service tenants; **and**
- The foundational tech would change anyway — e.g. move off the
  client-supplied-groups auth pattern or adopt a real API framework. Note: this
  does **not** include switching to a relational DB — see "Do not switch to SQL"
  below; DynamoDB is the right fit for this serverless workload; **and**
- The existing system can keep running untouched for H-DCN while the new one is
  built in parallel (no forced cutover pressure).

Even then, the main trap is the **second-system effect**: the rewrite grows in
scope, takes far longer than estimated, and results in maintaining two systems
for a long time.

## When refactoring in place is better

Refactoring the current system wins if **any** of these hold:

- The need is 2-5 known organizations (Option A silo is then clearly the cheapest
  and safest path).
- H-DCN must keep working throughout (no dual-maintenance window is acceptable).
- Preserving the domain knowledge, field registries, payment integrations, and
  i18n without re-earning them is a priority.

## Side-by-side

| Dimension | Refactor in place | Rewrite from scratch |
| --- | --- | --- |
| Domain knowledge | Preserved | Must be re-derived (high risk of regressions) |
| Payments / i18n / SSO | Kept as-is | Rebuilt and re-tested |
| Risk profile | Incremental, reversible | Big-bang, hard to reverse |
| Tenant isolation | Retrofitted into ~100 handlers (isolation bugs are a risk) | Built in from day one (cleaner isolation) |
| Time to first tenant | Short (esp. Option A silo) | Long |
| Dual-maintenance | None | Two systems until cutover |
| Best fit | 2-5 orgs, or incremental path to SaaS | Large-scale self-service SaaS + desire to change core tech |

## Do not switch to SQL (DynamoDB is the right fit here)

An earlier draft floated "relational DB instead of the DynamoDB field-registry
approach" as a possible reason to rewrite. That is retracted. In a serverless
architecture like H-DCN's, SQL carries real cost and operational penalties that
DynamoDB does not, and the current DynamoDB approach is well-matched to the
workload.

- **Provisioned cost floor.** Provisioned RDS (Postgres/MySQL/Aurora) bills for an
  instance running 24/7 whether or not anyone uses the portal. For bursty,
  low-baseline traffic (evenings, event sign-ups, occasional admin work) you pay
  for an idle instance most of the day. DynamoDB on-demand (PAY_PER_REQUEST,
  which H-DCN already uses) bills per request and drops to near-zero when idle.
- **The connection-pool problem.** Lambda scales horizontally into many
  concurrent execution environments, each wanting its own DB connection. SQL
  databases have hard connection limits, so a spike can exhaust the pool. AWS's
  fix is RDS Proxy — another always-on, per-hour billed component. DynamoDB has
  no connection concept (it is an HTTPS API) and scales with Lambda naturally.
  The ~100-Lambda-per-endpoint architecture is exactly the pattern that fights
  SQL connection limits.
- **Aurora Serverless v2 does not fully solve it.** It has a minimum-capacity
  floor (scale-to-zero exists but with cold-resume latency tradeoffs), so a
  baseline cost remains. Better than provisioned RDS for variable load, but for
  genuinely low, spiky traffic it rarely beats DynamoDB on-demand.

The field registries already provide the schema discipline that people usually
cite as SQL's advantage. So "we would switch to relational" is **not** a valid
reason to rewrite — it would raise cost and add operational burden for this
workload.

## The strong middle path: extract, don't rewrite

There is a third option that is often the right answer: **extract, don't
rewrite.** Incrementally pull the domain logic (order lifecycle, permission
model, field registries) into tenant-agnostic modules, fix the auth layer
properly, and add the tenant dimension as you go.

This keeps the working system, keeps the domain knowledge, and arrives at a
multi-tenant architecture without a big-bang cutover. It captures most of the
"clean core" benefit of a rewrite while carrying far less risk.

## The one honest argument for starting fresh

If the system were rebuilt as multi-tenant from day one, there would be no need
to retrofit tenant isolation into 100 handlers or migrate live production tables
— and getting tenant isolation slightly wrong in a retrofit is a genuine
security risk. That argument is real.

But it is an argument for building the **new tenant-aware core** cleanly — not
for throwing away payments, i18n, field registries, and Cognito integration that
already work.

## Recommendation

Lean **against** a from-scratch rewrite unless the explicit target is
large-scale self-service SaaS *and* there is existing dissatisfaction with the
underlying architecture (particularly the auth layer). The single-tenant
problems in this codebase are mostly parameterization, which refactoring handles
well and safely.

Preferred ordering:

1. **2-5 known orgs** → Option A (silo / stack-per-tenant). Refactor config,
   remove hardcoded fallbacks. Cheapest and safest.
2. **Path toward SaaS, keep H-DCN running** → extract-don't-rewrite. Fix the auth
   layer first, then introduce the tenant dimension incrementally.
3. **Large-scale SaaS + wanting new core tech** → only then consider a fresh
   build, and even then rebuild the tenant-aware core cleanly while reusing the
   proven integrations where practical. Keep DynamoDB — do not migrate to SQL
   (see "Do not switch to SQL").

## Multi-tenancy on DynamoDB (cheaper than the SQL equivalent)

Because DynamoDB stays, the pooled model (Option B in `first_thoughts.md`) is
both well-trodden and cost-efficient:

- **Composite key.** `PK = tenant_id`, `SK = <existing id>` (e.g. `member_id`). A
  `Query` on the partition key returns exactly one tenant's data — cleaner and
  cheaper than today's full-table `scan()` + in-memory `regio` filter.
- **Isolation via IAM.** DynamoDB supports leading-key conditions
  (`dynamodb:LeadingKeys`), so an IAM policy can restrict access to items whose
  partition key matches the caller's tenant — enforced at the AWS layer, not just
  in application code.
- **Cost stays on-demand.** No per-tenant instance floor. Adding a tenant adds
  request volume, not a fixed monthly cost. This is what makes both the silo
  (Option A) and pooled (Option B) models economically viable here.

## Hard prerequisite either way

Regardless of rewrite vs refactor, the auth layer must be fixed before any
pooled/shared-tenant model is safe: real JWT signature verification and dropping
trust in the client-supplied `X-Enhanced-Groups` header. In a multi-tenant
system, a spoofed tenant/group claim is a cross-tenant data breach. See
`first_thoughts.md` §1 (Auth) for the specifics.
