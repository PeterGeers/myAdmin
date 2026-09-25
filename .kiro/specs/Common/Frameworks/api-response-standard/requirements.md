# Platform API response & error standard v1.0 — Requirements

## Introduction

This spec defines **v1.0 of the platform-wide API response & error standard** that EVERY backend
handler and EVERY frontend (UI/UX) app conforms to — a single, versioned contract, not a
per-module convention.

**Three deliverables:**
- **A — The standard (incl. i18n).** The versioned v1.0 contract: one envelope, fail-loud bodied
  5xx, structured errors, code-driven localization (R1–R4, R6).
- **B — Implement it in SAM Members as-is today.** Bring the current Members handler + modals into
  full compliance (the catch-all, the envelope, code-driven localized errors surfaced inline) —
  real code, not just documentation (R1–R5).
- **C — A documented structure for shared building blocks.** A best-practice, reusable STRUCTURE for
  shared blocks — modeled on how the Table Filter Framework v2 is documented (`32-frontend-ui.md` →
  Frameworks spec + reference implementation) — so `applyApiError`/the error contract, and future
  shared blocks, are discoverable and built the same way (R7).

It was triggered when adding a member in production returned a bare **502 / "Failed to fetch"**
with no usable message (2026-09-24, s5k prod verify). The root cause (an unhandled `TypeError` in
`_reject_invalid_overlay_enum_values`) was hotfixed in s5k, but the empty 502 exposed that error
handling is **inconsistent and unversioned** across the platform: each module re-derives it, and
there is no written standard a new app inherits.

### Guiding principles

- **P1 — Flask is the reference implementation of v1.0.** The Flask apps already return the target
  envelope (`{success, data|error}` + real HTTP status). We do NOT change Flask to invent a new
  shape; every other plane (SAM today, any future plane) conforms TO it. "Don't rewrite Flask" is a
  principle, not an exclusion — Flask defines the baseline.
- **P2 — One envelope, everywhere.** Success and failure both carry a parseable JSON body with the
  real HTTP status. No empty responses; no per-plane shapes.
- **P3 — Every failure is user-visible AND localized.** A rejected action shows the user a message
  in their language (NL/EN), per-field where applicable — never a raw English backend string, never
  "Failed to fetch".
- **P4 — Fail loud, never silent.** An unanticipated error becomes a bodied 5xx with a logged
  traceback, not an opaque crash. (Shared philosophy with the Fail-loud integrity spec.)
- **P5 — The standard is written down and versioned (v1.0).** New modules conform by reading the
  steering doc, not by copying an existing file and hoping.

### What is ALREADY true (verified in code — so the spec is accurate)

- **Both planes already use real HTTP status codes.** Flask: `jsonify({"success": False, "error":
  ...}), 400` (`backend/src/*_routes.py`). SAM: `{"statusCode": status, ...}` via `_response`.
  Neither hides a failure as a 200. The planes are NOT "status vs envelope" — both are status-based;
  they differ only in BODY KEYS.
- **The only wire difference is envelope keys:** Flask success `{success:true, data}` / error
  `{success:false, error}`; SAM success `{data}` (no `success`) / error `{error, errors?, reasons?}`
  (no `success`; richer field errors).
- **SAM already maps anticipated errors** to `422 {errors}` / `409 {reasons}` / `403` / `404` via
  `_error`, and the SPA already reads `.error` on non-2xx.
- **i18n is INCOMPLETE even in the Flask/ZZP reference.** ZZP localizes CLIENT-side messages
  (`t('invoices.created', 'fallback')`) but shows a BACKEND error string RAW
  (`toast({ title: resp.error || 'Error saving invoice' })`) — English, unlocalized — and even
  string-sniffs it (`errorMsg.toLowerCase().includes('email')`) to re-localize one case. So the
  backend-message path is NOT localized anywhere today; v1.0 fixes that (R4).

### The gaps v1.0 closes

1. **No catch-all** in the SAM handler → unanticipated errors escape as an empty 502.
2. **SAM's envelope keys differ from Flask's** → two shapes for the frontend/shared helper.
3. **Structured errors are flattened** by the SPA (`new Error(error.error)`) → no inline 422
   field errors / 409 reasons.
