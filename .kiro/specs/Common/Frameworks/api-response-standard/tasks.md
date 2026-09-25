# Platform API response & error standard v1.0 — Tasks

Legend: `[ ]` todo · `(dt)` test-first · `[H]` human-gated (deploy). SAM tests via `sam/pytest.ini`
(steering 34/35); frontend via `vitest`. Flask is the reference (P1) — its shape is not changed, it
only GAINS `code`s as surfaces migrate. Ship SAM via `deploy-sam-members.yml`, frontend via Pages.

**Three deliverables:** **A** = the standard incl. i18n (Phases 1–3 contract + Phase 5 steering);
**B** = implement it in SAM Members as-is today (Phases 1–4 wired into the real handler + modals +
Phase 6 verify); **C** = documented shared-building-block structure (Phase 5.1/5.3/5.4 + the shared
`frontend/src/shared/api/` code path).

## Phase 1 — SAM envelope + fail-loud catch-all (R1, R2 · C1/C2)
- [x] **1.1 (dt)** Handler test: inject a service whose dispatch method raises a plain `Exception`;
  assert `statusCode == 500`, body `{success:false, error:"Internal error",
  code:"errors.api.serverError"}`, NO leaked exception text.
  → `test_unhandled_exception_returns_bodied_500_not_empty_502` (asserts `'boom' not in body`).
- [x] **1.2 (dt)** Envelope test: success body `{success:true, data}`; error body
  `{success:false, error, code?, errors?/reasons?}`; each with the correct HTTP status.
  → `test_success_response_carries_success_true_and_data_envelope` +
  `test_validation_error_carries_success_false_error_envelope`.
- [x] **1.3 (dt)** Regression test: anticipated mappings unchanged — `MemberValidationError → 422
  {errors}`, `TransitionDenied → 409 {reasons}`, `ScopeDenied → 403`, `MemberNotFound → 404`,
  `RouteNotImplemented → 501` (catch-all does not shadow them).
  → `test_transition_denied_carries_success_false_and_reasons` +
  `test_catch_all_does_not_shadow_anticipated_mappings` + the pre-existing 422/409/403 dispatch tests
  (all green in the full SAM run).
- [x] **1.4** Unify the envelope in `sam/members/handler/app.py`: `_response` adds
  `success = 2xx?`; `_error` gains `code`/`params` kwargs and inherits `success:false`. Centralized
  so ALL routes convert at once. NOTE: the "update exact-body-equality tests" clause was a NO-OP —
  no SAM test asserts `== {"data":...}`/`== {"error":...}`; all read specific keys
  (`["data"]`/`["error"]`/`["errors"]`/`["reasons"]`), which persist.
- [x] **1.5** Add the final `except Exception` to `_dispatch` in `handler`, AFTER the anticipated
  `except`s: `logger.exception(route, request_id)` + `return _error(500, "Internal error",
  code="errors.api.serverError")`. No client-side leak. (`request_id` from
  `getattr(context, "aws_request_id", None)`.)

## Phase 2 — SAM-wide fail-loud audit (R2.4 · C1)
- [x] **2.1** Audit every SAM entry point for a last-resort catch-all. FINDING: exactly TWO
  Lambda entry points exist (`grep 'def handler'` across `sam/**`, excluding `.aws-sam/` build
  copies):
  - `sam/members/handler/app.py` — API-GW-proxy → **bodied-500** catch-all (done in Phase 1).
  - `sam/pretokengen/handler.py` — Cognito V2 pre-token-gen trigger (returns the event, not an
    API-GW response) → **already "log + fail closed"** and compliant: its runtime computation is
    wrapped in `try/except`, config errors (`DynamoDBConfigError`) RE-RAISE (fail-fast on deploy
    misconfig), any other runtime error logs by identity + exception TYPE only (no secret/payload
    leak) and returns the event unmutated (login unbroken, entitlement claim omitted — fail-closed).
    The pre-try calls (`_identify_user` raising on a userless event, `_init_reader` propagating a
    config error) are deliberately outside the guard: a userless Cognito event / a deploy misconfig
    SHOULD surface, and there is nothing to fail-closed to.
- [x] **2.2** Apply the missing catch-all — **NO-OP**: both handlers already conform (Members via
  Phase 1; pretokengen already log-and-fail-closed). No handler is missing its catch-all, so no new
  code/test is needed here. (Pretokengen's fail-safe/fail-fast behaviour is already covered by its
  own tests under `sam/tests`.)

