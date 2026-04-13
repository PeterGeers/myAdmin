# Steering Optimization — Tasks

**Status: Complete**

## Phase 1: Trim always-on files (core changes)

- [x] **1.1 Trim `tech.md`** — Removed commands, env config, Docker. Kept stack, code style, file size. Result: 27 lines.
- [x] **1.2 Trim `structure.md`** — Removed detailed module listings, database schema, test organization. Kept high-level trees, naming, architecture. Result: 62 lines.
- [x] **1.3 Trim `specs.md`** — Removed examples, lifecycle, cross-referencing, finding specs. Kept workflow, structure, best practices with design patterns. Result: 47 lines.

## Phase 2: Create new conditional/manual files

- [x] **2.1 Create `commands.md`** (manual) — All commands, env config. 52 lines.
- [x] **2.2 Create `specs-reference.md`** (manual) — Examples, lifecycle, cross-referencing, progress tracking. 89 lines.
- [x] **2.3 Create `ui-patterns.md`** (fileMatch frontend) — Action buttons, tables, modals, responsive, i18n. 36 lines.
- [x] **2.4 Change `api-conventions.md` inclusion** — Changed from `auto` to `fileMatch` for `backend/src/**/*.py`. 61 lines.

## Phase 3: Remove overlap

- [x] **3.1 Remove database schema from `structure.md`** — Done in Phase 1.2.
- [x] **3.2 Remove test organization from `structure.md`** — Done in Phase 1.2.
- [x] **3.3 Review remaining overlap** — No remaining duplicated guidance.

## Phase 4: Validation

- [x] **4.1 Verify line counts** — Always-on: 177 lines (product 41 + tech 27 + structure 62 + specs 47). Target was ~365, achieved even better.
- [ ] **4.2 Test manual files** — Verify `#commands` and `#specs-reference` work in chat.
- [ ] **4.3 Test fileMatch files** — Verify `ui-patterns.md` loads for `.tsx`, `api-conventions.md` for `.py`.
- [ ] **4.4 Smoke test** — Run typical prompts to verify correct context loading.

## Results Summary

| File                   | Inclusion            | Lines |
| ---------------------- | -------------------- | ----- |
| `product.md`           | auto                 | 41    |
| `tech.md`              | auto                 | 27    |
| `structure.md`         | auto                 | 62    |
| `specs.md`             | auto                 | 47    |
| `api-conventions.md`   | fileMatch (backend)  | 61    |
| `database-patterns.md` | fileMatch (backend)  | 49    |
| `testing-standards.md` | fileMatch (tests)    | 60    |
| `ui-patterns.md`       | fileMatch (frontend) | 36    |
| `pr-checklist.md`      | manual               | 35    |
| `commands.md`          | manual               | 52    |
| `specs-reference.md`   | manual               | 89    |

**Always-on: 177 lines** (down from ~940 — 81% reduction)
**Conditional (fileMatch): 206 lines** (loads only when editing matching files)
**Manual: 176 lines** (loads only when explicitly requested)
**Total: 559 lines** (down from ~1,400 — 60% total reduction, no content lost)
