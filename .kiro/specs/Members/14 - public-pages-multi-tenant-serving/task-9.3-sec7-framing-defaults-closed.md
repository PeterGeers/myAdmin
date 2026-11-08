# Task 9.3 — SEC-7: framing defaults closed + embed origins input-validated on write

> **VERIFICATION + ONE GAP CLOSED** (R3.1, R5.1, R5.4, R5.5, R6.2, R6.3, R10.7, R10.8; part of the
> GATED Task 9). Confirms the deny-by-default framing mechanism already built in
> `infrastructure/application-form.tf`, and CLOSES a genuine write-path validation gap so a
> tenant-authored embed origin cannot weaken the CloudFront CSP `frame-ancestors` directive. No
> Terraform applied, no live AWS call, no Flask landing-module change — inspection + the paired
> unit test only. Matches the spec-folder decision-record convention
> (`task-1.1-slug-marker-decision.md`, `task-7.2-adr-consistency-review.md`,
> `task-7.3-hosting-backlog-reconciliation.md`).

## Confirmation 1 — framing DEFAULTS CLOSED (`'none'` when no entry) — **CONFIRMED by inspection**

Evidence: `infrastructure/application-form.tf`, the `aws_cloudfront_function
.application_form_frame_ancestors` viewer-response function (`cloudfront-js-2.0`) + its header
comment. Three independent fail-closed paths, each returning the response with **no**
`content-security-policy` header set (browser default = top-level only, i.e. equivalent to
`frame-ancestors 'none'` — NOT embeddable):

1. **KVS binding unavailable** — the `cf.kvs(kvsId)` call is wrapped in `try/catch`; the catch
   comment states *"KVS not available — fail closed (no frame-ancestors header set)."* and the
   handler then hits `if (!kvs || !host) { ... return response; }` → no header.
2. **Host has no KVS entry** — `kvs.get(host)` is wrapped in `try/catch`; on a not-found / lookup
   error the comment *"Key not found or lookup failed -> standalone, no header."* returns the
   response unchanged → no header.
3. **Entry present but empty** — after `split(/\s+/).filter(len>0)`, `if (list.length === 0) { ...
   return response; }` → *"No configured origins -> standalone, omit the header (not embeddable)."*

The header is emitted ONLY on the explicit-allow path (`list.length > 0` →
`'frame-ancestors ' + list.join(' ')`). A missing/unavailable/empty entry can never fall open to
allow-all. The `.tf` header comment states the invariant outright: *"Standalone (no origins
configured) => NO frame-ancestors header is emitted ... equivalently `frame-ancestors 'none'`."*
This matches design §10 / R6.3 and the SEC-7 row in the design security matrix.

## Confirmation 2 — tenant-authored embed origins INPUT-VALIDATED on write — **GAP FOUND + CLOSED**

Write path: a tenant authors `application_embed_origins` onto `config#mail` via
`PUT /members/config/mail` → `ConfigWriteService._validate_mail_body` →
`ConfigWriteService._shape_embed_origins` (`sam/members/domain/config_write_service.py`).

**Gap (genuine):** the prior `_shape_embed_origins` accepted ANY non-blank string. Because the edge
function builds the directive by raw concatenation (`'frame-ancestors ' + list.join(' ')`), a
tenant-authored entry of `*` would have opened framing to **everyone** (defeating deny-by-default),
and an entry containing whitespace, `;`, `'` or `"` could have injected an extra `frame-ancestors`
token or a second CSP directive at the edge. Design §2.3 (SEC-7) and the security matrix explicitly
require embed origins be *"INPUT-VALIDATED (well-formed origin, no `*` wildcard-all, no injection)
before it is written to the KVS"* — the code did not meet that. This is a stated SEC-7 property, so
the gap was closed at the WRITE layer (the single authoring guard both enforcers read back).

**Fix (`_shape_embed_origins`, write layer only):** every entry must now match
`_EMBED_ORIGIN_RE` = a bare `https://host[:port]` serialized origin —

- **no `*`** (wildcard-all / wildcard host / wildcard subdomain rejected);
- **https-only** (`http://` rejected — the form is HTTPS-only);
- **no path / query / fragment** (nothing after the authority);
- **no whitespace or CSP-delimiter characters** (space, `;`, `'`, `"`) → no directive/token
  injection;
- **bounded**: `_EMBED_ORIGINS_MAX_COUNT = 50` entries, `_EMBED_ORIGIN_MAX_LEN = 255` chars/entry.

A violation raises the caller-safe `ConfigWriteValidationError` (→ HTTP 400) fail-loud; nothing is
persisted — a malformed/dangerous config surfaces as a 400 instead of silently weakening
`frame-ancestors`. The existing non-list / non-string / blank-entry rejections and the trim +
first-seen de-dupe are retained. The two CONFIRMED v1 targets (`https://sites.google.com`,
`https://portal.h-dcn.nl`) and the live examples (`https://aanmelden.jabaki.nl`,
`https://members.h-dcn.nl`) all remain valid under the stricter rule.

**Paired test (same change, steering 30/34):** `sam/tests/test_config_write_service.py`

- `test_put_config_mail_embed_origins_rejects_wildcard_and_injection_sec7` — proves `*`,
  `https://*`, `https://*.evil.example`, `http://…`, a path/query/fragment, an embedded space, a
  `; script-src 'none'` directive injection, quote injection, a scheme-less value, an over-long
  entry, and a 51-entry list are each rejected and NOTHING is persisted.
- `test_put_config_mail_embed_origins_accepts_well_formed_https_with_port` — a well-formed
  `https://host[:port]` origin still passes and is stored.
- The pre-existing `…_malformed_raises_validation_error` / `…_shaped_when_well_formed` /
  `…_accepts_confirmed_v1_targets` / `…_absent_or_empty_writes_nothing…` tests still pass.

## Confirmation 3 — ONE list, TWO enforcement points, cannot drift — **CONFIRMED by inspection**

The single tenant-authored `application_embed_origins` attribute on `config#mail` feeds BOTH
enforcers, each reading the SAME shaped list so they cannot diverge:

- **CloudFront `frame-ancestors`** (edge): populated into the
  `aws_cloudfront_key_value_store.application_embed_origins` KVS from the same attribute (task 5.2).
- **SAM public-API CORS `Access-Control-Allow-Origin`**: `sam/members/handler/public_app.py`
  `_tenant_embed_origins` → `MembersProjectionReader.get_application_embed_origins`
  (`sam/members/repository/_mail_config_reader.py`), which reads the SAME `config#mail` attribute
  (task 5.3). Its docstring states it feeds *"TWO distinct enforcement points that MUST read the
  SAME list so they cannot drift."* The reader re-trims + re-de-dupes as belt-and-suspenders but
  reads no second source.

One write shaper (`_shape_embed_origins`), one stored attribute, two read-only consumers — a
tenant's embed allow-list cannot diverge between framing and CORS.

## Disposition — where recorded

This file IS the recorded SEC-7 confirmation. `application-form.tf` already carried the fail-closed
mechanism (confirmed, unchanged — no Terraform applied). The only code change is the write-layer
input-validation hardening in `_shape_embed_origins` + its paired test. Verified:
`python -m pytest -c sam/pytest.ini sam/tests/test_config_write_service.py -q` → **107 passed**
(embed-origins subset: 6 passed).

## Verdict — **PASS** (framing defaults closed; embed origins input-validated; one list, two enforcers)