## Phase 3 — Error codes + i18n, RFC 9457 (R4 · C4) — IN SCOPE [Deliverable A + B]

SCOPE = the FULL standard applied to Members (deliverable B: "implement it as-is today"), NOT just
handler-level. That means BOTH the top-level summary `code` AND per-field `errors[]` codes (RFC 9457
`{field, code, params?, detail}`). No per-field deferral for Members. (Flask surfaces migrate later
behind the same contract — Flask has NO per-field structure today, so that is a separate effort.)

### 3a — Shared field-error vocabulary + shape (the standard artifact)
- [x] **3.1** Add a `FieldError` value + a CODE-CONSTANTS module in the SAM domain (e.g.
  `sam/members/domain/error_codes.py` — or `sam/shared/` if it should be plane-wide): `FieldError =
  {code: str, params: dict|None, detail: str}` (RFC 9457 per-entry). Define the field-level codes as
  keys in the EXISTING `errors` i18n namespace (do NOT invent a namespace): field-level validation
  codes under the `errors.validation.*` category — `errors.validation.required`,
  `errors.validation.mustNotBeBlank`, `errors.validation.mustBeAString`,
  `errors.validation.mustBeOneOf` (`params.allowed`), `errors.validation.invalidDate`,
  `errors.validation.invalidFormat`; plus `errors.member.numberFormat`, `errors.membershiptype.*`
  (tenant/typeCode/label/order/unknownReference/retired), `errors.enum.roleRestricted`
  (`params.roles`). **Standard improved (agreed): field-level codes are homed under the `errors`
  namespace's `validation` category, NOT the standalone `validation` namespace — that file groups
  keys under sub-objects where a flat leaf has no home and `required` is an object; one namespace
  keeps resolution + completeness uniform.**
  → DONE: `sam/members/domain/error_codes.py` — frozen `FieldError(code, detail, params=None)` with
  `.as_entry(field_key=)` → RFC 9457 dict (omits `field`/`params` when unset). Kept domain-local
  (not `sam/shared/`): only Members emits per-field codes today. Constants map to EXISTING namespaces
  (`VALIDATION_REQUIRED = "validation.required"` reused; date msgs fold to `validation.invalidDate`;
  unsupported-type → `validation.invalidFormat`). Import + frozen + entry shape smoke-verified.

### 3b — Domain validators emit codes (fixed_fields, membership_service, membership_type_catalog)
- [x] **3.2 (dt)** Test-first: pin the NEW per-field shape — `validate_fixed_fields` / the service
  validators put a `FieldError` (code+params+detail) in the `errors` map, not a bare string; the
  existing behavioural tests (required, blank-optional-valid, mustBeOneOf, member_number format,
  role-gated enum, catalog validation) keep their PASS/FAIL outcomes but now assert on `.code`.
  → DONE: `sam/tests/test_field_error_codes.py` — asserts `errors[key]` is a `FieldError` with
  `.code`/`.detail`, `.params.allowed` on mustBeOneOf, English detail preserved, + `.as_entry()`
  RFC 9457 shape. Verified test-first: 11 shape assertions FAIL against the current string-returning
  validators (the 2 module-level tests pass), confirming the tests bite before 3.3.
- [x] **3.3** Convert the domain `errors`-map VALUES to `FieldError` across `fixed_fields.py`,
  `membership_service.py`, `membership_type_catalog.py`. **Update the coupled prune**:
  `membership_service.py` `if errors.get(dotted) == "is required"` → compare
  `errors.get(dotted).code == VALIDATION_REQUIRED` (with a test proving the show_when
  hidden-not-required prune still works). Keep the human `detail` (the current English text) on each
  `FieldError` so nothing is lost.
  → DONE: all three modules emit `FieldError`. `fixed_fields` (`_validate_value`/`_validate_date`/
  `validate_member_number_format`/`validate_fixed_fields` + `FieldValidationError.errors` typed
  `{str: FieldError}`); `membership_service` (all 5 `errors`-map helpers + the 2 membership-type-ref
  raises + `MemberValidationError`, which now coerces via `_as_field_error` so tenant-hook/legacy
  strings wrap into `validation.invalidFormat` keeping the string as `detail`); `membership_type_catalog`
  (`validate()` + `from_item`). The coupled prune now compares `.code == VALIDATION_REQUIRED` (kept the
  hidden-not-required behaviour; lifecycle prune test still green). Two breaking existing assertions
  updated (`test_fixed_fields.py` blank→`.code/.detail`; scope-dimension choices→`.detail`+`.params`).
  Remaining 13 full-suite failures are ALL the handler serializing the `FieldError` map (json.dumps) —
  fixed by 3.4/3.5.

