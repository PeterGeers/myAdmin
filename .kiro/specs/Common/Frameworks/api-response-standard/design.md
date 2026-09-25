# Error surfacing standard (SAM ⊕ Flask) — Design
# Platform API response & error standard v1.0 — Design

## Overview

Implement **v1.0 of the platform API response & error standard** so every backend emits one
envelope, every failure is a bodied response, and every surfaced message is localized — then codify
it as versioned steering all UI/UX apps conform to. Flask is the reference (P1); SAM is brought into
compliance. Coordinated changes:

- **C1 (backend, fail-loud):** a last-resort catch-all in each SAM handler → bodied 5xx + logged
  traceback.
- **C2 (backend, envelope):** SAM adopts the Flask envelope — `_response`/`_error` add `success`
  (Option 3). One wire shape platform-wide.
- **C3 (frontend):** preserve the full envelope through the API service and render structured errors
  (inline 422 field errors + summary toast, 409 reasons).
- **C4 (i18n / codes):** error bodies carry a stable machine `code`; the SPA maps `code → localized`
  copy against the EXISTING `errors`/`validation` i18n namespaces, with the English `error` as
  fallback. Removes the raw-English + string-sniff anti-pattern.
- **C5 (steering v1.0):** a versioned doc that ALL apps conform to.
- **C6 (shared-block structure):** document + follow a reusable structure for shared building blocks
  (Frameworks spec + shared code path + steering pointer + reference implementation), modeled on the
  Table Filter Framework v2 — deliverable C.

Three deliverables map to these: **A = the standard** (C2/C4/C5), **B = implement in SAM Members
today** (C1/C2/C3/C4 wired into the real Members handler + modals), **C = the shared-block
structure** (C6).

Grounding (verified in code):
- `sam/members/handler/app.py`: `_response(status, payload)` builds the API-GW response;
  `_error(status, message, **extra)` → `{"error": message, **extra}`; `_dispatch` maps anticipated
  exceptions but has **no final `except Exception`**.
- Flask reference: `backend/src/*_routes.py` return `jsonify({"success": ...}), <status>` — real
  status + `{success}` body (NOT 200-with-success).
- `frontend/src/services/membersApiService.ts`: `handleResponse` flattens the body to a single
  `Error.message`, dropping `errors`/`reasons`.
- i18n gap: `ZZPInvoiceDetail.tsx` shows `resp.error` RAW (English) and string-sniffs it
  (`errorMsg.includes('email')`) — proof the backend-message path is unlocalized today.

Grounding (verified in code):
- `sam/members/handler/app.py`: `_response(status, payload)` builds the bodied API-GW response;
  `_error(status, message, **extra)` → `{"error": message, **extra}`. `_dispatch` is wrapped in a
  `try/except` chain that maps anticipated domain exceptions to statuses but has **no final
  `except Exception`**.
- `frontend/src/services/membersApiService.ts`: `handleResponse` does, on `!response.ok`,
  `const error = await response.json().catch(() => ({error:'Unknown error'})); throw new
  Error(error.error || error.message || HTTP <status>)` — it reads the body but **flattens** it to
  a single `Error.message`, dropping `errors`/`reasons`.
- ZZP reference: `frontend/src/services/zzpInvoiceService.ts` (returns the `{success,error}`
  envelope) + `frontend/src/pages/ZZPInvoiceDetail.tsx` (`toast({title: resp.error || t(...)})`).

## C1 — SAM handler catch-all (bodied 500)

Add a FINAL `except Exception` to the `_dispatch` try-block in `app.py::handler`, AFTER every
anticipated mapping:

```python
    try:
        result = _dispatch(spec, request, ctx)
    except RouteNotImplemented: ...        # 501  (unchanged)
    except MemberNotFound: ...             # 404  (unchanged)
    except MembershipTypeConflict: ...     # 409  (unchanged)
    except MembershipTypeValidationError as exc:  # 422 {errors} (unchanged)
    except ScopeDenied: ...                # 403  (unchanged)
    except TransitionDenied as exc: ...    # 409 {reasons} (unchanged)
    except MemberValidationError as exc:   # 422 {errors} (unchanged)
    except KeyError as exc: ...            # 400  (unchanged)
    except Exception:                      # NEW — last resort
        logger.exception("Unhandled error dispatching Members route '%s'", spec.name)
        return _error(500, "Internal error", code="errors.api.serverError")
```

