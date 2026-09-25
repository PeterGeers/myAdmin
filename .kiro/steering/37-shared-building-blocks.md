---
inclusion: auto
---

# Shared building blocks — the registry + how to build one

The platform's **reusable building blocks** (frameworks / shared components / cross-cutting
contracts) live here as a single registry, plus the convention for creating a new one. Reach for a
registered block before inventing a local variant — that is the whole point of this file.

This file is `auto`-included (not `fileMatch`) because some blocks are **full-stack** (backend +
frontend), so the registry must be discoverable whether you are editing a Lambda handler or a React
modal. It is a thin **index**: it POINTS to each block's full guide and reference implementation —
it never copies them (facts live in one place; `00-index.md`).

## The registry

| Block | Scope | Status | Guide | Reference impl |
| --- | --- | --- | --- | --- |
| Table Filter Framework v2 | frontend | Stable | `.kiro/specs/Common/Frameworks/table-filter-framework-v2/design.md` | `frontend/src/pages/ZZPInvoices.tsx` |
| API response & error standard v1.0 | full-stack | Stable | `.kiro/specs/Common/Frameworks/api-response-standard/` | SAM Members; ZZP invoice |
| Lazy edit-on-click dropdown | frontend | Planned | tbd (myBacklog) | tbd |

Scope = which plane(s) the block serves. Status = Stable (use it) · In-progress (being built) ·
Planned (don't rely on it yet). When a block changes state, update its row here.

## When to register a block here

A thing earns a row ONLY when BOTH hold:
1. it is **cross-cutting / reused across modules** (not a one-off helper for a single page), AND
2. it is **backed by a Frameworks guide** (`.kiro/specs/Common/Frameworks/<name>/`).

Pure styling conventions (button colours, dark theme, modal layout) are NOT building blocks — they
stay in `32-frontend-ui.md`. A single-use utility is not a building block — it stays with its code.

`37` registers **feature building blocks** (what you reach for when building a feature). It is NOT
an index of everything under `.kiro/specs/Common/Frameworks/` — that folder also holds **test
infrastructure** specs (`test-maintenance-framework`, `chakra-test-mock-framework`), which are owned
by the testing steering (`33-frontend-testing.md` / `34-backend-testing.md`), not registered here.
So `37` omitting them is intentional, not stale.

## How a building block is structured (the template)

Every block follows the same four-part shape (modelled on the Table Filter Framework v2). Create a
new block by producing all four:

1. **A Frameworks spec** — `.kiro/specs/Common/Frameworks/<name>/{requirements,design,tasks}.md`.
   The full contract/design/plan; the single source of truth for the block.
2. **Shared code at a discoverable path** — not buried in one module:
   - frontend: `frontend/src/shared/<area>/` (e.g. `frontend/src/shared/api/` for `ApiError` /
     `applyApiError`), or the framework's own hooks/components dir;
   - SAM backend: `sam/shared/`; Flask backend: the shared services module.
3. **A steering pointer** — a row in the registry above. If the block is SINGLE-plane and already
   has a home in a plane file (e.g. Filters in `32-frontend-ui.md`), the detailed guidance STAYS
   there and the registry row just points to it — do not duplicate.
4. **A named reference implementation** — a real page/module that demonstrates the block correctly,
   so "how do I use it" has a concrete answer.

## The blocks

### Table Filter Framework v2 (frontend · Stable)
Hybrid table filtering: text-search filters in column headers (`FilterableHeader`), dropdowns/
multi-select above the table (`FilterPanel`); hooks `useColumnFilters`, `useTableSort`,
`useFilterableTable`, `useTableConfig`. **Detailed guidance lives in `32-frontend-ui.md`** (loaded
via `fileMatch` when editing `frontend/src/**`); this registry only points to it. Full guide:
`.kiro/specs/Common/Frameworks/table-filter-framework-v2/design.md`. Reference: `ZZPInvoices.tsx`.

### API response & error standard v1.0 (full-stack · Stable)
One response envelope on every backend — success `{success:true, data}`, error `{success:false,
error, code?, params?, errors?[], reasons?[]}` — always with the real HTTP status; every handler
ends in a catch-all returning a bodied 5xx (never an empty 502); the SPA surfaces structured errors
(inline 422 field errors as an RFC 9457 `errors[]` array, 409 `reasons[]`) and LOCALIZES them via a
stable machine `code` resolved `t('errors:<path>', params)` against the existing `errors` i18n
namespace (field-level validation codes under `errors.validation.*`; `TRANSLATION_KEY_CONVENTIONS.md`)
— the backend English `error`/`detail` is a fallback only. Shared code: `frontend/src/shared/api/`
(`ApiError`, `applyApiError`) + each backend's `_response`/`_error`. Flask is the REFERENCE for the
ENVELOPE (P1, `backend/src/*_routes.py`); SAM Members is the conforming full-stack example; ZZP invoice
is the i18n-code reference (`errors.invoice.emailMissing`). Full guide (with the v1.0 contract +
changelog): `.kiro/specs/Common/Frameworks/api-response-standard/` (`design.md`). Cross-links: the
Fail-loud integrity spec.

## Relationship to the other steering files

- `32-frontend-ui.md` — frontend UI conventions + the detailed Filters pointer (single-plane). This
  file (`37`) is the cross-plane REGISTRY; it does not restate `32`'s content.
- `36-config-and-parameters.md` — the config/parameter contract (a sibling cross-cutting standard).
- `00-index.md` — lists this file in the `3x` layer / `auto` load set.
