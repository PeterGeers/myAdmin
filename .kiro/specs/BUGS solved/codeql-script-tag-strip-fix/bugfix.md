# Bugfix Requirements Document

## Introduction

The full test suite on the `test` branch failed and GitHub Advanced Security (CodeQL) raised two
alerts on this PR, both in the test file
`frontend/src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormShellPanel.test.tsx`.

That test calls `buildIframeResizeListenerScript(FRAME_ORIGIN)` (from `applicationShellForm.ts`),
which returns a string of the exact shape `<script>\n…listener body…\n</script>`. To exercise the
generated listener body with `new Function(...)`, the test needs the body WITHOUT the wrapping
`<script>` / `</script>` tags. The original approach removed those wrapper tags with a regular
expression, and CodeQL flagged that regex-based tag stripping as unsafe HTML filtering — twice, once
for each regex variant tried:

1. `/<\/?script>/g` — CodeQL `js/bad-tag-filter` ("Bad HTML filtering regexp"): the pattern is
   case-sensitive, so it fails to match an upper-case `<SCRIPT>` / `</SCRIPT>` tag.
2. `/<\/?script\b[^>]*>/gi` — CodeQL `js/incomplete-multi-character-sanitization` ("Incomplete
   multi-character sanitization"): a single-pass replace can leave a residual `<script` substring,
   so stripping is not guaranteed to be complete.

Although this is test-only code (peeling author-controlled wrapper tags off a generated string, not
production HTML sanitization), CodeQL still gates the PR. The alerts must be cleared by fixing the
root cause — removing the regex-based tag-filtering pattern altogether — not by suppressing the
alert, and the test must continue to exercise the generated listener's secure, origin-matching
postMessage behavior (CWE-346).

## Bug Analysis

### Current Behavior (Defect)

The test extracts the listener body from the `<script>…</script>` string using a regular expression
to strip the wrapper tags, which triggers CodeQL's unsafe-HTML-filtering alerts.

1.1 WHEN the test strips the wrapper tags with the case-sensitive regex `/<\/?script>/g` THEN CodeQL
raises the `js/bad-tag-filter` alert because the pattern does not match an upper-case `<SCRIPT>` /
`</SCRIPT>` tag, blocking the PR.

1.2 WHEN the test strips the wrapper tags with the single-pass regex `/<\/?script\b[^>]*>/gi` THEN
CodeQL raises the `js/incomplete-multi-character-sanitization` alert because the single replace pass
can leave a residual `<script` substring, blocking the PR.

1.3 WHEN either regex-based strip is present and the CodeQL gate runs on the PR THEN the full test
suite / PR gate is reported as failed and cannot merge.

### Expected Behavior (Correct)

The listener body is obtained without any regex-based HTML tag filtering, so neither CodeQL alert
fires and the PR gate goes green.

2.1 WHEN the test needs the listener body from the generated `<script>…</script>` string THEN the
test SHALL extract it WITHOUT a regex tag-filter — slicing between the known author-controlled
delimiters (the content after the first `>` and before the final `</script>`) — so no
HTML-tag-stripping regular expression remains in the file.

2.2 WHEN the CodeQL gate runs on the PR THEN the system SHALL report no `js/bad-tag-filter` alert and
no `js/incomplete-multi-character-sanitization` alert for this file.

2.3 WHEN the CodeQL and test gates run on the PR THEN the system SHALL report the full test suite /
PR gate as passing so the PR can merge.

### Unchanged Behavior (Regression Prevention)

The behavioral intent of the test — proving the generated listener only resizes the iframe for a
valid, origin-matching height message — must be preserved exactly.

3.1 WHEN the generated listener receives a well-formed, origin-matching height message THEN the test
SHALL CONTINUE TO assert the targeted iframe is resized to the ceil'd height (e.g. `743px` for
`742.3`).

3.2 WHEN the generated listener receives a message from a non-matching origin THEN the test SHALL
CONTINUE TO assert the iframe is NOT resized.

3.3 WHEN the generated listener receives a message of the wrong shape (missing/incorrect
type/source tokens) THEN the test SHALL CONTINUE TO assert the iframe is NOT resized.

3.4 WHEN the generated listener receives a message whose height is non-numeric THEN the test SHALL
CONTINUE TO assert the iframe is NOT resized.

3.5 WHEN `buildIframeResizeListenerScript` and `buildIframeSnippet` are exercised by their other
existing assertions (origin-pinned listener, type/source/element-id tokens, empty string when the
origin cannot be derived, and the snippet contents) THEN the system SHALL CONTINUE TO produce the
same output, because the production helper source is unchanged — only the test's body-extraction
step changes.