Design points:
- **Ordering:** the catch-all is LAST, so no anticipated mapping is shadowed (R2.3).
- **No leak:** `logger.exception` logs the traceback SERVER-side (CloudWatch); the client gets only
  `{success:false, error:"Internal error", code:"errors.api.serverError"}` (R2.2). No exception
  message/PII crosses the boundary.
- **Scope:** wraps the DOMAIN-DISPATCH phase. The verified-auth phase keeps its own
  `try/except` (401/403/503) — those already return bodied errors, so they're fine; but the audit
  (R2.4) confirms each SAM handler's outermost dispatch is covered.
- **Correlation id (optional):** if a request id is readily available from the Lambda context, pass
  it as `_error(500, "Internal error", code="errors.api.serverError", request_id=...)` so support
  can correlate to the logged traceback. Nice-to-have, not required.

**Other handlers (R2.4):** audit `sam/pretokengen` and any other SAM entry point. A pre-token-gen
Lambda has a different contract (it returns a Cognito trigger event, not an API-GW response), so
its "catch-all" is "log + fail closed" rather than a JSON body — the audit records the right shape
per handler; only API-GW-proxy handlers get the bodied-500 form.

## C2 — SAM adopts the Flask envelope (Option 3 — ONE wire shape)

Corrected framing (verified in `backend/src/*_routes.py`): Flask does NOT return 200 with
`{success:false}` — it returns `jsonify({"success": ..., ...}), <status>`, i.e. **real status +
a `{success}` body**. SAM is also status-based. So the planes only differ in envelope KEYS, and
aligning SAM is cheap. We unify on the Flask shape (SAM aligns TO Flask; the working plane is
untouched):

| Case    | Flask (existing)                         | SAM today            | SAM after (this spec)                         |
|---------|------------------------------------------|----------------------|-----------------------------------------------|
| success | `{success:true, data}` + status          | `{data}` + status    | `{success:true, data}` + status               |
| error   | `{success:false, error}` + status        | `{error, errors?, reasons?}` + status | `{success:false, error, code?, errors?[], reasons?[]}` + status (RFC 9457 entries) |

The change is two functions in ONE file — every route already routes through them:

```python
def _response(status, payload):
    body = {"success": 200 <= status < 300, **payload}   # add success (derived from status)
    return {"statusCode": status, "headers": {...}, "body": json.dumps(body, default=_json_default)}

def _error(status, message, *, code=None, params=None, **extra):
    body = {"error": message, **extra}                    # inherits success:false via status
    if code is not None:
        body["code"] = code                               # stable machine id for i18n (C4)
    if params:
        body["params"] = params                           # interpolation values for the copy
    return _response(status, body)
```

The envelope after v1.0 (both planes): success `{success:true, data}`; error
`{success:false, error, code?, params?, errors?[], reasons?[]}` — all with the real HTTP status.
`errors[]` / `reasons[]` are RFC 9457 §3.1 per-entry arrays: `errors` entry `{field, code, params?,
detail}`, `reasons` entry `{code, params?, detail}`.

Notes:
- Deriving `success` from the status range keeps it consistent by construction (a 2xx is
  `success:true`, everything else `success:false`) — no per-call boolean to get wrong.
- SAM keeps its richer `errors`/`reasons` as an ADDITIVE superset; Flask consumers ignore unknown
  keys, so a shared reader works against both.
- The real HTTP status is retained on both planes (`success` is redundant parity, not a
  replacement) — API Gateway metrics/alarms and `response.ok` keep working.
- Test churn: SAM tests that assert exact-body equality gain a `success` key; tests that read
  `["data"]` / `["error"]` / `["errors"]` are unaffected (those keys persist).

## C3 — Frontend: preserve + render structured errors

### C3a — a typed API error that carries the structure

Introduce a small `MembersApiError` (or reuse a shared one) so the body survives the throw:

```ts
// RFC 9457 per-entry shape: machine `code` + optional `params` + human `detail`.
interface FieldErrorEntry { field: string; code?: string; params?: Record<string, unknown>; detail?: string; }
interface ReasonEntry { code?: string; params?: Record<string, unknown>; detail?: string; }

export class ApiError extends Error {   // shared (not Members-only — v1.0 is platform-wide)
  status: number;
  code?: string;                     // top-level (summary) machine id (i18n key, C4)
  params?: Record<string, unknown>;  // interpolation values for the summary copy
  errors?: FieldErrorEntry[];        // 422 per-field array (RFC 9457 §3.1)
  reasons?: ReasonEntry[] | string[];// 409 denials (array of entries; legacy string[] tolerated)
  constructor(status: number, message: string, opts?: {code?; params?; errors?; reasons?}) { ... }
}
```

Change `handleResponse` so on `!response.ok` it parses the body and throws an `ApiError` carrying
`status`, `error`→`message`, `code`, `params`, `errors`, `reasons` (falling back to `HTTP <status>`
when the body is absent/non-JSON — the genuinely-unexpected path). Backward compatible: existing
`catch` sites that read `err.message` still work; new sites read `err.code`/`err.errors`.

### C3b — a shared `applyApiError` helper (localized via C4)

A single platform helper the modals call in their `catch`, applying the code→localized-copy map.
Each `errors[]`/`reasons[]` entry is localized via its own `code` (RFC 9457), falling back to its
human `detail`:

```ts
const line = (e: {code?: string; params?; detail?: string}, t) =>
  (e.code && t(e.code, e.params)) || e.detail || t('errors.api.unknownError');

function applyApiError(err, {toast, t, setFieldError}): void {
  if (err instanceof ApiError) {
    const unmatched: string[] = [];
    for (const e of err.errors ?? []) {
      if (hasFormField(e.field)) setFieldError(mapFieldName(e.field), line(e, t));  // inline
      else unmatched.push(line(e, t));                                             // → toast
    }
    const reasonLines = (err.reasons ?? []).map((r) =>
      typeof r === 'string' ? (t(r) as string) : line(r, t));   // legacy string[] tolerated
    const summary =
      (err.code && t(err.code, err.params)) ||   // top-level localized summary (C4)
      [...reasonLines, ...unmatched].join('; ') ||
      err.message ||                             // English fallback (dev/last resort)
      t('errors.api.unknownError');
    toast({ title: summary, status: 'error' });
    return;
  }
  toast({ title: t('errors.api.serverError'), status: 'error' });  // network / non-JSON / unknown
}
```

`mapFieldName(field)` maps a dotted key (`personal.first_name`, `overlay.region`) to the form's
Formik field name (the modals already key fields by dotted/overlay key — reuse that mapping); a
`field` with no matching control folds into the toast summary (never dropped, R3.2).

### C3c — wire the modals/pages

`MembersAddModal`, `MembersEditModal`, `MembersTransitionModal` (and, for the reference, the ZZP
pages): replace the generic `catch → toast(genericMessage)` with
`applyApiError(err, {toast, t, setFieldError})`. Formik's `setFieldError`/`setErrors` surfaces the
inline messages; the toast shows the localized summary. `applyApiError` is a SHARED platform helper
(relates to the Shared-frontend-component spec), delivered here as v1.0's canonical implementation.

## C4 — Error codes + localization (i18n)

The user-visible message must be localized (NL/EN), so the wire carries a stable **`code`** and the
SPA owns the copy — the backend `error` string is a dev/last-resort fallback only.

- **Code namespace:** codes ARE keys in the EXISTING `errors` i18n namespace (per
  `TRANSLATION_KEY_CONVENTIONS.md` — camelCase, dotted, no new namespace), resolved as
  `t('errors:<path>', params)` (the `namespace:path` form the i18n tests already use, e.g.
  `i18n.exists('errors:api.networkError')`), e.g. `errors.api.serverError`,
  `errors.member.numberFormat`, `errors.transition.denied`, `errors.membershiptype.conflict`.
  **Field-level validation codes live under that namespace's `validation` category
  (`errors.validation.*` — `required`, `mustNotBeBlank`, `mustBeAString`, `mustBeOneOf`,
  `invalidDate`, `invalidFormat`), NOT the standalone `validation` namespace file.** The `errors`
  namespace already hosts flat string leaves there (`required`, `invalidFormat`, …), the natural
  home; the standalone `validation` namespace groups its keys under sub-objects (`required.field`,
  `format.email`) where a flat leaf like `mustNotBeBlank` has no home and `required` is an OBJECT
  (unresolvable as a string). Keeping every code in ONE namespace file makes resolution and the
  completeness check uniform. Field errors use the same idea:
  `errors["personal.first_name"] = {code: "errors.validation.required", params?}`.
