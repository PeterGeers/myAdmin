# CodeQL Script-Tag Strip Fix Bugfix Design

## Overview

Two GitHub Advanced Security (CodeQL) alerts fire on the test file
`frontend/src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormShellPanel.test.tsx`.
The behavioral test *"the generated listener resizes ONLY on a valid, origin-matching height
message"* needs the raw listener body (no wrapping `<script>` / `</script>` tags) so it can run
it with `new Function(...)`. The original approach stripped the wrapper tags with a regular
expression, and CodeQL flagged that regex-based tag filtering as unsafe HTML sanitization — once
per regex variant tried (`js/bad-tag-filter` for the case-sensitive `/<\/?script>/g`, then
`js/incomplete-multi-character-sanitization` for the single-pass `/<\/?script\b[^>]*>/gi`).

Because `buildIframeResizeListenerScript` is author-controlled and emits a string of the exact
shape `<script>\n…body…\n</script>`, the correct fix removes the regex entirely and instead
**slices between the known delimiters** — the content after the first `>` and before the final
`</script>`. No HTML parsing or sanitization pattern remains, so neither alert can fire, while the
secure-postMessage (CWE-346) assertions and the unchanged production helper are preserved exactly.

> **Current state — ALREADY FIXED at HEAD; verify green.** HEAD commit
> `96e8bbb6c "fix(members): CodeQL js/incomplete-multi-character-sanitization — slice, don't
> strip"` already contains this fix. The commit touches only the test file (7 insertions / 6
> deletions) and swaps the regex-strip line for the slice. The present body-extraction code is:
>
> ```ts
> const wrapped = buildIframeResizeListenerScript(FRAME_ORIGIN);
> const script = wrapped.slice(wrapped.indexOf('>') + 1, wrapped.lastIndexOf('</script>'));
> ```
>
> A repo-wide grep of the test file for `.replace(` and any `<\/?script…>` regex found **none** —
> the only `<script>` occurrences are plain `expect(snippet).toContain('<script>')` string
> assertions, not sanitization. The paired suite was run (`vitest run …
> ApplicationFormShellPanel.test.tsx`) and **all 37 tests pass**. So this design documents a
> source change that is already in place; the remaining work is confirming the gate goes green
> (re-run CodeQL on the PR) rather than editing the extraction code again.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a regex-based HTML tag-filter is
  used to strip the `<script>` / `</script>` wrapper off the generated listener string, which
  CodeQL classifies as unsafe HTML filtering/sanitization.
- **Property (P)**: The desired behavior — the listener body is obtained WITHOUT any regex tag
  filter (by slicing between the known delimiters), so no `js/bad-tag-filter` or
  `js/incomplete-multi-character-sanitization` alert fires and the PR gate goes green.
- **Preservation**: The behavioral intent of the test — proving the generated listener resizes the
  iframe only for a valid, origin-matching height message (CWE-346) — and the unchanged production
  helper `applicationShellForm.ts`, both of which must stay exactly as they are.
- **buildIframeResizeListenerScript**: The pure helper in
  `frontend/src/components/TenantAdmin/MembersConfig/applicationShellForm.ts` that returns the
  parent-side resize-listener string of the fixed shape `<script>\n(function () {…})();\n</script>`
  (or `''` when the frame origin cannot be derived). **Production source is unchanged by this fix.**
- **Body extraction**: The test-only step that peels the wrapper tags off that string to get the
  executable body. This is the ONLY code that changes.
- **CodeQL gate**: The `CodeQL Advanced` workflow (steering `43-cicd-deploys`) that runs on the PR;
  it must report zero alerts on this file for the PR to merge.

## Bug Details

### Bug Condition

The bug manifests when the test strips the `<script>` wrapper tags off the generated listener
string using a **regular-expression HTML tag filter** in order to execute the body with
`new Function(...)`. CodeQL treats any regex that filters HTML tags as unsafe sanitization and
raises an alert — the case-sensitive variant misses an upper-case `<SCRIPT>` tag
(`js/bad-tag-filter`), and the single-pass variant can leave a residual `<script` substring
(`js/incomplete-multi-character-sanitization`). Either alert blocks the PR.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type TestFileSource   # the source text of ApplicationFormShellPanel.test.tsx
  OUTPUT: boolean

  # The body is peeled off the generated <script>…</script> string using a
  # regular-expression HTML-tag filter (a .replace() against a /<\/?script…>/ pattern),
  # which CodeQL classifies as unsafe HTML filtering/sanitization.
  RETURN usesRegexTagFilterToStripScriptTags(input)
         AND (codeqlAlert(input) IN ['js/bad-tag-filter',
                                     'js/incomplete-multi-character-sanitization'])