### 3c — Handler emits the RFC envelope (summary code + errors[]/reasons[] arrays)
- [x] **3.4** Handler `_error(...)` calls in `sam/members/handler/app.py` carry a `code`
  (auth-phase 401/403/503 + dispatch-phase mappings). Existing i18n keys reused: 500
  `errors.api.serverError` (done), 404 `errors.api.notFound`, 403 `errors.api.forbidden`, 401
  `errors.api.unauthorized`, 503 `errors.api.serviceUnavailable`, 400 `errors.api.badRequest`. NEW
  keys: 405 `errors.api.methodNotAllowed`, 501 `errors.api.notImplemented`, 422 summary
  `errors.validation.failed`, `errors.transition.denied`, `errors.membershiptype.conflict`.
  → DONE: every `_error(...)` site now carries its `code` (route-resolve 404/405, auth 401/403/503,
  dispatch 501/404/409/422/403/400/500).
- [x] **3.5** Shape the handler's structured details as RFC 9457 ARRAYS: map the domain's
  `{field: FieldError}` → `errors: [{field, code, params?, detail}, …]` on the 422; map
  `TransitionDenied.reasons` → `reasons: [{code, params?, detail}, …]` on the 409. (A tiny helper in
  the handler converts the domain map/list to the array shape.)
  → DONE: `_field_errors_array(map)` (uses `FieldError.as_entry(field_key=)`, tolerant of a legacy
  string → `errors.api.badRequest`) on both 422 paths; `_reasons_array(reasons)` (wraps each
  string reason under `errors.transition.denied`, passes a `FieldError` through, tolerant of a
  single string) on the 409. Handler imports `FieldError`. Updated the handler-consuming tests to
  the array shape (`_error_fields(resp)` helper in write-dispatch; inline `{e["field"]}` in the
  catalog-routes tests; envelope test asserts `code`+`isinstance(list)`).
