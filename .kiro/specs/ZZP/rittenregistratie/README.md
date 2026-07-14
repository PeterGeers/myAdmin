# Rittenregistratie (Trip/Mileage Registration)

## Reading Order

1. **requirements.md** — User stories, acceptance criteria, scope decisions
2. **design.md** — Architecture, database schema, API contracts (TODO)
3. **tasks.md** — Phased implementation plan (TODO)

## Status

| Document     | Status                               |
| ------------ | ------------------------------------ |
| Requirements | ✅ Complete (10 active requirements) |
| Design       | ✅ Complete                          |
| Tasks        | ⏳ Not started                       |

## Context

The Rittenregistratie extends the ZZP module with trip/mileage tracking for Dutch freelancers. Key drivers:

- **Belastingdienst compliance** — proving <500 private km/year for business vehicles, or claiming €0.23/km deduction for private vehicles used for business
- **Client billing** — configurable km rates per client/contract, billable like time entries
- **Standalone access** — accessible at `/Ritten` as well as within the ZZP module

## Key Design Decisions

| Decision            | Choice                                           | Rationale                                                |
| ------------------- | ------------------------------------------------ | -------------------------------------------------------- |
| Scope               | Part of ZZP module + standalone route            | Reuses ZZP contacts, invoicing; accessible independently |
| Vehicle types       | Private-for-business + Business (bijtelling)     | Tenant-dependent, both must be supported                 |
| Multiple vehicles   | Yes                                              | Per tenant, each with type designation                   |
| Km rate             | Per client/contract, not parameter system        | More flexible for billing scenarios                      |
| Odometer            | Running total, start value required              | Belastingdienst compliance                               |
| Route presets       | Top X most-used from last 6 months               | X configurable via parameter system                      |
| Invoice integration | Yes, billable like time entries                  | Per client/contract opt-in                               |
| Export              | PDF with required fields, template-based         | Belastingdienst format compliance                        |
| Audit trail         | Full correction history                          | Legal requirement for rittenregistratie                  |
| Mobile              | Mobile-optimized quick-entry web view (PWA-lite) | Same codebase, no native app; fast entry on the road     |

## Change Log

| Date       | Change                                             |
| ---------- | -------------------------------------------------- |
| 2026-07-13 | Requirements document created (12 requirements)    |
| 2026-07-13 | Added Req 11 (mobile quick entry) and Req 12 (GPS) |
| 2026-07-13 | Req 9 removed, Req 12 moved to future, finalized   |
| 2026-07-13 | Design document created                            |