END FUNCTION
```

### Examples

- **js/bad-tag-filter** — `wrapped.replace(/<\/?script>/g, '')` is case-sensitive; it would not
  strip an upper-case `</SCRIPT>`, so CodeQL flags it as a bad tag-filter regexp (blocks the PR).
- **js/incomplete-multi-character-sanitization** — `wrapped.replace(/<\/?script\b[^>]*>/gi, '')`
  is a single-pass replace that can leave a residual `<script` substring; CodeQL flags it as
  incomplete multi-character sanitization (blocks the PR).
- **PR gate** — with either regex present, the PR's CodeQL gate is reported failed and the branch
  cannot merge, even though the helper's output is author-controlled, not untrusted HTML.
- **Edge case / fixed shape** — the generated string is always `<script>\n…\n</script>`, so there
  is exactly one leading `>` and one trailing `</script>`; slicing between them yields the exact
  body with no tag-filtering pattern (correct behavior, no alert).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The behavioral test still proves the generated listener resizes the iframe ONLY for a valid,
  origin-matching height message — resizes to the ceil'd height (`743px` for `742.3`) on a
  well-formed same-origin message, and does NOT resize for a wrong-origin message, a wrong-shape
  message, or a non-numeric height (CWE-346; requirements 3.1–3.4).
- The other existing `buildIframeResizeListenerScript` / `buildIframeSnippet` assertions stay green
  unchanged: origin-pinned listener (not a wildcard), `type`/`source`/element-id tokens, the empty
  string when the origin cannot be derived, and the snippet contents (requirement 3.5).
- The production helper source `applicationShellForm.ts` is NOT edited — only the test's
  body-extraction step changes, so every helper's output is byte-for-byte identical.

**Scope:**
All behavior that does NOT involve the regex tag-strip is completely unaffected by this fix. This
includes:
- The production `buildIframeResizeListenerScript` / `buildIframeSnippet` / `deriveFrameOrigin`
  helpers and all their output.
- Every other test in the file (public-URL derivation, embed mode, consent version, config#mail
  body assembly, the `ApplicationFormShellPanel` component tests).
- The secure-postMessage assertions in the behavioral test — only the one line that obtains the
  executable body changes from a regex `.replace(...)` to a `.slice(...)`.

## Hypothesized Root Cause

Based on the bug description and the confirmed file state, the cause is understood (not merely
hypothesized):

1. **Regex used for a non-sanitization job**: The test needed only to peel two *known,
   author-controlled* wrapper tags off a string it generated itself — but reached for a regex HTML
   tag-filter to do it. CodeQL cannot distinguish "peeling known delimiters off trusted output"
   from "sanitizing untrusted HTML", so any `/<\/?script…>/`-style filter trips its taint queries.

2. **Case sensitivity (first variant)**: `/<\/?script>/g` is case-sensitive, matching
   `js/bad-tag-filter` — a filter that would miss `<SCRIPT>`.

3. **Single-pass incompleteness (second variant)**: `/<\/?script\b[^>]*>/gi` replaces in one pass,
   matching `js/incomplete-multi-character-sanitization` — a residual `<script` can remain after
   one replace.

4. **Wrong tool, not wrong pattern**: The fix is NOT a "better regex" (that still trips CodeQL) and
   NOT a suppression comment (the alert must be cleared at the root). The right tool is index-based
   slicing on the known delimiters, which carries no HTML-filtering semantics at all.

## Correctness Properties

Property 1: Bug Condition - Listener body extracted without a regex tag filter

_For any_ test source where the bug condition holds (a regex HTML tag-filter is used to strip the
`<script>` wrapper, isBugCondition returns true), the fixed test SHALL obtain the listener body by
slicing between the known author-controlled delimiters — the content after the first `>` and before
the final `</script>` — so that NO HTML-tag-stripping regular expression remains in the file, the
extracted body is exactly the listener source, and neither `js/bad-tag-filter` nor
`js/incomplete-multi-character-sanitization` is raised for this file.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Secure postMessage behavior and unchanged helper output

_For any_ input where the bug condition does NOT hold (the regex tag-filter is absent,
isBugCondition returns false), the fixed test SHALL produce the same observable behavior as before:
the generated listener resizes the iframe to the ceil'd height on a valid, origin-matching message
and ignores wrong-origin, wrong-shape, and non-numeric-height messages (CWE-346), and every other
`buildIframeResizeListenerScript` / `buildIframeSnippet` assertion yields the same result, because
the production helper source `applicationShellForm.ts` is unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

The root-cause fix (already present at HEAD commit `96e8bbb6c`) is confined to the test file.

**File**: `frontend/src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormShellPanel.test.tsx`

**Function**: the body of the `it('the generated listener resizes ONLY on a valid, origin-matching
height message', …)` test (the `applicationShellForm — responsive iframe-resize snippet` describe
block).