- [x] **3.6 (dt)** Handler/edge test: a 422 returns `errors` as an ARRAY of
  `{field, code, params?, detail}` (assert a known field's `code`); a 409 returns `reasons` as an
  array of `{code, detail}`; the top-level `code` is set per mapping.
  → DONE: `sam/tests/test_members_write_dispatch.py` — `test_422_errors_is_rfc9457_array_with_field_code_detail`
  (422 `errors` is a list, `personal.first_name` entry `code == validation.required`, top-level
  `code == errors.validation.failed`, no empty `params`), `test_422_mustBeOneOf_entry_carries_allowed_params`
  (params.allowed present), `test_409_reasons_is_rfc9457_array_with_code_and_detail` (409 `reasons`
  list of `{code, detail}`, no `field`, top-level `code == errors.transition.denied`). Full SAM suite
  green (all dots / 100% / zero F·E in the `-q` run).

### 3d — i18n copy
- [x] **3.7 (dt)** Add every NEW code (3.1 + 3.4) to the NL + EN `errors.json` / `validation`
  namespace (camelCase, per `TRANSLATION_KEY_CONVENTIONS.md`, with `{{param}}` interpolation where
  used); a test asserts a code resolves in both languages and an unknown code degrades to the
  English `detail`/`error` fallback. Run the i18n completeness check.
  → DONE: all new codes added to `frontend/src/locales/{nl,en}/errors.json` under ONE namespace
  (`errors`): `api.methodNotAllowed`/`notImplemented`; `validation.{failed,mustNotBeBlank,mustBeAString,
  mustBeOneOf({{allowed}})}`; new categories `member.numberFormat`, `enum.roleRestricted({{roles}})`,
  `transition.denied`, `membershiptype.{conflict,tenant,typeCode,label,order,unknownReference({{type_code}}),
  retired({{type_code}})}`; `invoice.emailMissing`. Completeness checker: `errors` namespace 125=125,
  0 missing/extra in both langs (the only reported drift is 4 pre-existing `admin.landingPage.editor.*`
  keys — OUT of scope, flagged not touched). Test `frontend/src/shared/api/apiErrorCodes.test.ts`
  (37 cases) green: every code resolves in nl+en via `t('errors:<path>')`, params interpolate,
  reused `errors.validation.required` resolves, unknown code → no key (fallback path). vitest exit 0.
- [x] **3.8** Remove the string-sniff anti-pattern (ZZP `errorMsg.includes('email')`) → replace with
  the `errors.invoice.emailMissing` code + copy.
  → DONE (Flask GAINS a code, shape unchanged — P1). Backend: new `InvoiceEmailMissingError(ValueError)`
  in `invoice_email_service.py` carrying `code = "errors.invoice.emailMissing"`, raised at the
  compose-preview missing-email site + the 2 send/reminder return sites (now include `code`); the
  `email-preview` route surfaces `getattr(ve, "code", None)` on the 400 (still `ValueError`→400, English
  `error` intact). Frontend: `ZZPInvoiceDetail.tsx` — both send-preview `catch`/else branches replaced
  by `surfaceSendPreviewError(code, error)` (code-first: `errors.invoice.emailMissing`→localized warning,
  other known code→`t(code)`, else backend `error`, else generic); `EmailPreviewResponse` gains `code?`.
  Verified: backend 27 passed (incl. new `test_email_preview_missing_email_carries_code` + unchanged
  message tests), frontend 19 passed, full `tsc --noEmit` exit 0.

## Phase 4 — Frontend structured-error surfacing (R3 · C3) [Deliverable B; shared code = C]
- [x] **4.1 (dt)** API-service test: a mocked 422 `{error, code, errors:[{field,code,params?,detail}]}`
  and 409 `{error, reasons:[{code,detail}]}` (RFC 9457 arrays) cause `handleResponse` to throw an
  `ApiError` carrying `status/code/params/errors[]/reasons[]` (not a flattened `Error`); a legacy
  `reasons: string[]` is tolerated; non-JSON/empty → `HTTP <status>`; 200 still resolves;
  401-refresh/retry unchanged.
  → DONE: `frontend/src/services/membersApiService.apiError.test.ts` (5 cases) — 422 field-array,
  409 reasons-array, legacy `string[]`, non-JSON→`HTTP 502`, 2xx resolves. Test-first: 4 failed
  against the plain-`Error` handler; green after 4.2. 401 path untouched (it lives in `membersRequest`
  before `handleResponse`; the existing 401 retry test stays green).
- [x] **4.2** Add the shared `ApiError` (status, message, code?, params?, errors?: FieldErrorEntry[],
  reasons?: ReasonEntry[]|string[]) + the `FieldErrorEntry`/`ReasonEntry` types at a DISCOVERABLE
  shared path (e.g. `frontend/src/shared/api/` — NOT inside `components/members/`, per C6). Change
  `membersApiService.handleResponse` to throw it on `!response.ok` (backward compatible —
  `err.message` still reads).
  → DONE: `frontend/src/shared/api/ApiError.ts` — `ApiError extends Error` (status, code?, params?,
  errors?: FieldErrorEntry[], reasons?: ReasonEntry[]|string[]) + `hasFieldErrors()`/`hasReasons()`
  + `apiErrorFromResponse(response)` (JSON-tolerant → `{}`). `handleResponse` now
  `throw await apiErrorFromResponse(response)`. Backward compatible: `.message` = `error` || legacy
  `message` || `HTTP <status>` (kept a pre-existing test that relied on the `message` fallback green).
  Full existing membersApiService suite (28) + new suite (5) green.
- [x] **4.3** Add the shared `applyApiError(err, {toast, t, setFieldError})` helper (same shared
  path): each `errors[]` entry → inline field error via `line(e,t) = t(e.code,e.params) || e.detail`,
  matched to the form field (unmatched → toast); summary toast = `t(code, params)` || joined
  reasons/unmatched || `error` || `t('errors.api.unknownError')`; `reasons[]` entries → toast (legacy
  `string[]` tolerated); unknown/network → `t('errors.api.serverError')`.
  → DONE: `frontend/src/shared/api/applyApiError.ts` — resolves codes as `t('errors:<path>', params)`
  (first dot → namespace separator; robust to i18next echoing full-key OR path-only on a miss),
  inline via `setFieldError` with a `fieldNameFor` mapper (dotted → the form's own field name) +
  `knownFields`; unmatched fold into the summary; summary ALWAYS shown for an ApiError (inline is
  additive, per R3); reasons + legacy `string[]` tolerated; non-ApiError → `errors:api.serverError`.
  Unit test `applyApiError.test.ts` (8 cases, real i18n) green incl. nl localization + fallbacks.
- [x] **4.4 (dt)** Modal tests: Add/Edit — a 422 `errors[]` renders the matching field error INLINE
  (LOCALIZED via `code`, falling back to `detail`) + a toast, an unmatched `field` folds into the
  toast; Transition — a 409 `reasons[]` shows in the toast; a network failure shows the localized
  fallback.
  → DONE: `frontend/src/__tests__/MembersModals.apiError.test.tsx` (5 cases) — Add: 422 inline field
  error (via mapped `setFieldError`) + summary toast, unmatched folds into toast, network→fallback;
  Transition: 409 reasons in toast + network→fallback. Proves the WIRING through real modals (key-echo
  env asserts the `detail`/key; code LOCALIZATION proven by applyApiError.test.ts). vitest exit 0.
- [x] **4.5** Wire `MembersAddModal`, `MembersEditModal`, `MembersTransitionModal` `catch` blocks to
  `applyApiError`. Convert the ZZP-invoice page's `catch` sites to the same helper (reference parity).
  → DONE for the 3 Members modals: Add/Edit pass `{toast, t, setFieldError, fieldNameFor}` (a
  per-modal dotted→bare mapper honoring the scope-dimension `region`); Transition passes `{toast, t}`
  (no form fields). **ZZP parity NOTE:** the ZZP page consumes Flask RESPONSE objects
  (`resp.success/error/code`), not a thrown `ApiError`, so a literal `applyApiError` wiring would be
  lossy (drops `resp.error`); ZZP already got code-first handling in task 3.8 (`surfaceSendPreviewError`
  → `errors.invoice.emailMissing`). Full `applyApiError` parity for ZZP needs the Flask ZZP service to
  THROW `ApiError` — deferred with the incremental Flask migration (spec "Out of scope"). Full
  frontend `tsc --noEmit` exit 0; 97 frontend tests green.

## Phase 5 — Steering: generic building-blocks file + this block's guide (R6, R7 · C5/C6) [Deliverable A + C]
- [x] **5.1** Locate this spec as a Frameworks spec dir alongside `table-filter-framework-v2/`
  (`.kiro/specs/Common/Frameworks/api-response-standard/{requirements,design,tasks}.md`) so shared
  blocks share one home. (Move/rename from `Common/error-surfacing-standard/` if agreed.)
  → DONE: moved `Common/error-surfacing-standard/` → `Common/Frameworks/api-response-standard/`
  (plain `mv` — the spec was untracked; no git history to preserve). Updated the references: this
  file (self), `myBacklog/backlog.md`, and the `ApiError.ts` docstring now cite the new path. The
  `37` registry row already points here (path is now real).
- [x] **5.2 [Deliverable C]** Create the GENERIC steering file
  `.kiro/steering/37-shared-building-blocks.md` (`inclusion: auto`, `3x` layer). It (a) documents
  the reusable 4-part STRUCTURE convention (Frameworks spec + shared code path + steering pointer +
  reference implementation), (b) states the "when to register" bar (cross-cutting/reused across
  modules AND backed by a Frameworks guide — NOT one-off helpers or pure styling), and (c) is the
  REGISTRY of ALL blocks as POINTER rows (no copying — single-source per `00`) with columns
  Block · Scope · Status · Guide · Reference impl. Seed rows:
  - Table Filter Framework v2 · frontend · Stable · `Common/Frameworks/table-filter-framework-v2/` ·
    `ZZPInvoices.tsx` (note: detailed pointer stays in `32`).
  - API response & error standard v1.0 · full-stack · In-progress · `Common/Frameworks/api-response-standard/` · SAM Members; ZZP invoice.
  - Lazy edit-on-click dropdown · frontend · Planned · tbd.
  State the convention as the TEMPLATE future blocks follow.
  → DONE: `.kiro/steering/37-shared-building-blocks.md` exists with `inclusion: auto`. Has (a) the
  4-part template (Frameworks spec + shared code path + steering pointer + reference impl), (b) the
  two-part "when to register" bar (cross-cutting AND Frameworks-backed; excludes one-off helpers /
  pure styling → stay in `32`), (c) the registry table (Block·Scope·Status·Guide·Reference) with the
  3 seed rows. Explicitly documents that the 2 TEST-infra Frameworks (`test-maintenance-framework`,
  `chakra-test-mock-framework`) are NOT registered (owned by `33`/`34`) — intentional, not stale.
- [x] **5.3** Flesh out THIS block's row/section in `37`: name `ApiError` / `applyApiError` / the
  `_response`/`_error` envelope / the `errors`+`validation` code namespaces; link this guide; cite
  SAM Members (deliverable B) + ZZP invoice as reference implementations. Put the VERSIONED (`v1.0`
  + changelog) contract detail in the Frameworks guide (not duplicated in `37`) — name Flask as the
  reference (P1), reference `TRANSLATION_KEY_CONVENTIONS.md`, cross-link the Fail-loud spec.
  → DONE: `37`'s block section names `ApiError`/`applyApiError`/`_response`/`_error`/the
  `errors.validation.*` codes, cites Flask (P1 envelope) + SAM Members + ZZP invoice, status now
  **Stable**, points to the guide. The VERSIONED contract + a **Version & changelog** section (v1.0)
  live in the guide `design.md` (NOT duplicated in `37`), cross-linking `TRANSLATION_KEY_CONVENTIONS.md`
  and the Fail-loud spec.
- [x] **5.4** Update `.kiro/steering/00-index.md`: add `37` to the `3x` layer table + the `auto`
  load-behavior list, with the one-line rationale (a full-stack registry must load on both planes →
  `auto`, not `fileMatch`). Add a one-line "see `37` for the building-block registry" link to
  `32-frontend-ui.md`'s Filters section (which stays the frontend-only detailed pointer).
  → DONE: `00-index.md` — `37-shared-building-blocks.md` added to the `3x` layer row + the `auto`
  load list, with the rationale (full-stack registry → discoverable on both planes → `auto`, not
  `fileMatch`; thin registry, low always-on cost). `32-frontend-ui.md` Filters section gained a
  one-line pointer to `37` (the detailed Filters guidance stays in `32`).

## Phase 6 — Verify + ship (R5)
- [x] **6.1** SAM suite green (`sam/pytest.ini`) + affected frontend tests green (judge by summary).
  → DONE: full SAM suite `SAM_EXIT=0` (all dots/100%); frontend 130 passed across 10 files
  (`FE_EXIT=0` — `shared/api` ApiError/applyApiError/apiErrorCodes, membersApiService (+apiError),
  zzpInvoiceService, MembersModals.apiError, MembersAddModal, MembersTransitions, ZZP preview,
  i18n); backend ZZP 27 passed (`BE_EXIT=0`). Full `tsc --noEmit` exit 0 (run in Phase 4).
- [ ] **6.2 [H]** Ship: SAM via `deploy-sam-members.yml`; frontend via Pages. (Phase 2 audit +
  broader code migration may be separate PRs.)
- [ ] **6.3 [H]** Prod verify: a known 422 → inline LOCALIZED field error + toast, no 502; a 409 →
  reasons shown; an induced unhandled error → bodied 500 (not empty 502) + traceback in CloudWatch;
  toggle NL/EN and confirm the message localizes.

## Done criteria
- ONE envelope on every backend (`{success, data|error, code?, errors?, reasons?}` + real status);
  Flask unchanged except added `code`s.
- No handler can return an empty 5xx on an unanticipated error — bodied 500 + logged traceback.
- Every surfaced error is LOCALIZED (NL/EN) via `code`; no raw-English or string-sniffing.
- The SPA renders 422 field errors inline + 409 reasons; genuine network failures show a localized
  fallback.
- The standard is written as VERSIONED steering (v1.0) all apps conform to.
- All tests green; verified in prod.

## Out of scope
- Re-fixing the s5k `_reject_invalid_overlay_enum_values` TypeError (already emits a compliant 422 —
  a statement of current compliance, NOT an exclusion; SAM compliance everywhere is in scope).
- Rewriting the Flask apps' shape (P1: Flask is the reference; it only GAINS `code`s). Route logic
  and `data` payloads unchanged.
- Migrating EVERY legacy backend message to a code in one pass — v1.0 defines the mechanism +
  converts the Members + ZZP-invoice surfaces; the rest migrate incrementally behind the contract
  (tracked here, not hidden).
- A visual redesign of the toast / inline-error UI (reuse existing Chakra components).