4. **Backend messages are not localized** when surfaced → raw English in a NL-first UI.
5. **The standard is not codified/versioned** → new modules don't inherit it.

## Glossary

- **Envelope** — the JSON body every response carries: success `{success:true, data}`; error
  `{success:false, error, code?, params?, errors?, reasons?}`.
- **`code`** — a stable, machine-readable error identifier that IS a key in the existing i18n
  `errors`/`validation` namespaces (camelCase, dotted; e.g. `validation.required`,
  `errors.member.numberFormat`, `errors.api.serverError`). Language-independent; the SPA maps it to
  localized copy. Follows `TRANSLATION_KEY_CONVENTIONS.md` (no new namespace).
- **`error`** — a human-readable English summary (dev-facing / last-resort fallback), NOT the
  primary thing shown to an end user when a `code` exists.
- **`errors`** — a 422 per-field validation ARRAY, following RFC 9457 §3.1's `invalid-params`
  model: each entry is an object `{ "field": "<dotted key / JSON-pointer-ish>", "code": "<i18n
  key>", "params"?: {..}, "detail": "<English sentence>" }`. `field` locates the offending value,
  `code` is the machine identifier the client localizes off, `detail` is the human fallback. ALL
  failing fields are reported in one response.
- **`reasons`** — a 409 denial ARRAY (transition/guard). Each entry `{ "code": "<i18n key>",
  "params"?: {..}, "detail": "<English sentence>" }` — same shape as an `errors` entry but with no
  `field` (a denial is not tied to one input). (Legacy `reasons: string[]` still accepted by the
  SPA resolver — degrades to the string.)
- **Anticipated / Unanticipated error** — a mapped domain 4xx vs any other exception.

### Standards basis — RFC 9457

The envelope + per-field shape follow **RFC 9457 (Problem Details for HTTP APIs)**, the IETF
standard for structured API errors, specifically its §3.1 validation-errors model: an array of
per-field entries, each carrying a machine `code` AND a human `detail`, with all failing fields
reported at once. We keep our `{success, data|error, code, errors, reasons}` envelope (the SPA +
Flask already branch on `success`/HTTP status) rather than the raw `application/problem+json`
`{type,title,status,detail}` body — RFC 9457 explicitly permits extension members, so this is
standard-aligned, not a bespoke format. `code` values are keys in the existing `errors`/`validation`
i18n namespaces.

## Requirements

### R1 — The unified envelope (P1, P2) — all backends

Acceptance criteria:
1. A **success** response SHALL be `{ "success": true, "data": <payload> }` + the real 2xx status.
2. An **error** response SHALL be `{ "success": false, "error": "<English summary>", "code"?:
   "<i18n key>", "params"?: {..}, "errors"?: [ {field, code, params?, detail}, … ],
   "reasons"?: [ {code, params?, detail}, … ] }` + the real 4xx/5xx status. `errors`/`reasons`
   follow the RFC 9457 §3.1 per-entry shape (machine `code` + human `detail`); ALL failing fields
   are reported at once.
3. Flask (reference) is UNCHANGED except where it lacks `code` (R4). **SAM SHALL be brought into
   compliance**: `_response` adds `success` (derived from the status range); `_error` inherits
   `success:false`. Centralized in those two functions so every route converts at once.
4. Both planes SHALL keep the real HTTP status; `success` is redundant parity, never a replacement.
5. Every future backend module SHALL emit this envelope (enforced by the steering doc, R6).

### R2 — Every handler is fail-loud with a bodied 5xx (P4) — all backends

Acceptance criteria:
1. WHEN a handler hits an exception NOT mapped to a specific status, THEN it SHALL log the full
   traceback server-side (route + request id) and return a bodied `500` envelope
   (`{success:false, error:"Internal error", code:"errors.api.serverError"}`) — never an empty 502.
2. The 5xx body SHALL NOT leak internals (no stack trace / exception text / PII) to the client.
3. The catch-all SHALL be LAST so it never shadows the anticipated mappings (422/409/403/404/501
   keep their statuses/bodies).
