---
inclusion: auto
---

# SAM module architecture (SAM plane) — where application logic lives

Authoritative layering rule for **SAM-backed modules** on the myAdmin platform
(React + TS frontend → API Gateway → Lambda → DynamoDB). It governs how a migrated
app (Members first, then Events/Webshop) is structured, and it is the standard the
first migration (S5) validates. Seeded from the settled design principle:
**React owns presentation, Lambda owns business/application logic, DynamoDB owns
persistence + data-level integrity.**

> Promoted to `inclusion: auto` because the S5 app migration it governs is active — this
> layering rule should always be in context, not opt-in.

## The layers (dependencies point downward only; nothing skips a layer)

```
React / TypeScript            presentation + client-side UX only
      │  DTO over HTTPS (never DynamoDB directly)
      ▼
API Gateway
      ▼
Lambda HANDLER (thin adapter) parse request · authenticate + tenant context ·
      │                       authorize (entitlement + regional) · shape HTTP response
      ▼
Application / domain SERVICE  business rules · validation · authorization ·
      │                       workflows · orchestration  (storage-agnostic, testable)
      ▼
Repository                    the ONLY code that talks to DynamoDB
      ▼
DynamoDB                      persistence + data integrity (keys/indexes, conditional
                              writes, transactions, atomic counters, tenant scoping)
```

**Golden rule:** the Lambda **handler is an adapter, not the logic**. Substantial
business logic never lives in the handler — it lives in application/domain services the
handler calls. This keeps handlers small and lets the same rules be reused by multiple
APIs, jobs, or event handlers.

```python
# handler = adapter
def handler(event, context=None):
    command = parse_request(event)          # + authenticate + tenant context
    result = order_service.create_order(command)   # all logic here
    return to_http_response(result)
```

## Responsibility matrix (who owns what)

| Concern | React | Lambda (handler→service) | DynamoDB |
| --- | :---: | :---: | :---: |
| UI behaviour / navigation / loading+error states | ✅ | | |
| Formatting, display sort/filter, optimistic UI | ✅ | | |
| Form validation | ✅ (immediate feedback) | ✅ (**authoritative**) | |
| **Business rules** | | ✅ | |
| Price / calculation / workflow / orchestration | | ✅ | |
| **Authorization** (entitlement, roles) | | ✅ | ✅ (supporting conditions) |
| **Tenant access / scoping** | | ✅ (context) | ✅ (`tenant_id` key + `LeadingKeys`) |
| Data integrity / uniqueness / atomicity | | | ✅ (conditional writes, transactions) |
| Data relationships / access-pattern modelling | | ✅ (repository) | ✅ |
| Query optimisation (keys/GSIs) | | | ✅ |
| Persistence | | | ✅ |

## Non-negotiable rules

1. **Never trust React to enforce a business rule.** A client can bypass the frontend
   entirely. Validation may be **duplicated** — React for immediate feedback, Lambda for
   the **authoritative** check — and that is *good* duplication (different purposes), not
   a smell. The authoritative decision is always server-side.
2. **DynamoDB is not a business-rule engine.** It protects *data* — invariants, atomicity,
   uniqueness — via conditional expressions and transactions (e.g. `Update stock WHERE
   stock >= requested` guards the invariant even under concurrent invocations). Business
   *policy* stays in the application service.
3. **The handler is thin.** Parse → authenticate/tenant-context → authorize → delegate →
   respond. No domain logic, no direct DynamoDB access in the handler.
4. **The domain/application service is storage-agnostic.** It calls the repository through
   an interface; it does not know it is DynamoDB and it does not build HTTP responses. This
   is where reused app logic (e.g. h-dcn's regional access + membership workflow) lands.
5. **The repository is the only DynamoDB touch-point**, and it is where **tenant scoping is
   enforced** (`tenant_id` partition key + IAM `dynamodb:LeadingKeys`) — so the layers
   above cannot cross tenants even by mistake.
6. **SAM-plane tables are named `sam-<module>`** (e.g. `sam-members`), with the environment
   as a suffix (`sam-members-test`), resolved from a per-module env var (fail-fast, e.g.
   `MEMBERS_TABLE`) — **never hardcoded/synthesized**. Each module owns its own table(s)
   under this prefix, so module-plane IAM scopes to `sam-*` (defense in depth over the
   `tenant_id` LeadingKeys). The env token is a suffix, never a prefix, so the `sam-*` match
   holds. See `23-aws-accounts.md`.

## How this composes with the rest of the platform

- **Auth/entitlement plug in at the handler layer:** the vendored `sam/shared` toolkit
  (verified JWT → `get_verified_claims`/`get_groups` + `get_entitlements`/`has_capability`)
  is adopted **once** at the edge — never re-implemented per route/handler.
- **Fixed vs. variable fields live in the domain layer:** the field-resolution service
  merges the platform **base registry** (fixed personal/membership fields) with the
  **per-tenant overlay** (variable club fields, via `tenant_template_config`/field-config),
  and serves the resolved config to a presentation-only React frontend.
- **Tenancy lives in the repository/data layer:** `tenant_id` PK + `LeadingKeys`, one place.

## Why generic (reusable across app migrations)

Only the **application/domain service** is app-specific. The **frontend contract**, the
**handler edge** (auth + entitlement + tenant context), and the **repository/DynamoDB
tenancy** are platform-standard. Migrating the next app is therefore "write its domain
services + repository; reuse the edge and tenancy" — which is exactly what the Members
Go/No-Go pilot (`.kiro/specs/multi-tenant/s5-members-first-migration/`) is meant to prove.

## References

- `20-platform-architecture.md` (two-plane platform, module contract, projection),
  `22-authentication.md` (verified-JWT), `31-backend-database-flask-mysql.md`, `23-aws-accounts.md`.
- `.kiro/specs/multi-tenant/s1-prepare-platform/module-contract.md` (the four seams).
- `.kiro/specs/multi-tenant/s5-members-first-migration/members-wireframe.md` +
  `migration-plan.md` (the first app this governs).
- **Deploying a SAM app (codified, not hand-typed):** each app has a committed
  `samconfig.toml` + an OIDC CI workflow; deploy via `sam deploy --config-env <env>` (never
  inline `--parameter-overrides` / `--stack-name`). See `sam/members/samconfig.toml` +
  `.github/workflows/deploy-sam-members.yml`, and `sam/pretokengen/DEPLOY.md` +
  `deploy-sam-pretokengen.yml` (spec `s5e-codify-sam-deploys`).
