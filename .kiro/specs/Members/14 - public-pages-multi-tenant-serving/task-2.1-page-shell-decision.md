# Task 2.1 — `page_shell` extraction + packaging decision (shared rendering library)

> **DECISION FOR TASK 2.2 / 2.3 / 5.1 TO BUILD ON.** Task 2.1 extracts the plane-neutral,
> dependency-free HTML shell (`page_shell.render_page(head_meta, body_html, css)`) from a COPY
> of the Flask shell logic, keeps `LandingPageStyles` as the single shared CSS source, and
> DECIDES where the library is packaged. D-RENDER (design) + R7.1–R7.3.

## Decision

**SELECTED: vendor `page_shell` in `sam/shared/` (the `sam/shared`-style vendor named in
D-RENDER).** NOT a new top-level shared package.

- **Module:** `sam/shared/page_shell.py` — exported from `sam/shared/__init__.py`
  (`from sam.shared import render_page, HeadMeta`).
- **Contract:** `render_page(head_meta: Mapping[str, str], body_html: str, css: str) -> str`
  returns a complete `<!DOCTYPE html>` document — the `<head>` SEO/OG/Twitter/canonical meta
  block + a single `<style>` wrapping the caller's `css` + a `<body>` wrapping the caller's
  `body_html`. Recognised (all optional) `head_meta` keys: `lang` (default `"nl"`), `title`,
  `description`, `og_image`, `canonical`, `site_name`, `font_links` (pre-built `<link>` markup,
  emitted verbatim), `og_locale` (default `"nl_NL"`). Every value except `font_links` is
  HTML-escaped; a missing key renders empty (parity with the Flask shell's `.get(..., "")`).
- **`LandingPageStyles` stays the ONE CSS source** — `page_shell` does NOT import or fork it.
  CSS enters as the `css` PARAMETER, so the caller (Task 2.2) invokes
  `LandingPageStyles.build_css_variables` + `build_page_css` and passes the result in. This is
  what keeps `page_shell` dependency-free AND keeps CSS single-sourced.

## Why `sam/shared/` and not a new top-level package

1. **D-RENDER named it.** The design says: "a small plane-neutral module vendored where SAM can
   import it (`sam/shared`-style vendor) — exact packaging decided in Task 2." This records that
   exact choice.
2. **It already ships to Lambda with zero build change.** `sam/members/layer/Makefile` rsyncs
   `$(SAM_SRC)/shared/` wholesale into `python/sam/shared/` in the Members layer. Dropping
   `page_shell.py` into `sam/shared/` means it is on the Lambda `sys.path` automatically — no
   Makefile edit, no new vendoring rule. (Verified by reading the layer Makefile.)
3. **`sam/shared` is already the cross-plane "shared mechanism, not store" home.** It is
   self-contained by charter ("no dependency on myAdmin's `backend/src`" — `sam/README.md`).
   Because `page_shell` imports only stdlib `html` + `typing`, it fits that charter exactly and
   introduces no new coupling.
4. **The future Flask share-back still works.** R7.2 defers sharing the library INTO the landing
   plane to a later spec. A dependency-free module under `sam/shared/` can be imported by the
   Flask plane later (repo root is importable; nothing in it needs Lambda). No top-level package
   is needed to unblock that — and inventing one now would add a second shared location for no
   present benefit. If/when the landing plane shares back and a neutral top-level home reads
   better, the module can move then (one-line import change) — recorded as a future option, not
   done here.

## Flask landing module NOT touched (🚫 Scope decision / R7.2)

`page_shell` is extracted from a **COPY** of the `generate_index_html` shell f-string in
`backend/src/services/landing_page_publish_service.py`. That file is **not modified** by this
task — the live Flask function keeps calling its own code. `backend/src/services/landing_page_styles.py`
(`LandingPageStyles`) is **not modified** either; it stays the single CSS source and is confirmed
`re`/`typing`-only (verified by reading its imports). No landing-module file, key shape, or slug
function is touched (landing-plane non-regression, R9.5).

## No hidden Flask coupling (Task 2.4 fallback NOT taken)

The shell logic copied is a pure f-string over escaped `published_data`-shaped values + three
`LandingPageStyles` CSS calls + two already-built fragments (sections/footer/header, carousel JS).
None of that requires Flask, boto3, a request context, or a DB — the only non-stdlib calls were to
`LandingPageStyles`, which is itself dependency-free. The clean, dependency-free extraction
therefore succeeded; the Task 2.4 fallback (STOP → SAM-renders-own-shell → record the deferral)
is **NOT** triggered. The decomposition that made it clean: CSS and the body are PARAMETERS, so
`page_shell` owns only the scaffold, and the producer owns body + CSS composition.

## Consequences for the rest of Task 2 / dependent tasks

- **2.2** wires the SAM form: build the form body (via `ApplicationFormRenderer` output) + the
  `head_meta` dict + `css` (from `LandingPageStyles`) and call `render_page`. Does NOT refactor
  Flask `generate_index_html`. If 2.2 needs `LandingPageStyles` at Lambda runtime, vendor that one
  `re`/`typing`-only file into the Members layer the same least-surface way `dynamodb_client.py` is
  (explicit `cp` in the layer Makefile) — flagged for 2.2, not done here.
- **2.3** asserts output parity of `page_shell` + `LandingPageStyles` against a fixture (the
  separate change-with-tests task). A minimal import/structure smoke test is landed with 2.1
  (`sam/tests/test_page_shell.py`).
- **5.1** wraps the published form shell with `page_shell`.

---

# Task 2.4 — fallback-condition evaluation (SAM-renders-own-shell): NOT TAKEN

> **TASK 2.4 is the safety valve for Task 2** (R7.1/R7.2/R7.3, D-RENDER): *"If a hidden Flask
> coupling blocks clean extraction, STOP and fall back to SAM-renders-own-shell for v1 (record
> the deferral; do not silently drop R7)."* Its job is to VERIFY — not assume — whether the clean
> `page_shell` extraction (2.1/2.2) actually succeeded dependency-free, and to RECORD the outcome
> either way so R7 is never silently dropped. This section is that explicit, traceable record.

## Verdict

**The clean extraction HELD. The SAM-renders-own-shell fallback was NOT triggered. R7 is satisfied
via the shared library (`sam/shared/page_shell.py` + the single-sourced `LandingPageStyles`) — it
is NOT deferred.** No hidden Flask coupling was found.

## What was independently verified (not inferred from 2.1/2.2)

**Step 1 — `page_shell` is plane-neutral / dependency-free (R7.1, R7.3).**
- Direct import grep of `sam/shared/page_shell.py` shows only stdlib: `import html as _html` and
  `from collections.abc import Mapping`. No Flask, no boto3, no `backend/src` app import, no
  SAM-runtime coupling.
- The dependency-free AST test (`sam/tests/test_page_shell.py::test_render_page_is_dependency_free_stdlib_only`)
  parses the module's AST and asserts every imported root is in `{html, typing, collections}`.
  **Ran the full file: 6 passed in 0.17s** (`python -m pytest tests/test_page_shell.py -v`,
  marker=0). CSS enters only as the `css` PARAMETER — `page_shell` never imports or forks
  `LandingPageStyles`.

**Step 2 — the SAM form renders its shell THROUGH `page_shell`, CSS single-sourced (R7.1).**
- `sam/members/domain/application_form_render.py` imports `from sam.shared.page_shell import
  render_page` and `render_application_form_page(...)` ends by calling `render_page(head_meta=...,
  body_html=..., css=...)` — the shared shell owns the `<!DOCTYPE html>`/`<head>`/`<style>`/`<body>`
  scaffold; the producer owns only body + CSS composition.
- `LandingPageStyles` is the single CSS source: the renderer does `from services.landing_page_styles
  import LandingPageStyles` and composes CSS via `build_css_variables` + `build_page_css` — it is
  IMPORTED, never forked. A repo-wide grep confirms every SAM reference to `LandingPageStyles` is an
  import/call or a doc comment; no SAM file re-implements the CSS.

**Step 3 — NO Flask landing file was modified by Task 2 (🚫 DO-NOT-TOUCH banner / R7.2, R9.5).**
- `git status --porcelain` for `backend/src/services/landing_page*` and `tenant_slug*` is EMPTY.
- `git diff --name-only` (working tree) lists only SAM-plane files (`sam/...`) + spec docs — not a
  single `landing_page*`/`tenant_slug*` path.
- `landing_page_styles.py`'s last commit is `e7b1cffae` (2026-08-12), predating the 2026-11-01 Task 2
  reframing — so the shared CSS source was not touched by this task either.

## Disposition of the fallback branch

Because Step 1 proved `page_shell` genuinely stdlib-only (AST test, not assertion) and Step 2 proved
the SAM form renders without any Flask dependency (the only `backend/src` touch is the dependency-free
`LandingPageStyles` CSS generator, imported as a library), **there is no hidden coupling that would
force SAM to render its own shell.** The fallback (STOP → SAM-renders-own-shell for v1 → defer the
shared library) is therefore NOT implemented — implementing it would be inventing a fallback that the
evidence shows is unnecessary.

## Note (state of the work, not a coupling)

The Task 2 artifacts (`sam/shared/page_shell.py`, `sam/members/domain/application_form_render.py`,
and the paired tests) are present on disk and untracked (`??`) in git — i.e. the extraction exists and
its tests pass, but the change is not yet committed. This is a commit-state observation, not a coupling
or a reason to take the fallback.

**Evaluated and recorded per R7.2 ("noted, not silently dropped").**
