# ADR 0002 — myAdmin is the pattern source and admin-plane codebase, not the single trunk

- Status: Superseded by ADR 0003

- Date: 2026-09-15

> **Superseded (2026-09-15) by [ADR 0003](0003-myadmin-is-platform-base-modules-as-sam-apps.md).**
> myAdmin is now the platform base/trunk itself (evolved in place), not merely a
> pattern source for a separate `mysaas` trunk. The original text is retained below
> as the decision trail.

## Context

myAdmin already implements the multi-tenant ideas well (tenant key, tenant

governance tables, @tenant_required, provisioning, JWT verification). This makes it

tempting to use myAdmin as the base codebase everything else builds on.

## Decision

Use myAdmin as the source of multi-tenant patterns and as the admin service plane's

code (it stays Flask/MySQL, adapted into mysaas/admin/). Do NOT treat myAdmin's

codebase as the single trunk the whole platform merges into. The mysaas workspace is

the trunk. The portal domain comes from h-dcn, rebuilt tenant-aware on the

serverless/DynamoDB plane using myAdmin's patterns (not its Flask code).

## Rationale

- myAdmin is the one live production system — do risky construction on the disposable

  (greenfield h-dcn) side, not the live one.

- Making myAdmin the trunk would drag the serverless portal domain toward MySQL/Flask,

  undoing the deliberate two-plane / DynamoDB decision.

- myAdmin's ~307 backend files are mostly finance-domain logic, not reusable platform

  scaffolding — as trunk it would make the platform finance-centric.

- It would bake myAdmin's naming/steering/role vocabulary in as defaults instead of

  deciding them fresh for the platform.

## Consequences

- Reusing myAdmin's code and patterns is expected and encouraged; reusing its name

  while the original is alive is not.

- The admin plane may reuse much of myAdmin's code largely intact, as a plane within

  the platform.

## Related

- ADR 0001 (new target workspace).