4. EVERY SAM handler SHALL have this catch-all — Members first, then an audit of all others
   (`sam/pretokengen`, any future edge). A non-HTTP handler (e.g. a Cognito trigger) uses the
   equivalent "log + fail closed" form.

### R3 — The SPA surfaces structured errors (P3) — all UI apps

Acceptance criteria:
1. The API service layer SHALL preserve the full envelope on a non-2xx: a caller MUST reach
   `code`, `error`, `errors`, `reasons` — not only a flattened `Error.message`.
2. Add/Edit forms SHALL render each `errors[]` entry **inline against its `field`** (localized via
   `entry.code`, falling back to `entry.detail`) PLUS a summary toast; an entry whose `field` has no
   matching form control folds into the toast (never dropped).
3. Transition/action flows SHALL render `reasons[]` (each localized via `entry.code`, else `detail`).
4. A genuinely unexpected failure (network / non-JSON / no body) SHALL fall back to a localized
   generic message.
5. No regression to happy paths or existing 401-refresh/retry behavior.

### R4 — Localized, code-driven messages (P3) — IN SCOPE

**User story:** As a Dutch user, when an action is rejected I want the message in Dutch, not a raw
English backend string.

Grounding: the platform ALREADY has the i18n taxonomy for this — `TRANSLATION_KEY_CONVENTIONS.md`
defines an **`errors`** namespace (categories `api`, `validation`, `invoice`, `data`, `generic`, …)
and a **`validation`** namespace (`required`, `format`, `range`, …). v1.0 does NOT invent a new
namespace; error `code`s ARE (or map to) these existing keys.

Acceptance criteria:
1. The error envelope SHALL carry a stable machine **`code`** (+ optional `params`) for every
   anticipated error, where `code` is a key in the existing `errors`/`validation` namespaces (e.g.
   `validation.required`, `errors.api.notFound`, `errors.invoice.emailMissing`). Each `errors[]` /
   `reasons[]` entry SHALL carry its own `code` (+ `params?`) AND a human `detail` (RFC 9457
   per-entry shape), never English-only.
2. The SPA SHALL resolve `code → localized copy` (NL/EN) via `useTypedTranslation` against those
   namespaces (per `TRANSLATION_KEY_CONVENTIONS.md`), with the backend `error` string as the
   DEV/last-resort fallback only.
