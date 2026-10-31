# Specs Index & Organization Model

This directory holds all Kiro specs for myAdmin, organized by **functional area**. This index
documents the model and links to each area.

## The model

1. **Top level = functional areas only** (plus `myBacklog` and the legacy `BUGS solved`
   archive). Every spec lives under exactly one area.
2. **Status by per-area `_archive/`.** Active specs sit directly under their area; completed
   specs move to `<area>/_archive/`. Lifecycle is also recorded in each spec's `.config.kiro`
   via a `"status"` key (`active` | `done`), alongside `specId` / `specType`.
3. **Each area has a `README.md` index** listing its specs with a one-line status and links —
   the single at-a-glance map for that area.
4. **`myBacklog` stays flat** and holds unstarted candidates. A candidate **graduates** into a
   functional area (as a spec folder) when work on it starts.
5. **`git mv`** is used for relocations so history is preserved.

## Functional areas

| Area | Purpose | Index |
| --- | --- | --- |
| FIN | Financial transaction processing, reporting, tax declarations. | [FIN/README.md](FIN/README.md) |
| STR | Short-term-rental bookings, revenue/pricing, tourist tax. | [STR/README.md](STR/README.md) |
| Members | Membership config, application forms, member analytics. | [Members/README.md](Members/README.md) |
| Commerce | Public landing pages and custom domains. | [Commerce/README.md](Commerce/README.md) |
| ZZP | Sole-trader invoicing, debtors, trip registration. | [ZZP/README.md](ZZP/README.md) |
| WEBSITE | SaaS marketing/website surface. | [WEBSITE/README.md](WEBSITE/README.md) |
| support-feedback | In-app support and user feedback. | [support-feedback/README.md](support-feedback/README.md) |
| Common | Cross-cutting platform concerns (grouping of sub-areas). | [Common/README.md](Common/README.md) |

## Other top-level entries

| Entry | Role |
| --- | --- |
| `myBacklog` | Unstarted spec candidates (flat). Graduate into an area when started. **Not reorganized.** |
| `BUGS solved` | Legacy global archive of completed bug work. **Left untouched this pass.** |
| `code-quality-maintenance` | Cross-cutting code-quality/test-suite upkeep. |

## Deferred (future passes)

- **Redistribute `BUGS solved`** into each owning area's `_archive/` (large, separate pass).
- **Re-triage true status** of existing active-area specs. This pass defaults existing specs to
  `active` and only marks the one archived spec (`Common/image-asset-management/_archive/
  merge-duplicates-and-storage-500s`) as `done`.
