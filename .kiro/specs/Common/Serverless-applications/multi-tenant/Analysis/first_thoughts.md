# Multi-Tenancy Feasibility — First Thoughts

> Initial analysis of how difficult it would be to make the H-DCN system
> multi-tenant. This is an exploratory assessment based on reading the current
> auth layer, SAM template, data model, handlers, and frontend config. No code
> has been changed.

## Short answer

Making H-DCN multi-tenant is a **large, high-risk undertaking** — not a weekend
refactor. It is not architecturally impossible, but the system was built
end-to-end on the assumption of exactly one organization, one Cognito pool, one
set of DynamoDB tables, in one AWS account and region. There is **no tenant
identifier anywhere** in the data model, request path, auth, or frontend today.
Multi-tenancy therefore means threading a "tenant" concept through every layer
that currently has a single hardcoded value.

The difficulty depends heavily on *which* multi-tenancy model is chosen.

## Where single-tenant is baked in

### 1. Auth (the hardest part)

- One Cognito pool + one app client ID (`eu-west-1_fcUkvwjH5` /
  `6jhvk853b0lfg9q1m861qs0cug`), hardcoded as fallbacks in `aws-exports.ts`,
  `AuthProvider.tsx`, `template.yaml`, CI, and various scripts.
- The permission model in `auth_utils.py` uses a **flat, global Cognito group
  namespace** — roles like `Members_CRUD` and Dutch region roles
  (`Regio_Utrecht`, `Regio_Limburg`, ...). Every user across a hypothetical
  second org would land in the same group namespace and collide. The full
  vocabulary is mirrored on the frontend in `HDCNGroup` (`types/user.ts`).
- Worth flagging: `extract_user_credentials` only base64-decodes the JWT payload
  — it does not verify the signature, and it trusts an `X-Enhanced-Groups`
  header from the frontend for group membership. In a single-org internal tool
  that is a design smell; in a multi-tenant system where tenant isolation is a
  security boundary, it becomes a real cross-tenant data-access risk that would
  have to be fixed first.

### 2. Data model — no tenant key at all

- All tables (Members, Producten, Orders, Events, ...) use a single string PK
  (`member_id`, etc.) with no org/tenant attribute.
- The only scoping that exists is `regio`, and that is an *intra-org* concept
  applied by scanning the whole table and filtering in memory (`get_members`
  does `table.scan()` then filters by `member.get('regio')`). It is not a
  partition boundary and would not isolate tenants.

### 3. Backend handlers

- ~100 Lambdas, one per endpoint, each resolving its table via
  `os.environ.get('MEMBERS_TABLE_NAME', 'Members')` — env var with a
  **hardcoded single-org literal fallback**. Table selection is a single global
  set with no tenant-derived routing.

### 4. Frontend

- API base URL, data/frontend bucket names, the H-DCN logo (hardcoded full S3
  URLs), org name, org email addresses, region, and account ID are all literals
  or single build-time env values. Branding is fixed at build time, not
  per-request.

### 5. Infrastructure

- Single AWS account (`506221081911`), single region (`eu-west-1`), CORS pinned
  to `portal.h-dcn.nl`. Critically, per the project guardrails: **Cognito pool,
  DynamoDB tables, and the S3 data bucket are managed outside CloudFormation**
  because a prior deploy deleted prod data. Any multi-tenant infra automation
  has to respect that boundary.

## The realistic options (least to most invasive)

### Option A — Silo / stack-per-tenant (lowest code risk, highest ops cost)

Deploy a full copy of the stack per tenant: separate Cognito pool, separate
tables, separate buckets, separate SAM stack, separate frontend build. The code
barely changes because each deployment stays "single-tenant." The existing
`Stage`/parameter mechanism already points this direction. This gives the
strongest isolation. The cost is operational: N stacks to deploy, monitor,
migrate, and bill.

- **Effort: Moderate.** Mostly config/parameterization + removing the hardcoded
  fallbacks (which the guardrails already say should throw, not fall back).

### Option B — Pooled / shared tables with a tenant key (most code change, best economics at scale)

Add a `tenant_id` to every table (likely as a partition key, so
`PK = tenant_id`, `SK = member_id`), thread it through every handler, derive it
from a verified JWT claim, and enforce it in every query. Make the Cognito group
namespace tenant-scoped. Make the frontend load branding/config per tenant at
runtime instead of build time.

- **Effort: Large and invasive.** Touches all ~100 handlers, the auth layer, the
  data model (requires data migration scripts per the migration rules), the
  field registries, and the frontend config/branding layer. Plus the
  JWT-verification / `X-Enhanced-Groups` trust issue must be fixed first, because
  in pooled mode a spoofed tenant claim = cross-tenant breach.

### Option C — Bridge (hybrid)

Pooled tables with tenant key, but separate Cognito pool per tenant. Common in
practice. Effort sits between A and B.

## Honest take

If the goal is "serve 2-5 known organizations," **Option A (silo)** is by far
the most pragmatic given how this codebase is structured. It leans on the
parameterization that already exists, avoids a risky migration of production
tables that have already been deleted once, and keeps tenant isolation trivially
provable. The main work is disciplined config extraction and killing hardcoded
fallbacks.

If the goal is "SaaS with dozens/hundreds of self-service orgs," Option B is
required, and it should be budgeted as a multi-month effort with a hard
prerequisite of fixing the auth layer (real JWT signature verification, drop the
client-supplied groups header, tenant-scoped claims). Until that is done, pooled
multi-tenancy would not be safe.

## Key coupling points (quick reference)

1. One Cognito pool/client ID, hardcoded as fallbacks in `aws-exports.ts`,
   `AuthProvider.tsx`, `template.yaml`, CI, and scripts.
2. Flat, org-specific Cognito group namespace (roles + Dutch `Regio_*`) shared
   by all users, mirrored front and back.
3. DynamoDB has NO tenant key; `regio` is intra-org, applied via post-scan
   in-memory filtering.
4. Table names are a single global set via env vars whose fallbacks are the one
   org's literal table names.
5. Frontend API URL, buckets, logo, org name/emails, region, and account ID are
   hardcoded literals or single build-time env values.
6. Infra (region, account, buckets, hosted-UI domain, CORS origins) all pinned
   to one org in one account/region; Cognito + tables + data bucket live outside
   CloudFormation entirely.

## Relevant files

1. `backend/layers/auth-layer/python/shared/auth_utils.py` — core auth/permission
   logic; hardcodes org-specific role names and regional (`Regio_`) scoping; JWT
   group extraction shared by all handlers.
2. `backend/template.yaml` — defines the single Cognito pool/client IDs,
   single-org table-name params, buckets, region, CORS origins, and the
   manual-vs-CloudFormation resource split.
3. `frontend/src/aws-exports.ts` — frontend Amplify config with hardcoded
   pool/client ID fallbacks, hosted-UI domain, and org redirect URLs.
4. `frontend/src/types/user.ts` — enumerates the fixed org-specific Cognito
   group/role namespace including hardcoded Dutch region roles.
5. `backend/handler/get_members/app.py` — representative handler showing
   env-var + literal table fallback, full-table scan, and `regio`-based
   in-memory filtering (no tenant key).
