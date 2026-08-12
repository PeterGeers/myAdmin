# Code Quality Maintenance Prompt (CI Results Only)

Run the "Full Test Suite" GitHub Actions workflow and analyze the results: backend tests, frontend tests, and lint/static analysis. No local scans — purely CI-based.

---

## Prompt

### Step 1: Trigger the Full Test Suite

```bash
cd /home/peter/projects/myAdmin
export GH_PAGER=""
gh workflow run "Full Test Suite" --field scope=both --ref $(git branch --show-current)
```

Wait for completion (repeat until status shows "completed"):

```bash
gh run list --workflow=full-test-suite.yml --limit=1 --json status,conclusion,databaseId 2>&1 | head -5
```

Download the artifacts:

```bash
RUN_ID=$(gh run list --workflow=full-test-suite.yml --limit=1 --json databaseId --jq '.[0].databaseId' 2>&1 | head -1)
gh run download $RUN_ID --dir /tmp/test-reports
```

### Step 2: Analyze test failures from downloaded reports

Read the actual report files — do NOT parse log streams or use `--log`:

```bash
# Backend test summary
cat /tmp/test-reports/backend-test-reports/test-output.txt | grep -E "(FAILED|PASSED|ERROR|passed|failed)" | tail -20

# Frontend test summary
cat /tmp/test-reports/frontend-test-reports/SUMMARY.md

# Backend failures detail
cat /tmp/test-reports/backend-test-reports/test-output.txt | grep "FAILED"
```

Extract:

- Total tests passed / failed / errored per suite
- List of each failing test with error type (Flaky, AssertionError, ImportError, etc.)
- Group failures by root cause

### Step 3: Analyze Backend Lint & Static Analysis

The CI generates a downloadable `backend-lint-reports` artifact. Read it:

```bash
cat /tmp/test-reports/backend-lint-reports/SUMMARY.md
cat /tmp/test-reports/backend-lint-reports/ruff-lint.md
cat /tmp/test-reports/backend-lint-reports/ruff-format.md
cat /tmp/test-reports/backend-lint-reports/vulture.md
```

If the lint artifact is missing (older workflow version), fall back to log parsing:

```bash
LINT_JOB_ID=$(gh run view $RUN_ID --json jobs --jq '.jobs[] | select(.name=="Backend Lint & Static Analysis") | .databaseId' 2>&1 | head -1)
gh run view $RUN_ID --log --job=$LINT_JOB_ID 2>&1 | grep "##\[error\]" | sed 's/.*##\[error\]//' | cut -d: -f4 | sort | uniq -c | sort -rn > /tmp/test-reports/ruff-summary.txt
cat /tmp/test-reports/ruff-summary.txt
```

Include in the spec:

- Total ruff errors by rule code
- Which rules are auto-fixable vs manual
- Whether it's a version mismatch (local vs CI ruff version)

### Step 4: Generate the spec

Create a new spec at `.kiro/specs/code-quality-maintenance/full-test-suite-fixes-YYYY-MM-DD/` (use today's date) containing:

**requirements.md**: Summary of all findings with counts:

- Test failures: X backend, Y frontend (grouped by root cause)
- Lint failures: N ruff errors (grouped by rule code, auto-fixable vs manual)

**tasks.md**: Actionable fix tasks grouped by priority:

1. **Critical** — test import errors and broken fixtures (tests that can't even collect)
2. **High** — test assertion failures (tests that run but fail), ruff lint errors (CI-blocking)
3. **Medium** — flaky tests (Hypothesis deadline, non-deterministic), vulture dead code
4. **Low** — ruff format-only issues, minor warnings

Each task should have: file path, specific action, estimated effort (S/M/L), and a verification command.

Do NOT fix the issues — only generate the spec with the analysis and task list.

Ensure the tasks.md conform to Kirop requirements for tasks including .config.kiro, meta.json, dependency graphs (json)

### Step 5: Compare with previous run

Check `.kiro/specs/code-quality-maintenance/` for the most recent previous spec (e.g. `full-test-suite-fixes-YYYY-MM-DD/` or `code-quality-fixes-YYYY-MM-DD/`). If one exists:

1. Compare failure counts — are they going down?
2. Identify **recurring failures** that were "fixed" last time but reappear. Flag these prominently.
3. Identify **new failures introduced by the previous fix sprint** (regression from refactoring).
4. Add a "Lessons / Recurring Issues" section to requirements.md noting patterns that keep coming back.

### Step 6: Clean up downloaded reports

After generating the spec, remove temporary files:

```bash
rm -rf /tmp/test-reports
```

---

## Terminal Rules

**CRITICAL: All terminal commands must use bash/Linux syntax.**

- The workspace runs on WSL Ubuntu at `/home/peter/projects/myAdmin`
- Use `cat`, `grep`, `wc -l`, `head`, `tail`, `sed`, `find`, `sort`, `uniq` — standard Linux tools
- Use `2>&1 | head -N` or `2>&1 | tail -N` to limit output (avoids pager issues)
- NEVER use PowerShell cmdlets, Windows paths, or `Get-Content`
- Always pipe through `head`/`tail` to prevent `less`/pager from blocking the terminal
- Set `GH_PAGER=""` before any `gh` command to prevent pager hangs

---

## Lessons Learned Reference

Follow all Lessons Learned rules from `prompt.md` in this same directory. Key rules for this workflow:

- **Rule 7**: Always run on the feature branch (`--ref`), not main
- **Rule 9**: Read CI artifacts (zip reports) — don't scrape log streams
- **Rule 10**: Commit and push before triggering CI
- **Rule 11**: Hypothesis flaky tests need `derandomize=True` + `deadline=None`
- **Rule 13**: Lint failures are blocking — treat with same priority as test failures