**Specific Changes**:
1. **Remove the regex tag-filter**: delete any `.replace(/<\/?script…>/…, '')` strip of the
   `<script>` / `</script>` wrapper — no HTML-tag-stripping regular expression remains in the file.
2. **Slice between known delimiters**: obtain the body as
   ```ts
   const wrapped = buildIframeResizeListenerScript(FRAME_ORIGIN);
   const script = wrapped.slice(wrapped.indexOf('>') + 1, wrapped.lastIndexOf('</script>'));
   ```
   `indexOf('>')` lands at the end of the opening `<script>`; `lastIndexOf('</script>')` at the
   start of the closing tag. This relies only on the helper's fixed `<script>\n…\n</script>` shape
   and carries no HTML-filtering semantics.
3. **Keep an explanatory comment**: note why this is NOT sanitization (peeling known
   author-controlled delimiters off trusted self-generated output), so a future reader does not
   "restore" a regex.
4. **Do NOT touch the production helper**: `applicationShellForm.ts` stays exactly as is — the
   generated `<script>…</script>` string is unchanged, preserving requirement 3.5.
5. **Do NOT suppress the alert**: no CodeQL `// codeql[...]` suppression — the alert is cleared by
   removing the flagged pattern, per the requirements and the change-with-tests contract.

### Change-with-tests contract & CodeQL re-run

- This change IS a change to a test file, and the test file is itself the allocated paired test for
  the `applicationShellForm` helper (steering `30-backend-api-flask-mysql` change-with-tests
  contract, mirrored for the frontend). The source edit and its assertions live in the same file
  and the same commit, so there is no "product edit leaves paired test stale" gap here. The paired
  suite MUST be run before considering the change done:
  `cd frontend && npx vitest run src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormShellPanel.test.tsx`
  (verified: 37/37 pass at HEAD).
- CodeQL is re-run to confirm the two alerts clear. Per steering `43-cicd-deploys`, CodeQL triggers
  automatically on push / PR to `test` and `main`, and can be dispatched manually:
  ```bash
  gh workflow run "CodeQL Advanced" --ref spec/members-11-application-form-builder
  gh run list --workflow "CodeQL Advanced" --limit 5
  ```
  and the PR head-commit gate results inspected with:
  ```bash
  SHA=$(git rev-parse HEAD)
  gh api repos/PeterGeers/myAdmin/commits/$SHA/check-runs
  ```
  Success = no `js/bad-tag-filter` and no `js/incomplete-multi-character-sanitization` alert for the
  file, and the CodeQL + GitGuardian gates green so the PR can merge (requirements 2.2, 2.3).

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate
the bug on the un-fixed code (the CodeQL alert fires), then verify the fix clears the alert and
preserves the behavioral assertions. Because the "bug" is a static-analysis finding rather than a
runtime fault, the primary oracle for the bug condition is the CodeQL gate itself; the runtime
oracle is the existing behavioral test, which must stay green throughout.

### Exploratory Bug Condition Checking

**Goal**: Surface the counterexamples that demonstrate the bug BEFORE the fix. Confirm the root
cause — that the regex tag-filter, not the body-execution approach, is what CodeQL flags.

**Test Plan**: On the un-fixed code (a `.replace(/<\/?script…>/…)` strip present), run the CodeQL
`CodeQL Advanced` workflow and inspect the PR check-runs. Observe the alert(s) and confirm which
query fires for which regex variant.

**Test Cases**:
1. **Case-sensitive strip**: with `/<\/?script>/g` present, CodeQL raises `js/bad-tag-filter`
   (will fail on un-fixed code).
2. **Single-pass strip**: with `/<\/?script\b[^>]*>/gi` present, CodeQL raises
   `js/incomplete-multi-character-sanitization` (will fail on un-fixed code).
3. **PR gate**: with either regex present, the PR's CodeQL gate is reported failed and the branch
   cannot merge (will fail on un-fixed code).