3. This SHALL remove the string-sniffing anti-pattern (ZZP's `errorMsg.includes('email')`) — that
   case becomes the `errors.invoice.emailMissing` code.
4. New codes SHALL be added to BOTH language files (nl + en) under the correct existing category,
   following the conventions doc (camelCase keys, 2–4 levels, no duplicates); the completeness check
   passes.
5. Backend `error` text MAY stay English (fallback only); the USER-VISIBLE message is the localized
   `code`. Rollout: v1.0 wires the mechanism + converts the Members + ZZP-invoice surfaces; a
   surface without codes degrades gracefully to the English fallback until migrated.

### R5 — Verified, not regressed

Acceptance criteria:
1. A test SHALL prove the SAM catch-all yields a bodied 500 (not a raise/empty), anticipated
   mappings unchanged.
2. A test SHALL prove the unified envelope (success `{success:true,data}`, error
   `{success:false,error,code,...}`) with correct status.
3. A frontend test SHALL prove: a 422 renders inline field errors + toast (LOCALIZED via `code`), a
   409 renders reasons, a network failure shows the localized fallback.
4. Full SAM suite green; affected frontend tests green.

### R6 — The standard is codified as v1.0 steering (P5) — all apps

Acceptance criteria:
1. A VERSIONED steering doc (`v1.0`) SHALL define, for ALL current and future UI/UX apps + backends:
   the envelope (R1), the fail-loud catch-all (R2), structured-error surfacing (R3), and the
   code-driven localization contract (R4).
2. It SHALL name Flask as the reference implementation (P1) and give the canonical examples on each
   plane (Flask/ZZP + SAM Members).
3. It SHALL be discoverable from the steering index and cross-link the Fail-loud integrity + Shared
   frontend component specs.
4. The doc SHALL carry a version (v1.0) and a changelog stub so future revisions are tracked.

### R7 — A documented structure for shared building blocks (deliverable C)

**User story:** As a developer, I want a documented, best-practice STRUCTURE for shared frontend/
backend building blocks — so `applyApiError` + the error contract are discoverable and reusable the
same way the Table Filter Framework v2 is, and so future shared blocks follow one pattern.

Model: the Table Filter Framework v2 — a **Frameworks spec dir**
(`.kiro/specs/Common/Frameworks/table-filter-framework-v2/{requirements,design,tasks}.md`) + a
**steering pointer** (a section in `32-frontend-ui.md` naming the hooks/components, linking the
guide, and citing a **Reference Implementation**). v1.0 establishes the SAME structure for the
error/response standard AND documents the structure itself so the next shared block reuses it.

Acceptance criteria:
1. The standard SHALL live as a Frameworks spec dir (this spec, located to sit with the other
   frameworks) with `requirements/design/tasks`, mirroring Filter Framework v2's layout.
2. A NEW generic steering file `.kiro/steering/37-shared-building-blocks.md` (`inclusion: auto`,
   `3x` layer) SHALL be created because this block is FULL-STACK and `32-frontend-ui.md` is
   frontend-`fileMatch`-scoped (it would never load on the backend). `37` SHALL:
   - document the reusable 4-part STRUCTURE convention (Frameworks spec + shared code path + steering
     pointer + reference implementation) as the TEMPLATE all future blocks follow;
   - state the "when to register" bar — a block earns a row only if it is cross-cutting/reused across
     modules AND backed by a Frameworks guide (not one-off helpers or pure styling conventions);
   - be the REGISTRY of ALL blocks as POINTER rows (never copies — `00`'s "point, don't copy"), with
     columns Block · Scope · Status · Guide · Reference impl. Seeded with Table Filter Framework v2
     (frontend, Stable — detailed pointer stays in `32`) and this API standard (full-stack,
     In-progress).
3. `32-frontend-ui.md` SHALL keep its frontend-only "Filters" section (+ a one-line link to `37`);
   `00-index.md` SHALL be updated (add `37` to the `3x` table + `auto` list, with rationale). No
   fact is duplicated across `32`/`37`/the guide.
4. `applyApiError` + `ApiError` SHALL live at a discoverable shared path (e.g. `frontend/src/shared/
   api/`), not buried in a module — consistent with how Filter Framework v2 exposes shared
   hooks/components.

## Out of scope

- **Rewriting the Flask apps' shape** (P1: Flask IS the standard; it only GAINS `code`s per R4 as
  surfaces are migrated). Route/business logic and `data` payloads are untouched.
- Migrating EVERY existing backend message to a `code` in one pass — v1.0 defines the mechanism and
  codes the HANDLER-LEVEL (summary) errors + the ZZP-invoice surface; other surfaces migrate
  incrementally behind the same contract (tracked, not hidden).
- **Per-field codes in the FLASK apps — deferred.** Flask has NO per-field `errors` structure today
  (flat `{error}` only), so per-field coding there is a larger, per-route effort that migrates later
  behind this same contract. NOTE: per-field codes ARE fully in scope for **SAM Members** now
  (deliverable B — Phase 3 converts the domain validators + the coupled `== "is required"` prune,
  with tests). So this is a NEW capability v1.0 raises for both planes, applied to Members first.
- A visual redesign of toasts/inline errors (uses the existing Chakra toast + form-field error UI).

Note: making the SAM codebase COMPLY with the standard is explicitly IN scope everywhere — nothing
about SAM compliance is excluded. (The s5k `_reject_invalid_overlay_enum_values` line already emits
a compliant 422; it needs no re-fix, but that is a statement of current compliance, not an
exclusion.)

## Relationships

- **Fail-loud integrity spec** — shared philosophy (P4); this spec is the user-visible half.
- **Shared frontend component library spec** — the SPA `applyApiError` helper + the code→copy map
  are shared building blocks.
