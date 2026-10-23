# Implementation Plan

## Overview

Per the design, the root-cause fix — slice-based body extraction with no regex HTML-tag
filter — is ALREADY present at HEAD commit `96e8bbb6c`, and the paired vitest passes 37/37.
These tasks follow a **verify-and-confirm** posture: confirm that state and clear the CodeQL
gate rather than re-editing already-correct code. The edit task (3) is CONDITIONAL — perform
it only if verification shows a regex tag-filter has somehow come back.

## Task Dependency Graph

- Tasks 1 and 2 are independent read-only verifications and run first, in parallel.
- Task 3 is CONDITIONAL — it runs ONLY if Task 1 finds a regex tag-filter still present; otherwise skip it.
- Task 4 (CodeQL re-run) depends on the file being in the confirmed/fixed state (Task 1, and Task 3 if it ran).
- Task 5 (Checkpoint) depends on Tasks 2 and 4 being green.

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "dependsOn": []
    },
    {
      "wave": 2,
      "tasks": ["3"],
      "dependsOn": ["1"]
    },
    {
      "wave": 3,
      "tasks": ["4"],
      "dependsOn": ["1", "3"]
    },
    {
      "wave": 4,
      "tasks": ["5"],
      "dependsOn": ["2", "4"]
    }
  ]
}
```

## Tasks

- [x] 1. Confirm the listener body is extracted without a regex tag filter (Bug Condition check)
  - **Property 1: Bug Condition** - Listener body extracted without a regex tag filter
  - **GOAL**: Surface any counterexample proving the bug (a regex HTML-tag filter) still exists in the test file; expect NONE at HEAD.
  - **Scoped PBT Approach**: The bug is a static-analysis finding on one known file, so scope the "property" to a grep over the concrete file `frontend/src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormShellPanel.test.tsx`.
  - Grep the file for `.replace(` and for any `<\/?script…>`-style regex — assert NEITHER a `.replace(` tag-strip nor a `/<\/?script…>/` pattern is present (the only `<script>` occurrences must be plain `expect(...).toContain('<script>')` string assertions, not sanitization). Per design `isBugCondition` / Fix Checking.
  - Assert the slice-based extraction IS present:
    `const script = wrapped.slice(wrapped.indexOf('>') + 1, wrapped.lastIndexOf('</script>'));`
  - **EXPECTED OUTCOME at HEAD**: grep finds no regex tag-filter and the slice line is present — the bug condition is already FALSE (fix in place). If a regex IS found, document the counterexample (the offending `.replace(...)` line) and proceed to the conditional edit in task 3.
  - _Requirements: 1.1, 1.2, 1.3, 2.1_

- [x] 2. Confirm the preserved secure-postMessage behavior by running the paired vitest (Preservation check)
  - **Property 2: Preservation** - Secure postMessage behavior and unchanged helper output
  - **IMPORTANT**: Follow observation-first methodology — the existing behavioral test already encodes the preserved behavior across the full input partition and serves as the preservation oracle directly.
  - Observe on current code: valid origin-matching height `742.3` → iframe resized to `743px`; wrong-origin message → no resize; wrong-shape message (missing type/source tokens) → no resize; non-numeric height → no resize (CWE-346).
  - Observe the other helper assertions still hold: origin-pinned listener (not a wildcard), `type`/`source`/element-id tokens, empty string when the origin cannot be derived, and the snippet contents — all unchanged because the production helper `applicationShellForm.ts` is untouched.
  - Run the paired suite:
    `cd frontend && npx vitest run src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormShellPanel.test.tsx`
  - **EXPECTED OUTCOME**: all tests PASS (37/37 at HEAD) — confirms the sliced body is the correct executable listener and no behavior regressed.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. (CONDITIONAL) Apply the slice-based fix — ONLY if task 1 found a regex tag-filter still present

  - [x] 3.1 Replace the regex strip with a delimiter slice
    - **SKIP this task entirely if task 1 confirmed no regex remains (the HEAD state).** Perform it only if verification surfaced a `.replace(/<\/?script…>/…, '')` strip.
    - Remove the regex tag-filter: delete any `.replace(/<\/?script…>/…, '')` strip of the `<script>` / `</script>` wrapper so no HTML-tag-stripping regular expression remains in the file.
    - Slice between the known author-controlled delimiters instead:
      ```ts
      const wrapped = buildIframeResizeListenerScript(FRAME_ORIGIN);
      const script = wrapped.slice(wrapped.indexOf('>') + 1, wrapped.lastIndexOf('</script>'));
      ```
    - Keep an explanatory comment noting this is NOT sanitization (peeling known author-controlled delimiters off trusted self-generated output) so a future reader does not restore a regex.
    - Do NOT edit the production helper `applicationShellForm.ts` — the generated `<script>…</script>` string stays byte-for-byte identical (preserves requirement 3.5).
    - Do NOT add a CodeQL `// codeql[...]` suppression — the alert is cleared by removing the flagged pattern, not suppressing it.
    - _Bug_Condition: isBugCondition(input) = usesRegexTagFilterToStripScriptTags(input) AND codeqlAlert(input) IN ['js/bad-tag-filter', 'js/incomplete-multi-character-sanitization']_
    - _Expected_Behavior: expectedBehavior(result) — body obtained via slice between known delimiters, no regex tag filter remains_
    - _Preservation: Preservation Requirements from design (CWE-346 assertions + unchanged helper output)_
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.2 Verify the bug condition check now passes
    - **Property 1: Expected Behavior** - Listener body extracted without a regex tag filter
    - **IMPORTANT**: Re-run the SAME grep check from task 1 — do NOT write a new check.
    - Re-grep the file: assert no `.replace(` tag-strip and no `/<\/?script…>/` regex remains, and the slice line is present.
    - **EXPECTED OUTCOME**: check PASSES (confirms the regex-based strip is gone).
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Secure postMessage behavior and unchanged helper output
    - **IMPORTANT**: Re-run the SAME paired vitest from task 2 — do NOT write new tests.
    - Run `cd frontend && npx vitest run src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormShellPanel.test.tsx`.
    - **EXPECTED OUTCOME**: all tests PASS (no regressions — CWE-346 assertions and all other helper assertions unchanged).
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Re-run CodeQL on the branch and confirm the PR gate is green (integration oracle)
  - **Property 1: Bug Condition** - no CodeQL alert fires for the file
  - Dispatch / watch the CodeQL workflow on the branch (per steering `43-cicd-deploys`):
    ```bash
    gh workflow run "CodeQL Advanced" --ref spec/members-11-application-form-builder
    gh run list --workflow "CodeQL Advanced" --limit 5
    ```
  - Inspect the PR head-commit check-runs:
    ```bash
    SHA=$(git rev-parse HEAD)
    gh api repos/PeterGeers/myAdmin/commits/$SHA/check-runs
    ```
  - **EXPECTED OUTCOME**: no `js/bad-tag-filter` and no `js/incomplete-multi-character-sanitization` alert for `ApplicationFormShellPanel.test.tsx`, and the combined CodeQL + GitGuardian PR gate is green so the branch can merge.
  - _Requirements: 2.2, 2.3_

- [x] 5. Checkpoint - Ensure all tests and gates pass
  - Confirm the paired vitest is green (37/37), the grep check finds no regex tag-filter, and the CodeQL + GitGuardian PR gate is green.
  - Ask the user if any question arises (e.g. the CodeQL run is still pending, or a gate is unexpectedly red).

## Notes

- **Already-fixed posture**: The design confirms the slice-based fix is present at HEAD
  `96e8bbb6c` (test file only, 7 insertions / 6 deletions) and the paired vitest is 37/37
  green. Tasks 1–2 are verifications, not edits.
- **Change-with-tests contract**: The changed file IS the allocated paired test for the
  `applicationShellForm` helper, so the source edit and its assertions live in the same file
  and commit — there is no stale-paired-test gap. Still run the paired vitest before calling
  any change done (steering `30-backend-api-flask-mysql`, mirrored for the frontend).
- **Do not suppress**: The CodeQL alerts (`js/bad-tag-filter`,
  `js/incomplete-multi-character-sanitization`) must be cleared by removing the regex pattern,
  never with a `// codeql[...]` suppression.
- **Production helper untouched**: `applicationShellForm.ts` is NOT edited — only the test's
  body-extraction line changes — so every helper's output stays byte-for-byte identical
  (requirement 3.5).
- **CodeQL mechanics**: `CodeQL Advanced` triggers on push / PR to `test` and `main` and via
  `workflow_dispatch` (steering `43-cicd-deploys`); the WSL terminal reports `Exit Code: -1`
  even on success, so judge gate results by the `gh api … check-runs` output, not the exit
  code.
