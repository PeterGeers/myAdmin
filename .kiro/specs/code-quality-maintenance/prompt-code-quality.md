# Code Quality Improvement Prompt

A **local, source-focused** code-quality scan — no CI, no test-suite execution. It looks
for ways to make the codebase smaller and more consistent: **code reduction, duplicate
code, dead code, over-long files, and the (non-)use of the project's own frameworks /
reusable building blocks** (people re-implementing something a shared helper, hook, or
abstraction already provides).

> **Scope split.** Running the CI **Full Test Suite** and triaging test/lint failures is a
> SEPARATE task — see `promptTestSuiteResults.md` in this same directory. This prompt does
> NOT trigger workflows, download CI artifacts, or analyze test failures. It reads the
> source tree and produces a code-quality improvement spec.

Paste this into Kiro to run the analysis and generate improvement tasks automatically.

---

## Prompt

Perform a local code-quality scan of the repository and combine the findings into an
actionable spec. Do NOT run the test suite or CI — this is a static, source-level review.

Analyze the following dimensions. For each, capture concrete file paths + line counts /
match locations so the generated tasks are directly actionable.

### 1. File length (split candidates)

Find over-long source files — they are the usual home of duplication and dead code.

```bash
# Backend Python + frontend TS/TSX over 500 lines (flag > 1000 as critical)
find backend/src frontend/src -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) \
  -not -path '*/node_modules/*' -not -path '*/__pycache__/*' \
  -exec wc -l {} + | sort -rn | awk '$1 > 500 {print}' | head -60

# SAM plane too (module handlers grow quietly)
find sam -type f -name '*.py' -not -path '*/node_modules/*' -not -path '*/__pycache__/*' \
  -exec wc -l {} + | sort -rn | awk '$1 > 500 {print}' | head -40
```

Record: files 500–1000 lines, files > 1000 lines (critical). For each large file, note
WHAT could be extracted (a cohesive helper, a sub-module, repeated blocks).

### 2. Dead code

```bash
# Backend + SAM
vulture backend/src/ backend/vulture_whitelist.py --min-confidence 80 --exclude validate_pattern/
vulture sam/ --min-confidence 80

# Frontend: unused exports / files (heuristic — review before deleting)
# Look for exported symbols never imported elsewhere, and orphaned components.
grep -rn "export " frontend/src/ --include='*.ts' --include='*.tsx' | wc -l
```

Record each finding with confidence. Vulture at ≥ 80 is high-signal; still verify a symbol
is not referenced dynamically (getattr, string dispatch, route registration) before proposing removal.

### 3. Duplicate / near-duplicate code (code reduction)

Find repeated logic that should be collapsed into one shared implementation.

```bash
# Repeated function/const signatures (candidates for a shared helper)
grep -rhoP '^\s*(def|async def)\s+\w+' backend/src sam --include='*.py' | sort | uniq -c | sort -rn | head -30
grep -rhoP 'export (async )?function \w+|export const \w+\s*=' frontend/src --include='*.ts' --include='*.tsx' | sort | uniq -c | sort -rn | head -30

# Copy-pasted blocks: look for identical multi-line snippets (e.g. the same try/except
# envelope, the same fetch+unwrap, the same date-format). Grep a distinctive line and see
# how many files repeat it.
```

Record: the duplicated pattern, every location it appears, and the single place it should
live (an existing helper if one exists — see §4 — or a new shared one).

### 4. (Non-)use of frameworks / reusable building blocks  ← primary focus

The project ships shared abstractions; new code should USE them rather than re-implement.
Flag hand-rolled code that bypasses an existing, documented building block. Check the
project's own conventions (steering `37-shared-building-blocks.md`, `30-backend-api-flask-mysql.md`,
`31-backend-database-flask-mysql.md`, `32-frontend-ui.md`) for the canonical helpers, then grep for bypasses:

```bash
# Backend DB: raw mysql.connector instead of DatabaseManager / dialect_helpers
grep -rn "import mysql.connector\|mysql\.connector\.connect" backend/src --include='*.py' \
  | grep -v "database.py\|scalability_manager.py"
# Raw SQL string-interpolation instead of parameterized %s (injection + bypass smell)
grep -rn "execute(.*f\"\|execute(.*%\s*(" backend/src --include='*.py' | head

# Backend auth: routes NOT using the shared decorators (@cognito_required/@tenant_required/@module_required)
grep -rLn "cognito_required\|tenant_required\|module_required" backend/src/routes --include='*.py'

# Frontend data fetching: direct axios/fetch instead of the shared service/api layer
grep -rn "axios\.\|fetch(" frontend/src --include='*.ts' --include='*.tsx' \
  | grep -v "src/services/\|apiService\|test"
# Frontend filters/tables: bespoke table/filter code instead of the shared framework
#   (GenericFilter / the Table Filter Framework / shared hooks) — grep for local re-impls.
grep -rn "useState.*filter\|\.filter(.*includes(" frontend/src --include='*.tsx' | head

# Frontend UI: hardcoded values instead of the Chakra theme / shared components
grep -rn "#[0-9a-fA-F]\{6\}\|colorScheme=" frontend/src --include='*.tsx' | head
```

For each hit, decide: is this a legitimate low-level site (the helper's own
implementation, an intentional exception) or a bypass that should be migrated to the shared
building block? Record the bypasses with the specific building block they should adopt.

### 5. Type safety

```bash
# Frontend: explicit `any` in production code (not tests)
grep -rn ":\s*any\b\|as any\|<any>" frontend/src --include='*.ts' --include='*.tsx' \
  | grep -v "__tests__\|\.test\." | head -40

# Backend: public service/route functions missing return/param type hints (heuristic)
grep -rn "def \w\+(" backend/src/services backend/src/routes --include='*.py' \
  | grep -v "->" | head -40
```

### 6. Mobile compliance (frontend)

Every frontend function/component that renders UI, handles interaction, or affects layout
must be mobile-optimized unless it carries an explicit exemption marker. Flag:

- Fixed pixel widths/heights that don't adapt (`width: 1200px`, non-responsive `min-width`) instead of responsive units (`%`, `rem`, `vw`, `clamp()`) or breakpoints.
- Missing responsive breakpoints — desktop-only layouts with no mobile/tablet handling (no media queries, no Tailwind `sm:`/`md:`, no MUI/Chakra `{ base, md }` props / `useBreakpointValue`).
- Touch targets smaller than 44x44px.
- Horizontal-overflow risks — wide tables/grids/flex rows without `overflow-x` handling or a stacked/card mobile fallback.
- Hover-only interactions with no touch/tap equivalent.
- Non-responsive font sizes / spacing hardcoded for desktop.
- Viewport meta — confirm `index.html` has `<meta name="viewport" content="width=device-width, initial-scale=1">`.

A component is **exempt** only with an explicit marker — a `// mobile-exempt: <reason>` comment,
a `data-mobile-exempt` attribute, or a documented exemption-list entry. Record exempt items
separately (do not count them as violations).

```bash
# Fixed pixel widths (heuristic — review matches)
grep -rn "width:\s*[0-9]\{3,\}px\|minWidth:\s*[0-9]\{3,\}\|min-width:\s*[0-9]\{3,\}px" frontend/src/ --include="*.ts" --include="*.tsx" --include="*.css" | grep -vi "mobile-exempt"
# Components with no responsive breakpoints
grep -rLn "@media\|sm:\|md:\|lg:\|breakpoints\|useMediaQuery\|useBreakpointValue" frontend/src/ --include="*.tsx" | grep -vi "mobile-exempt"
# Hover-only interactions
grep -rn ":hover\|_hover" frontend/src/ --include="*.css" --include="*.tsx" | grep -vi "mobile-exempt"
# Explicitly exempt items (record separately, do not flag)
grep -rn "mobile-exempt" frontend/src/
```

### 7. Stale documentation (light pass)

Flag docs that clearly no longer match the code (reference deleted modules, old endpoints,
retired frameworks). Keep this light — it is the lowest-priority signal.

