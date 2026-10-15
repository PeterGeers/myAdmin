# Archived point-in-time status docs (2026)

These are historical, point-in-time status artifacts — `*_COMPLETE.md`,
`*_SUMMARY.md`, `*_PLAN.md`, `*_REPORT.md` — generated during feature/test work
across late-2025 through mid-2026. They describe the state of the project at the
moment they were written and are not living documentation.

They were moved here (via `git mv`, so history is preserved) by task 15 of the
`code-quality-fixes-2026-10-15` spec, which flagged them as stale (see §7 "Stale
Documentation" of that spec's `requirements.md`).

## Layout

Each file is stored under its **original repository-relative path** beneath this
directory, so you can see where it used to live. For example:

- `backend/tests/api/API_TESTS_COMPLETE.md` was at `backend/tests/api/API_TESTS_COMPLETE.md`
- `frontend/src/MIGRATION_PLAN.md` was at `frontend/src/MIGRATION_PLAN.md`

## Selection criteria

Only docs with **no live references** anywhere in the repo were moved. Any status
doc still linked or mentioned from a README, another doc, or an active `.kiro/specs/**`
artifact was intentionally **left in place** to avoid creating a broken link.
