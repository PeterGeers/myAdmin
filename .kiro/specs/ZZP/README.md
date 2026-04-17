# ZZP Module Spec

## Reading Order

1. **requirements.md** — User stories and acceptance criteria (22 requirements)
2. **design.md** — Architecture, database schema, API contracts, service layer, frontend design
3. **tasks.md** — Phased implementation plan with checkboxes (18 phases)

## Supporting Files

- **design-parameter-enhancements.md** — Design addendum for Phases 11–16 (Reqs 16–22)
- **zzp ideas.md** — Original brainstorm (Dutch) covering all ZZP administration needs
- **comments.md** — Review comments and open questions

## Status

| Document     | Status                                                   |
| ------------ | -------------------------------------------------------- |
| Requirements | ✅ Complete (22 requirements)                            |
| Design       | ✅ Complete (architecture, DB, APIs, services, frontend) |
| Tasks        | ✅ Complete — Phases 1–9 core, Phases 11–17 enhancements |

### Implementation Summary

- **Phases 1–9**: Core ZZP module — database, contacts, products, invoices, booking, PDF, email, credit notes, payment checking, time tracking, recurring invoices, frontend pages, integration tests
- **Phase 10**: Future — advanced time tracking input (timesheet import, calendar import) — not started
- **Phase 11**: Parameter table column filtering (Req 16) — complete
- **Phase 12**: Ledger parameters & invoice revenue account (Reqs 17, 18, 19) — complete
- **Phase 13**: Invoice PDF header details & branding namespace (Req 20) — complete
- **Phase 14**: Locale-aware invoice formatting (Req 21) — complete
- **Phase 15**: Strict send flow with storage validation (Req 22) — complete
- **Phase 16**: Integration testing & migration (Reqs 16–22) — complete
- **Phase 17**: Merge to main & Railway deployment — complete (branding cleanup pending)

### Outstanding Items

- **Phase 10** (future): Client timesheet import (PDF/Excel) and calendar import (iCal/ICS) — deferred
- **Task 17.3.5**: Delete old `branding` namespace parameters after verification — pending manual confirmation

### Test Results (2026-04-17)

- **ZZP tests**: 611 passed, 0 failed (unit, API, integration, property-based)
- **Backend total**: 1,703 passed, 5 failed (all pre-existing, unrelated to ZZP)
- **Frontend total**: 1,052 passed, 12 failed (all pre-existing, unrelated to ZZP)
- **STR invoice generation**: 21 passed, 0 failed (no regressions from branding rename)

## Change Log

| Date       | Change                                                                                                  |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| 2026-04-15 | Requirements document created (15 requirements)                                                         |
| 2026-04-15 | Design document created (architecture, DB schema, APIs, services, frontend)                             |
| 2026-04-15 | Tasks document created (Phases 1–10)                                                                    |
| 2026-04-15 | Phase 1 complete: database migration, module registration, field config, contacts, products             |
| 2026-04-15 | Phase 2 complete: invoice engine, numbering, line calculations, multi-currency                          |
| 2026-04-15 | Phase 3 complete: booking helper, PDF generator, SES email, send flow                                   |
| 2026-04-16 | Phase 4 complete: credit notes, payment checking, overdue detection, debtors                            |
| 2026-04-16 | Phase 5 complete: time tracking service, routes, invoice from time entries                              |
| 2026-04-16 | Phase 6 complete: copy last invoice (recurring)                                                         |
| 2026-04-16 | Phase 7 complete: frontend types, services, hooks, shared components, i18n                              |
| 2026-04-16 | Phase 8 complete: frontend pages (contacts, products, invoices, time tracking, debtors)                 |
| 2026-04-16 | Phase 9 complete: integration tests, edge cases, error handling                                         |
| 2026-04-16 | Requirements expanded to 22 (added Reqs 16–22: filtering, ledger params, branding, locale, strict send) |
| 2026-04-16 | Design addendum created for Phases 11–16                                                                |
| 2026-04-16 | Tasks expanded with Phases 11–16                                                                        |
| 2026-04-16 | Phase 11 complete: parameter table column filtering with FilterPanel                                    |
| 2026-04-17 | Phase 12 complete: ledger parameters, revenue account on invoices, booking helper refactor              |
| 2026-04-17 | Phase 13 complete: zzp_branding namespace, PDF header details, template registration                    |
| 2026-04-17 | Phase 14 complete: Babel locale-aware formatting (dates, currency, numbers)                             |
| 2026-04-17 | Phase 15 complete: strict send flow with storage health check, soft email failure                       |
| 2026-04-17 | Phase 16 complete: integration tests, database migrations, final checkpoint                             |
| 2026-04-17 | Phase 17 complete: merged to main, Railway deployment, production smoke tests passed                    |
| 2026-04-17 | Spec marked complete — all core phases implemented and verified                                         |