**Exclude everywhere:** test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`,
`dist/`, `.hypothesis/`, `mysql_data/`, `.agent-output/`.

---

## Generate the spec

Create a new spec at `.kiro/specs/code-quality-maintenance/code-quality-fixes-YYYY-MM-DD/`
(today's date). Conform to Kiro spec conventions: include `requirements.md`, `tasks.md`,
`tasks.meta.json` (seed `{"pbtResults":{},"executionHistory":{}}`), and `.config.kiro`
(`{"specId":"<uuid>","workflowType":"requirements-first","specType":"bugfix"}`).

**requirements.md** — findings with counts:

- File length: N files 500–1000 lines, M files > 1000 (critical), by plane (backend/sam/frontend).
- Dead code: N items (with confidence).
- Duplicate code: N patterns and their repeat counts + locations.
- Framework/reusable-code bypasses: N sites re-implementing a shared building block (with the block each should adopt).
- Type safety: N issues.
- Mobile compliance: N not mobile-optimized (plus M explicitly exempt, listed separately).
- Stale documentation: N outdated files.

**tasks.md** — improvement tasks grouped by priority. Each task: file path(s), specific
action, estimated effort (S ≤ 30 min / M ≤ 2 h / L > 2 h), and a verification note.

1. **High** — duplicate-code consolidation and framework-bypass migrations with broad reach
   (a repeated pattern in many files; a bypass of the DB/auth/service layer that carries
   security or consistency risk); dead-code removal that shrinks the surface materially.
2. **Medium** — files > 1000 lines split into cohesive modules; remaining framework
   bypasses; type-safety gaps in service/route layers.
3. **Low** — files 500–1000 lines refactored opportunistically; minor `any`/type-hint
   gaps; stale documentation.

Mobile-compliance violations are prioritized by user impact: **High** for unusable-on-mobile
(horizontal overflow, tap targets too small, no responsive layout on primary flows),
**Medium** for degraded-but-usable, **Low** for cosmetic issues on secondary/admin-only screens.

Do NOT fix the issues in this pass — only generate the spec with the analysis and task list.

## Compare with the previous run

Check `.kiro/specs/code-quality-maintenance/` for the most recent previous
`code-quality-fixes-YYYY-MM-DD/`. If one exists:

1. Are the counts going down (fewer duplicates, smaller files, fewer bypasses)?
2. Flag **recurring** items that were meant to be fixed last cycle but reappear.
3. Flag **new** debt introduced since (a fresh > 1000-line file, a new framework bypass).
4. Add a "Lessons / Recurring Issues" section to requirements.md.

---

## Terminal Rules

**All terminal commands must use bash/Linux syntax.** (Full rules: steering `41-shell-environment.md`.)

- Workspace runs on WSL Ubuntu at `/home/peter/projects/myAdmin`; use `cat`, `grep`, `wc -l`,
  `head`, `tail`, `sed`, `find`, `sort`, `uniq`.
- Limit output with `2>&1 | head -N` / `tail -N`; never use PowerShell cmdlets or Windows paths.
- Empty output does not mean failure — judge by the in-band `<<<DONE marker=$?>>>` marker; if
  output is swallowed, redirect to a file under `.agent-output/` and read that.

---

## Principles when executing the generated tasks

### 1. Reuse before rewrite

Before adding a helper/component, check whether one already exists (steering
`37-shared-building-blocks.md`; grep the services/hooks/utils). Prefer adopting the shared
building block over introducing a parallel implementation — the point of this task is to
REDUCE code, not add more.

### 2. Consolidate duplicates into ONE home

When collapsing repeated logic, move it to a single shared function/module and update every
call site in the same change. Do not leave a half-migrated split where some callers use the
new helper and others keep the copy.

### 3. Verify a symbol is truly dead before deleting

Vulture ≥ 80 is high-signal, but confirm the symbol is not referenced dynamically
(`getattr`, string dispatch, route/blueprint registration, a template, an entry-point)
before removing. Prefer deletion over commenting-out.

### 4. Split large files along cohesion seams

When splitting a > 1000-line file, extract cohesive units (one concern per module), keep the
public import surface stable (re-export from the original module path if others import it),
and change behavior in zero places — this is a structural refactor, not a rewrite.

### 5. A behavior change drags its tests along

If any reduction/refactor changes observable behavior, update the paired test(s) in the same
change (steering "Change-With-Tests Contract" in `30-backend-api-flask-mysql.md` /
`32-frontend-ui.md`). A pure move/rename with no behavior change needs no test change, but
run the affected tests to confirm.

### 6. Mobile-first is the default

Every UI-rendering/interaction/layout component must be mobile-optimized unless explicitly
marked exempt (`// mobile-exempt: <reason>`, `data-mobile-exempt`, or a documented list).
Use responsive units/breakpoints, ≥ 44x44px tap targets, a mobile fallback for wide
tables/grids, and a tap equivalent for any hover-only interaction. Record exemptions with a
reason — never silently skip.
