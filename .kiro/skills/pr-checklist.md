---
inclusion: auto
---

# PR Review Checklist

Use this checklist when reviewing code changes. Pull it into context with
`#pr-checklist`. It applies **platform-wide** — items cover both planes: the Flask/
MySQL plane (myAdmin) and any SAM-backed module plane (Lambda/DynamoDB). Where a rule
is plane-specific, both forms are given.

## Security

- [ ] No hardcoded secrets, API keys, or credentials.
- [ ] **Verified identity only:** JWTs are signature-verified against the originating
      Cognito pool's JWKS; no trust in unverified headers (`X-Tenant`,
      `X-Enhanced-Groups`) as a source of truth.
- [ ] **Tenant isolation maintained on every query:**
      - Flask plane (MySQL): scoped by the tenant key (`administration`).
      - Module plane (DynamoDB): scoped by `tenant_id` partition key, with IAM
        `LeadingKeys` as defense in depth.
- [ ] **Auth enforced on all new routes/handlers:**
      - Flask plane: auth + tenant decorators present (`@cognito_required` +
        `@tenant_required`), and `@module_required` where the route belongs to a
        module.
      - Module plane: API Gateway Cognito authorizer + tenant scoping in the handler.
- [ ] **Injection-safe data access:**
      - Flask plane: parameterized SQL (`%s`), never string interpolation.
      - Module plane: no unsanitized input into key/filter expressions.
- [ ] Input validation on all user-provided data.
- [ ] No sensitive data in logs or error messages.
- [ ] Critical env vars fail fast (throw on missing) — no dangerous fallbacks.

## Code Quality

- [ ] Files reasonably sized (target < 500 lines; refactor past ~1000).
- [ ] Python: functions have docstrings and type hints.
- [ ] TypeScript: proper types, no `any`.
- [ ] Error handling on all routes/handlers.
- [ ] Follows existing patterns for the plane (Flask: Blueprint routing + service
      layer; module: one-handler-per-Lambda + shared layer).
- [ ] Code lands in the plane that owns its domain (finance/admin → Flask; module
      domain → its SAM app).
- [ ] No dead code or commented-out blocks.

## Testing

- [ ] New code has tests.
- [ ] Tests use existing fixtures (`conftest.py`) and utilities; proper markers
      (unit/integration/api).
- [ ] Frontend tests use Vitest (`npx vitest run`) with the shared Chakra mock /
      `@/test-utils` pattern; never `jest.*`.
- [ ] Backend tests run per plane (Flask: `pytest tests/unit/`; module: its Lambda
      test suite).
- [ ] Identity/tenant changes validated against the **test environment** (standing
      test Cognito pool + Docker MySQL + `test_` DynamoDB), never production — see
      `aws-accounts.md` / `environments_and_testing.md`.
- [ ] Edge cases covered (empty input, invalid data, missing fields, cross-tenant
      access attempts).

## Performance

- [ ] No N+1 query patterns.
- [ ] Large result sets paginated.
- [ ] Expensive operations cached where appropriate (e.g. tenant-overlay / projection
      caches keyed by `tenant_id + version`).
- [ ] **Module (Lambda) handlers do NOT query MySQL at request time** — authorize from
      the verified token and read their own DynamoDB / the read-only projection (see
      `architecture.md`).

## Documentation & governance

- [ ] New routes/handlers documented (Flask: Swagger/Flasgger annotations).
- [ ] API changes reflected in the plane's API docs.
- [ ] Spec updated if implementing a spec task.
- [ ] **Governance kept current:** steering/ADRs updated if the change invalidates or
      introduces a rule (fold into existing steering; ADRs append-only).
- [ ] Breaking changes noted.
