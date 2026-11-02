# Task 10.2 — SEC-6 (DoS-bounded): throttle-fronts-the-rate + O(1) scan-free resolution

> **CONFIRM + RECONCILE + RECORD** (R10.2, R10.6; part of the GATED Task 10 edge hardening,
> pairs with Task 9's live public API). SEC-6's two halves — an edge control that bounds the
> request rate, and an O(1) keyed slug resolution that removes the DynamoDB cost-amplifier —
> are **already built** (the throttle in Task 10.1, the scan-free resolver in Tasks 3/4).
> This note confirms both by inspection + focused tests, reconciles "WAF / throttling"
> against the D17 WAF deferral, and records the finding. No deploy, no live AWS call, no
> Flask landing-module change. Companion to `task-10.1-sec2-edge-abuse-controls.md` and
> matches the spec-folder decision-record convention (`task-1.1-…`, `task-7.3-…`,
> `task-9.3-sec7-…`).

## The exact acceptance text (the hinge for the WAF reconciliation)

requirements.md **R10.6 (SEC-6)**:

> "The public `GET/POST {slug}` functions SHALL sit behind edge **throttling / WAF**, and slug
> resolution SHALL be **O(1) keyed lookup (never a scan, R5.3)**, so flood traffic cannot amplify
> cost or exhaust the datastore."

design.md **SEC-6** (risk-register severity 🟡, the lowest): "the public `GET/POST {slug}`
functions sit behind edge **throttling / WAF**; … **No-scan resolution (Property 4) removes the
DynamoDB cost-amplifier**; throttling bounds the Lambda/marker-lookup load from `GET {random-slug}`
floods." The mitigation cell reads "Edge throttling / WAF … no-scan resolution removes the
DynamoDB cost-amplifier".

**The `/` in "throttling / WAF" is disjunctive** — either control satisfies the edge arm. Neither
text mandates a WAF specifically (parallel to R10.2's "a CAPTCHA **or equivalent challenge**"
reconciled in Task 10.1). So a WAF is **NOT a hard, un-deferrable acceptance criterion**.

## Confirmation 1 — FRONTING: the public API is rate/burst-bounded at the edge — **CONFIRMED (via Task 10.1)**

The `MembersPublicApi` stage carries a wildcard `MethodSettings` throttle
(`ThrottlingRateLimit`/`ThrottlingBurstLimit` on `HttpMethod: "*"` / `ResourcePath: "/*"`) plus a
`MembersPublicApiUsagePlan` bound to the public stage with the same rate/burst — covering BOTH
public routes (`GET` + `POST {slug}`), with fail-safe low defaults, re-tunable per env in
`samconfig.toml`. Full template evidence is quoted in `task-10.1-sec2-edge-abuse-controls.md`
(Confirmation 1) and pinned by `test_public_api_hardening_stack_contract.py` (13 passed).

**HONEST SCOPE (same caveat as 10.1):** this is a **stage-wide** API Gateway throttle, not a
per-IP WAF rate-based rule. A flood is therefore **RATE-BOUNDED** (it cannot exceed the stage
rate/burst, which is the economic-DoS backstop SEC-6 asks for) but a single source is **not
individually isolated** — one abuser consuming the shared bucket also throttles legitimate
callers. True per-IP isolation is the deferred WAF add-on (D17). At a member-application form's
low, human-paced volume (R10.4) the stage throttle is the proportionate control.

## Confirmation 2 — O(1) SCAN-FREE RESOLUTION (the real DoS-amplification guard, R10.6 / Property 4) — **CONFIRMED on BOTH public routes**

Both public routes resolve the slug through the SAME single O(1) keyed `get_object` on
`_slugs/{slug}` — `S3SlugMarkerStore.resolve` via `_resolve_sam_form_tenant(slug)` in
`sam/members/handler/public_app.py` — **never a `.scan()`** (the h-dcn Events table-scan
anti-pattern the design explicitly rejects, C2):

- **GET `…/field-config`** (Task 3.1): `_dispatch_public` `if request.method == "GET":` →
  `tenant_id = _resolve_sam_form_tenant(slug)` (public_app.py ~line 738).
- **POST `…/applications`** (Task 4.1): the submit path →
  `tenant_id = _resolve_sam_form_tenant(slug)` (public_app.py ~line 790) — the module docstring
  is explicit it is "the SAME `_slugs/{slug}` marker BODY the GET read uses … a scan-free O(1)
  `get_object` … NEVER a value from the request body and NEVER a second resolution mechanism".

So a `GET {random-slug}` **or** `POST {random-slug}` flood costs **one keyed lookup each** (which
misses → the non-probeable 404); it **cannot** amplify into a table scan or exhaust the datastore.
This no-scan resolution is the real cost-amplifier removal R10.6 demands; the throttle
(Confirmation 1) bounds the per-request Lambda/marker-lookup rate on top of it.

### The no-scan tests (the proof the flood can't amplify)

`sam/tests/test_public_app_edge.py` — each uses a `_ScanIsForbidden` fake store whose `.scan()`
raises `AssertionError`, so the route still returning 200 proves it resolved by keyed
`get_object`, never a scan:

- `test_get_read_resolution_is_a_keyed_get_object_never_a_scan` — GET route (pre-existing, Task 3).
- `test_post_submit_resolution_is_a_keyed_get_object_never_a_scan` — **POST route (added here,
  Task 10.2)** — closes the gap so BOTH public routes are proven scan-free.

```
python -m pytest -c sam/pytest.ini sam/tests/test_public_app_edge.py -k "never_a_scan"
→ 2 passed, 65 deselected in 0.17s
```

## Reconciliation — WAF vs D17 — **SATISFIED; NO HARD CONFLICT**

R10.6 / design SEC-6 both say "throttling **/** WAF" (disjunctive) and rate SEC-6 the lowest
severity (🟡). The **stage throttle (Confirmation 1) + the O(1) scan-free resolution
(Confirmation 2) together satisfy "DoS-bounded"** at this volume:

- the throttle bounds the request **rate** at the edge (economic-DoS backstop), and
- the keyed resolution removes the datastore **cost-amplifier** (no scan to fan out into).

A WAF (per-IP rate-based rule / managed CAPTCHA) is the **documented deferred add-on per D17**
("the one material recurring cost, deferred until real abuse appears"), whose attach point
already exists (the usage-plan / stage). This is consistent with Task 10.1's SEC-2 reconciliation.
Re-reading R10.6 carefully: it does **not** mandate a WAF as a hard gate — the `/` admits throttle
alone — so there is **no conflict requiring a human decision**, and no WAF was built.

## Outcome

Task 10.2's SEC-6 is **confirmed DoS-bounded**: the stage throttle fronts the request rate on both
public routes (stage-wide, not per-IP — stated honestly), and slug resolution is a single O(1)
keyed `get_object` with **NO scan on EITHER route**, so a random-slug flood cannot amplify cost or
exhaust the datastore. A POST no-scan test was added to prove the submit route matches the read
route; both no-scan tests pass (2 passed, 0.17s). WAF remains the deferred add-on per D17 — no hard
conflict. Nothing was deployed; no live AWS call; the Flask landing module untouched.
