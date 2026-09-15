# ADR 0001 — New target workspace (mysaas) seeded from analysis; legacy workspaces remain live

- Status: Accepted
- Date: 2026-09-15

## Context

Two systems are being unified into one multi-tenant platform: h-dcn (AWS SAM +
DynamoDB member portal/webshop, greenfield — only real user webmaster@h-dcn.nl) and
myAdmin (Flask + MySQL finance app on Railway, live with real tenants/data). An
early plan was to merge the two workspaces into one. That would force reconciliation
of two sets of .kiro governance, two frontends, and two backends — all written under
single-system assumptions — while both systems are live.

## Decision

Create a new, clean workspace mysaas as the target platform trunk. Seed it with the
multi-tenant analysis (.kiro/specs/multi-tenant/Analysis/) and author fresh steering
+ skills for the target. Make mysaas the definition of record (owns roadmap + ADRs).
Keep h-dcn and myAdmin as live systems that receive only migration-driven or
keep-the-lights-on changes; reflect their real changes back into mysaas governance.

## Rationale

- Governance is authored fresh for the target, not reconciled from two conflicting
  legacy sets.
- Risky construction happens in the new/greenfield space, not on the live myAdmin
  production system.
- Avoids inheriting two codebases' legacy mess before the target is defined.

## Consequences

- Risk: mysaas must be the definition of record from day one, or it becomes an
  aspirational graveyard while work stays in the old workspaces. Rule:
  target/migration work -> mysaas; keep-the-lights-on -> legacy workspace.
- Migrate in thin vertical slices; each roadmap step lands something real in mysaas.

## Supersedes

- The original roadmap step S1 ("merge the two workspaces" / S1a+S1b).