- **Backend:** anticipated errors pass a `code` (and `params` for interpolation) to `_error` /
  the Flask equivalent. Flask GAINS `code`s on the migrated surfaces (P1 — Flask keeps its shape,
  just adds the key). A domain exception can carry its own `code` so the handler maps it directly.
- **Frontend:** the existing i18n resources (`useTypedTranslation` / locale JSON) gain the missing
  keys under the `errors`/`validation` categories with NL + EN copy; `applyApiError` resolves
  `t(code, params)`.
- **Removes the anti-pattern:** ZZP's `errorMsg.toLowerCase().includes('email')` string-sniff
  becomes a real code (`errors.invoice.emailMissing`) with its own localized copy — no string
  matching.
- **Graceful degradation:** a surface not yet emitting codes falls back to the English `error`
  string (today's behavior), so migration is incremental behind the same contract.

### Per-field codes: how the two planes actually stand (verified in code)

Checked `backend/src/*_routes.py` and the SAM domain layer. The reality is the OPPOSITE of "SAM
lags Flask" for per-field errors:

- **Flask has NO per-field error contract at all.** Every Flask failure is a single flat
  `{"success": false, "error": "<English string>"}` (sometimes a raw `str(e)`) + status — no
  `errors` map, no `code`. The SPA localizes by string-matching the message (the ZZP
  `errorMsg.includes('email')` sniff). So there is no Flask per-field pattern to copy.
- **SAM is already AHEAD:** it returns structured per-field 422 detail today (a `{field: msg}` map
  with English VALUES). v1.0 reshapes that to the RFC 9457 `errors[]` array of `{field, code,
  params?, detail}` — the smaller step (add code+array shape); Flask needs the bigger one (it has
  NO per-field structure at all) whenever its validation surfaces migrate.

Consequence for the standard: "Flask is the reference (P1)" holds for the **envelope shape**, but
per-field codes are a **NEW capability v1.0 raises for BOTH planes** — not a "make SAM match Flask".

### Deferred as its own careful pass (NOT in this phase) — per-field code migration

Converting the SAM domain's per-field `errors` VALUES from English strings to codes is a
cross-cutting change across `fixed_fields.py`, `membership_service.py`,
`membership_type_catalog.py`, and it touches a **string-equality comparison** that must be updated
in lockstep: `membership_service.py` does `if errors.get(dotted) == "is required": del errors[...]`
(the show_when "hidden-not-required" prune keys off the literal string). Flipping values to codes
without updating that comparison silently breaks the prune. Because of that coupling + the breadth,
per-field coding is its own pass with a clear shape:
- introduce a small `FieldError` = `{code, params?, detail}` (RFC 9457 per-entry) the domain emits
  instead of raw strings, and shape the handler's 422 body as an `errors[]` array of
  `{field, code, params?, detail}` (from the domain's `{field: FieldError}` map);
- update the `== "is required"` prune to compare the code, not the English string;
- add the field-level codes (`errors.validation.required`, `errors.validation.mustNotBeBlank`,
  `errors.validation.mustBeOneOf` with `params.allowed`, `errors.member.numberFormat`, …) to the locale
  files;
- the SPA already renders `errors` per-field (C3) — it just resolves a code instead of showing raw
  text.
Until then, per-field messages STILL surface (the English string degrades gracefully, R4.5); only
the TOP-LEVEL summary `code` (C4 handler-level) lands in this phase.

## C5 — Steering v1.0 (versioned, all apps)

Add a VERSIONED steering doc (`.kiro/steering/NN-api-response-standard.md`, header `v1.0` +
changelog stub) that ALL current and future UI/UX apps + backends conform to:
- **Envelope (R1, RFC 9457-aligned):** success `{success:true, data}`; error `{success:false,
  error, code?, params?, errors?[], reasons?[]}`; `errors`/`reasons` are per-entry arrays
  (`{field?, code, params?, detail}`, RFC 9457 §3.1); always the real HTTP status; never an empty
  response.
- **Fail-loud (R2):** every handler ends in a catch-all → bodied 5xx (`errors.api.serverError` /
  `errors.generic`), traceback logged, no leak.
- **Frontend (R3):** surface the full envelope via `applyApiError`; never a bare throw that drops
  the body; inline 422 field errors + summary toast; 409 reasons.
- **i18n (R4):** user-visible message = `t(code, params)` resolved against the EXISTING `errors` /
  `validation` namespaces (per `.kiro/specs/Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md`);
  backend `error` is the fallback; no string-sniffing.
- **Reference implementation (P1):** Flask (`backend/src/*_routes.py`, `ZZPInvoiceDetail.tsx`,
  `zzpInvoiceService.ts`); SAM canonical example (Members handler catch-all + `membersApiService` +
  `applyApiError` — deliverable B).
- Cross-link the Fail-loud integrity + Shared-frontend-component specs; add to the steering index.

This standard's pointer lives in the generic `37-shared-building-blocks.md` (C6) — NOT in
`32-frontend-ui.md`, because the block is full-stack and `32` is frontend-`fileMatch`-scoped. The
pointer mirrors the shape of `32`'s "Filters" section (name the building blocks → link the full
guide → cite a reference implementation).

## C6 — A generic shared-building-blocks steering file (deliverable C)

This block spans BOTH planes (backend envelope/catch-all/codes + frontend ApiError/applyApiError/
i18n), so it does NOT belong in `32-frontend-ui.md` — that file is `fileMatch`-scoped to
`frontend/src/**` and would never load while editing backend code. Per the steering model
(`00-index.md`: numeric layers, one fact one place, fold-don't-fork, point-don't-copy), add a NEW
**generic, `auto`-included** file in the `3x` (coding-conventions) layer:

**`.kiro/steering/37-shared-building-blocks.md`** (`inclusion: auto`) — the platform's registry of
reusable building blocks + the STRUCTURE convention for creating them. It:

1. **Documents the reusable structure** (the 4-part convention every block follows):
   - a **Frameworks spec** — `.kiro/specs/Common/Frameworks/<name>/{requirements,design,tasks}.md`;
   - **shared code at a discoverable path** (frontend `frontend/src/shared/<area>/`, backend
     `sam/shared/` or the Flask shared module);
   - a **steering pointer** (a registry row here, or a section in the plane-specific file when the
     block is single-plane — e.g. Filters stays in `32`);
   - a **named reference implementation**.
2. **Is the registry of ALL blocks**, each a POINTER row (never a copy of the guide — single-source,
   `00`'s "point, don't copy"), tagged by SCOPE + STATUS so a dev sees what is reusable TODAY vs
   planned:

   | Block | Scope | Status | Guide | Reference impl |
   |---|---|---|---|---|
   | Table Filter Framework v2 | frontend | Stable | `Common/Frameworks/table-filter-framework-v2/` | `ZZPInvoices.tsx` (detailed pointer in `32`) |
   | API response & error standard v1.0 | **full-stack** | In-progress (spec) | `Common/Frameworks/api-response-standard/` | SAM Members; ZZP invoice |
   | Lazy edit-on-click dropdown | frontend | Planned | tbd | tbd |

   The Table Filter row is a POINTER: the detailed guidance stays in `32-frontend-ui.md` (loaded via
   `fileMatch` when editing `.tsx`); `37` just registers it so ALL blocks are discoverable from one
   place on either plane. No fact is duplicated.

3. **States the "when to register" bar** so the registry stays meaningful, not a dumping ground: a
   block earns a `37` row ONLY when it is (a) cross-cutting / reused across modules AND (b) backed by
   a Frameworks guide. One-off helpers and pure styling conventions (button colours, dark theme in
   `32`) do NOT get registered.

4. **Cross-references the plane-specific steering** so nothing is duplicated: `32-frontend-ui.md`
   keeps its frontend-only "Filters" section (+ a one-line "see `37` for the full building-block
   registry"); `37` owns the cross-cutting/full-stack blocks and the structure convention.

`00-index.md` is updated: add `37` to the `3x` layer table and to the `auto` load-behavior list,
with a one-line rationale (a full-stack registry must load on both planes, so `auto` not
`fileMatch`).

Why `auto` (not `fileMatch`): a `fileMatch` file scoped to one plane can't serve a full-stack
block; the registry must be discoverable whether you're editing a Lambda handler or a React modal.
It's a thin registry (points to guides), so always-on cost is low — consistent with `35`/`36`
being `auto`.

## Testing strategy

- **C1 (SAM catch-all):** a handler test injects a service whose method raises a plain `Exception`
  on a dispatch path; assert `statusCode == 500` with body `{success:false, error, code:
  "errors.api.serverError"}` and NO leaked detail. Regression: 422/409/403/404/501 unchanged.
- **C2 (envelope):** assert a success body is `{success:true, data}` and an error body is
  `{success:false, error, code?, ...}` with the correct status.
- **C3 (frontend):** `handleResponse` throws an `ApiError` carrying `code`/`errors`/`reasons` from a
  mocked 422/409 body; a modal test drives a 422 and asserts inline field error(s) + a LOCALIZED
  toast (via `code`), a 409 asserts the reasons, a network failure asserts the localized fallback.
- **C4 (i18n):** assert `applyApiError` renders `t(code, params)` (not the raw English `error`) for
  a coded error, and that a missing locale key degrades to the English fallback.
- Full SAM suite + affected frontend tests green.

## Rollout

- **Low risk, additive.** The catch-all only changes the *unhandled* path (empty 502 → bodied 500);
  the envelope change adds a `success` key (existing readers unaffected); codes degrade to the
  English fallback where not yet added. No data migration, no infra change.
- **Incremental i18n.** v1.0 wires the mechanism + converts the Members + ZZP-invoice surfaces; other
  surfaces migrate to codes behind the same contract over time (tracked in tasks, not hidden).
- Ships via the normal path (SAM via `deploy-sam-members.yml`, frontend via Pages). The audit of
  other SAM handlers (R2.4) and the broader code migration may be split into follow-up PRs.

## Version & changelog

This guide is the **versioned source of truth** for the contract; `37-shared-building-blocks.md`
only POINTS here (it never restates the version detail). Bump the version here when the wire
contract changes; additive, backward-compatible changes are a minor bump.

### v1.0 — initial standard

The envelope, the fail-loud catch-all, the RFC 9457 error/reason arrays, the machine-code + i18n
localization, and the shared frontend `ApiError` / `applyApiError`. Reference implementation:
Flask (P1) for the ENVELOPE; SAM Members as the conforming full-stack example (deliverable B);
ZZP invoice as the i18n-code reference (`errors.invoice.emailMissing`, replacing the string-sniff).

Contract summary (authoritative):
- **Envelope:** success `{success:true, data}`; error `{success:false, error, code?, params?,
  errors?[], reasons?[]}` — always the real HTTP status; `success` is DERIVED from the status range.
- **`errors[]`** (422): RFC 9457 per-entry array of `{field, code, params?, detail}`.
- **`reasons[]`** (409): array of `{code, params?, detail}` (no `field`).
- **Codes** are keys in the EXISTING `errors` i18n namespace, resolved `t('errors:<path>', params)`;
  **field-level validation codes live under the `errors.validation.*` category** (a v1.0 decision —
  ONE namespace hosts every code; the standalone `validation` namespace groups keys under sub-objects
  where a flat leaf has no home). Per `TRANSLATION_KEY_CONVENTIONS.md` (camelCase leaves).
- **Fallback:** the backend English `error`/`detail` is shown when a `code` has no locale key
  (graceful degradation); a genuine network/non-`ApiError` throw shows `errors.api.serverError`.
- **Fail-loud:** every backend handler ends in a last-resort catch-all → a bodied 5xx
  (`errors.api.serverError`) + a server-side logged traceback; never an empty 502, never a client leak.

Cross-links: `TRANSLATION_KEY_CONVENTIONS.md` (i18n key conventions); the Fail-loud integrity spec
(the catch-all discipline); `37-shared-building-blocks.md` (the registry entry that points here).

### Deferred (tracked, behind the same contract)
- Flask per-field `errors[]` migration (Flask has no per-field structure today — envelope-only for now).
- Full `applyApiError` wiring for ZZP (needs the Flask ZZP service to THROW `ApiError`; today it
  returns response objects — ZZP uses code-first handling for the email-missing case in the interim).
- Migrating every remaining legacy backend message to a code (incremental).