**Expected Counterexamples**:
- A CodeQL alert on `ApplicationFormShellPanel.test.tsx` naming the regex `.replace(...)` line.
- Possible causes: case-sensitive tag filter, single-pass incomplete sanitization, use of a regex
  HTML-tag filter for a non-sanitization job.

### Fix Checking

**Goal**: Verify that where the bug condition holds (a regex tag-filter was used), the fixed test
obtains the body without any regex and no CodeQL alert fires.

**Pseudocode:**
```
FOR ALL testSource WHERE isBugCondition(testSource) DO
  fixed := replaceRegexStripWithDelimiterSlice(testSource)
  ASSERT NOT usesRegexTagFilterToStripScriptTags(fixed)          # grep: no /<\/?script…>/ or .replace
  ASSERT extractedBody(fixed) == listenerBodyWithoutWrapperTags  # slice yields the exact body
  ASSERT codeqlAlerts(fixed) does NOT contain 'js/bad-tag-filter'
  ASSERT codeqlAlerts(fixed) does NOT contain 'js/incomplete-multi-character-sanitization'
END FOR
```

Concretely: (a) a grep of the file finds no `.replace(` and no `<\/?script…>` regex; (b) the paired
vitest passes, proving the sliced body is the correct executable listener; (c) the re-run CodeQL
gate reports zero of the two alerts for the file.

### Preservation Checking

**Goal**: Verify that where the bug condition does NOT hold, the fixed test produces the same
observable behavior as before — the CWE-346 secure-postMessage assertions and all other helper
assertions are unchanged, because the production helper source is untouched.

**Pseudocode:**
```
FOR ALL message WHERE NOT isBugCondition(message) DO
  ASSERT listenerBehavior_before(message) == listenerBehavior_after(message)
END FOR
# i.e. for every non-regex concern:
#   valid + same origin            -> resizes to ceil(height) + "px"   (743px for 742.3)
#   wrong origin                   -> no resize
#   wrong shape (type/source)      -> no resize
#   non-numeric height             -> no resize
#   all other build*/derive* tests -> identical output (helper unchanged)
```

**Testing Approach**: The existing behavioral test already encodes the preserved behavior across
the full input partition (valid, wrong-origin, wrong-shape, non-numeric), so it serves as the
preservation oracle directly. Property-based testing would strengthen the origin/shape/height
domain coverage, but the production helper is unchanged, so the risk of regression is confined to
whether the sliced body equals the original body — which the fixed-shape delimiters guarantee and
the behavioral test confirms.

**Test Plan**: Run the paired vitest on the fixed code and confirm every assertion that is NOT the
body-extraction line is byte-for-byte unchanged and still green.

**Test Cases**:
1. **Valid message resizes**: observe `743px` for height `742.3` — unchanged after the fix.
2. **Wrong origin ignored**: observe no resize for `https://evil.example.org` — unchanged.
3. **Wrong shape ignored**: observe no resize for a message missing the type/source tokens —
   unchanged.
4. **Non-numeric height ignored**: observe no resize for `height: 'tall'` — unchanged.
5. **Other helper assertions**: origin-pinned (not wildcard), type/source/element-id tokens, empty
   string when origin cannot be derived, snippet contents — all unchanged (requirement 3.5).

### Unit Tests

- The body-execution behavioral test (`the generated listener resizes ONLY on a valid,
  origin-matching height message`) — the direct unit oracle for Property 1 and Property 2's runtime
  half.
- The token/shape assertions (`the listener validates the message TYPE + SOURCE tokens`), the
  origin-pinning assertion, and the `buildIframeResizeListenerScript(null) === ''` edge case.
- A static check (grep / lint) asserting no `.replace(` tag-filter and no `<\/?script…>` regex
  remains in the file.

### Property-Based Tests

- Not required for this fix (the production helper output is unchanged and the input partition is
  small and already enumerated by the behavioral test). If added, a generator over
  `{origin, type, source, height}` tuples could assert the resize-iff-valid invariant across many
  random messages, strengthening the CWE-346 preservation guarantee.

### Integration Tests

- The **CodeQL `CodeQL Advanced` workflow** on the PR is the integration-level oracle: it must
  report zero `js/bad-tag-filter` and zero `js/incomplete-multi-character-sanitization` alerts for
  the file, and the combined CodeQL + GitGuardian PR gate must be green so the branch can merge
  (requirements 2.2, 2.3). Dispatch with `gh workflow run "CodeQL Advanced" --ref <branch>` and
  inspect with `gh api repos/PeterGeers/myAdmin/commits/$SHA/check-runs`.
