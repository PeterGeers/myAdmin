# Steering Files — Analysis & Recommendations

**Status: ✅ ALL DECISIONS MADE**

## Current State

8 steering files, ~1,400 lines total. Most are `auto` inclusion (always loaded into every prompt).

| File                   | Lines | Inclusion           | Role                                               |
| ---------------------- | ----- | ------------------- | -------------------------------------------------- |
| `product.md`           | ~55   | auto (always)       | What myAdmin is                                    |
| `tech.md`              | ~175  | auto (always)       | Stack, commands, env config, code style            |
| `structure.md`         | ~230  | auto (always)       | Full project tree, modules, naming, architecture   |
| `specs.md`             | ~400  | auto (always)       | Spec workflow, examples, lifecycle, AI guidelines  |
| `api-conventions.md`   | ~80   | auto (always)       | API URL patterns, auth decorators, response format |
| `database-patterns.md` | ~75   | fileMatch (backend) | SQL patterns, tenant isolation                     |
| `testing-standards.md` | ~100  | fileMatch (tests)   | Test naming, fixtures, coverage                    |
| `pr-checklist.md`      | ~55   | manual              | PR review checklist                                |

**Always-on total: ~940 lines** (product + tech + structure + specs + api-conventions)

## Problems Identified

### 1. Too much always-on context (~940 lines)

Every prompt — even "fix a typo" — loads 940 lines of steering. This wastes tokens and dilutes the AI's focus on the actual task.

### 2. `structure.md` is oversized (230 lines)

Lists every backend module, every route file, every service. The AI can discover file structure with tools — it doesn't need it memorized. The detailed file listings are reference material, not guidance.

### 3. `specs.md` is oversized (400 lines)

Contains ~250 lines of examples (Railway Migration, Template Preview), lifecycle diagrams, cross-referencing guides, and "Finding Relevant Specs" sections. These are only useful when actively creating or updating specs.

### 4. `tech.md` includes rarely-needed content (175 lines)

Common commands (npm, pytest, docker), environment variable lists, and refactoring strategies are reference material. The core value is knowing the stack and code style (~80 lines).

### 5. `api-conventions.md` loads for frontend work too

API conventions are only relevant when editing backend Python files, but currently load on every interaction.

### 6. Content overlap

- Database schema appears in both `structure.md` and `database-patterns.md`
- Test organization appears in both `structure.md` and `testing-standards.md`
- Architecture patterns partially overlap between `structure.md` and `api-conventions.md`

### 7. No frontend-specific UI patterns file

Action buttons, table/modal layout, and responsive patterns are buried in `specs.md` under "Writing Design" — not discoverable when editing frontend components.

## Recommendations

### Decision 1: Trim always-on files to essentials only

**Rationale**: Always-on files should contain only guidance that's relevant to nearly every task. Reference material moves to conditional/manual files.

**Target**: ~365 lines always-on (down from ~940)

### Decision 2: Split `tech.md`

| Content                                          | Destination               | Inclusion          |
| ------------------------------------------------ | ------------------------- | ------------------ |
| Stack versions, code style, file size guidelines | `tech.md` (keep, trimmed) | auto (~80 lines)   |
| Commands (npm, pytest, docker), env config       | `commands.md` (new)       | manual (~70 lines) |

### Decision 3: Trim `structure.md`

| Content                                                              | Destination                                | Inclusion        |
| -------------------------------------------------------------------- | ------------------------------------------ | ---------------- |
| High-level directory tree, naming conventions, architecture patterns | `structure.md` (keep, trimmed)             | auto (~80 lines) |
| Detailed module listings, file-by-file breakdowns                    | Remove (discoverable via tools)            | —                |
| Database schema section                                              | Remove (already in `database-patterns.md`) | —                |
| Test organization section                                            | Remove (already in `testing-standards.md`) | —                |

### Decision 4: Trim `specs.md`

| Content                                                                                                 | Destination                | Inclusion           |
| ------------------------------------------------------------------------------------------------------- | -------------------------- | ------------------- |
| Spec organization, structure, workflow, when to use, best practices (incl. design patterns)             | `specs.md` (keep, trimmed) | auto (~150 lines)   |
| Examples, lifecycle diagram, cross-referencing, finding specs, AI guidelines, progress tracking details | `specs-reference.md` (new) | manual (~250 lines) |

### Decision 5: Change `api-conventions.md` to fileMatch

Change from `auto` to `fileMatch` with pattern `backend/src/**/*.py` — same as `database-patterns.md`.

### Decision 6: Create `ui-patterns.md` for frontend

New file with `fileMatch` pattern for `frontend/src/**/*.tsx,frontend/src/**/*.ts`. Contains:

- Action button standards (BankingProcessor pattern)
- Table & modal layout conventions
- Responsive design patterns
- Chakra UI component preferences

### Decision 7: Keep unchanged files

- `product.md` — good size, always relevant
- `database-patterns.md` — already well-scoped with fileMatch
- `testing-standards.md` — already well-scoped with fileMatch
- `pr-checklist.md` — already manual inclusion

## Proposed Final Structure

| File                   | Inclusion            | Purpose                                    | ~Lines |
| ---------------------- | -------------------- | ------------------------------------------ | ------ |
| `product.md`           | auto                 | What myAdmin is                            | 55     |
| `tech.md`              | auto                 | Stack + code style + file size guidelines  | 80     |
| `structure.md`         | auto                 | High-level dirs + naming + architecture    | 80     |
| `specs.md`             | auto                 | Core spec workflow + design patterns       | 150    |
| `api-conventions.md`   | fileMatch (backend)  | API patterns                               | 80     |
| `database-patterns.md` | fileMatch (backend)  | SQL patterns, tenant isolation             | 75     |
| `testing-standards.md` | fileMatch (tests)    | Test standards                             | 100    |
| `ui-patterns.md`       | fileMatch (frontend) | Action buttons, tables, modals, responsive | 60     |
| `pr-checklist.md`      | manual               | PR review checklist                        | 55     |
| `commands.md`          | manual               | All commands, env config, Docker           | 70     |
| `specs-reference.md`   | manual               | Spec examples, lifecycle, AI guidelines    | 250    |

**Always-on total: ~365 lines** (down from ~940 — 61% reduction)
**Conditional total: ~315 lines** (loads only when editing matching files)
**Manual total: ~375 lines** (loads only when explicitly requested)
