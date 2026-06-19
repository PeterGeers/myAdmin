# Budget Module Redesign

## Status: Ready for Implementation

## Summary

Simplify the budget module from 4 pages + 4 tables + complex template system to:

- **1 preparation page** (version selection + line management)
- **1 dashboard tab** (in FIN Reports, version-driven)
- **2 tables** (versions + lines only)
- **Multiple active budgets** (no single-active-per-year restriction)

## Reading Order

1. `requirements.md` — what changes and why
2. `design.md` — architecture, API changes, UI layout, files to create/remove
3. `tasks.md` — phased implementation plan (~18h total)

## Key Decisions

| Decision                              | Rationale                                                            |
| ------------------------------------- | -------------------------------------------------------------------- |
| Drop templates                        | Unnecessary complexity; AI draft doesn't need stored template config |
| Multiple active versions              | Users may want to compare different budgets                          |
| Dashboard in FIN Reports              | It's an analytical report, not a preparation tool                    |
| Version-driven dashboard              | Year is redundant when you select a specific version                 |
| Single preparation page               | Versions/Lines are tightly coupled, no reason for separate pages     |
| Permissions: Finance_CRUD/Read/Export | Standard FIN permissions, no budget-specific ones                    |

## Change Log

| Date       | Change                        |
| ---------- | ----------------------------- |
| 2026-06-15 | Initial redesign spec created |
