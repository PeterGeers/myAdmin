# Task 10.3 — paired tests / verification battery (completes Task 10)

> **CONFIRM + MAP + thin-consolidate + RECORD** (R10.2, R10.6; the GATED Task 10 edge
> hardening, pairs with Task 9's live public API). The three 10.3 verification items —
> (1) throttle trips at the configured rate, (2) a challenge is required on submit, (3) a
> burst of unknown-slug GETs is rate-limited, not amplified — are **already covered** across
> the 10.1 stack-contract tests, the 10.2 no-scan tests, and the honeypot edge tests. This
> note maps each item to the test(s) that prove it, states which half is a **live/edge
> assertion deferred to the 9.4 runbook** (not a unit test), records the ONE thin
> consolidating assertion added, and the pass count. No deploy, no live AWS call, no Flask
> landing-module change. Companion to `task-10.1-sec2-edge-abuse-controls.md` and
> `task-10.2-sec6-dos-bounded.md`; matches the spec-folder decision-record convention.

## The battery was ALREADY complete — this task MAPS it and adds one consolidating assertion

No item required new infrastructure or new behaviour. 10.1 built the throttle + usage plan,
10.2 proved O(1) scan-free resolution on both routes, and the honeypot has been the
submit-time challenge since task 1.1 / 4.x. 10.3 is the verification battery that confirms
the three items are each proven and coherent — it does **not** duplicate those proofs. One
genuinely-missing assertion was added (item 3's consolidated "unknown-slug burst = one keyed
lookup each, never amplified"); everything else is mapped to a pre-existing test.

## Item 1 — "throttle trips at the configured rate" — **a STACK CONTRACT (unit) + a live-edge assertion (9.4)**

An API Gateway **stage throttle is enforced by AWS at the edge, NOT by application code** — the
handler never sees the throttle (AWS returns 429 before Lambda is invoked), so sending N requests
to the handler can never exercise it. The honest, unit-testable assertion is the **stack
contract**: the configured rate/burst params are declared on the public stage (both routes) plus a
usage plan bound to that stage. The live **429-on-exceed** is an edge behaviour, verified in the
live e2e **(task 9.4 runbook)**, not a unit test.

Proven by `sam/tests/test_public_api_hardening_stack_contract.py` (pre-existing, 10.1):

| Assertion | Test |
| --- | --- |
| Wildcard `*`/`/*` stage `MethodSettings` carries `ThrottlingRateLimit`/`ThrottlingBurstLimit` bound to the `PublicApiThrottleRateLimit`/`PublicApiThrottleBurstLimit` params → **both** `GET` + `POST {slug}` routes | `test_public_api_has_a_stage_throttle_bound_to_params` |
| A usage plan bound to the **public** API's stage (never `MembersApi`) carrying the **same** rate/burst params | `test_usage_plan_exists_and_is_bound_to_the_public_api_stage`, `test_usage_plan_is_not_bound_to_the_authenticated_api` |
| Fail-safe low defaults (bounded, not unlimited) | `test_throttle_params_have_fail_safe_low_defaults` |
| samconfig supplies a concrete rate+burst per env (TEST tighter than PROD) | `test_samconfig_supplies_throttle_per_env` |

So "the configured rate/burst IS declared on the stage, bound to both routes, with a usage plan" —
the rate the edge enforces — is fully pinned. **No new assertion needed.** The live 429-on-exceed
is recorded as the 9.4 deferral.

## Item 2 — "a challenge is required on submit" — **UNIT-tested (honeypot = the equivalent challenge)**

Per 10.1, the honeypot is the sanctioned "CAPTCHA **or equivalent challenge**" (R10.2 wording); a
full CAPTCHA/WAF is the D17 deferred add-on. The honeypot gate runs on the **POST submit path,
before any resolution or write**. Proven by pre-existing tests in
`sam/tests/test_public_app_edge.py`:

| Assertion | Test |
| --- | --- |
| A bot-filled honeypot on POST → neutral 400 (nested field) | `test_honeypot_populated_returns_neutral_400` |
| A bot-filled honeypot on POST → neutral 400 (top-level field) | `test_honeypot_at_top_level_also_trips` |
| A blank honeypot (real human) PASSES → 200 (challenge does not block legitimate submits) | `test_blank_honeypot_is_not_a_trip` |
| The challenge gate is on the POST submit path **before** slug resolution/write | `test_abuse_guard_runs_before_slug_resolution` |
| The rejection body does not reveal which guard tripped (trap not discoverable) | `test_abuse_guard_message_does_not_reveal_which_control_tripped` |

Explicitly covers "a challenge is required on submit" (tripped → rejected) AND "it does not block a
real human" (blank → 200), with the gate proven to run before resolution. **No new assertion
needed.**

## Item 3 — "a burst of unknown-slug GETs is rate-limited, not amplified" — **two halves; ONE thin consolidating assertion added**

Two halves:

- **"rate-limited"** = the stage throttle (item 1, stack contract) — the live 429 is the 9.4
  edge assertion.
- **"not amplified"** = the O(1) scan-free resolution (10.2) — an unknown-slug GET costs one
  keyed `get_object` miss → the non-probeable 404, never a `.scan()` fan-out.

Pre-existing proofs:

| Assertion | Test |
| --- | --- |
| GET read resolves by a keyed `get_object`, never `.scan()` (known slug, 200) | `test_get_read_resolution_is_a_keyed_get_object_never_a_scan` (10.2) |
| POST submit resolves by a keyed `get_object`, never `.scan()` | `test_post_submit_resolution_is_a_keyed_get_object_never_a_scan` (10.2) |
| An unknown slug → the non-probeable 404 | `test_unknown_slug_returns_non_probeable_404`, `test_empty_slug_map_makes_every_slug_non_probeable_404` |

**The thin gap:** the no-scan test used a *known* slug (returns 200); the unknown-slug 404 tests did
not assert the no-scan path. No single test asserted the exact verification wording — *a burst of
**unknown** slugs each resolves by **one keyed lookup**, returns the **non-probeable 404**, and
**never a scan*** (the "miss path" of a random-slug flood). Added ONE consolidating test (not a
duplicate — it combines the unknown-slug 404 with a scan-forbidding, resolve-counting store):

- `test_unknown_slug_get_burst_resolves_by_one_keyed_lookup_and_is_not_amplified`
  — fires a 5-slug burst of unknown slugs against a store that FAILS LOUD on `.scan()` and COUNTS
  `resolve` calls; asserts every request is the non-probeable 404 AND exactly N keyed lookups for N
  requests (linear, O(1) each, zero scans). This is the application-level "not amplified" proof the
  item names; the "rate-limited" half remains the stage throttle (item 1) with the live 429 deferred
  to 9.4.

## What is a live/edge assertion vs a unit test

| Verification | Unit test (this battery) | Live/edge (deferred to 9.4 runbook) |
| --- | --- | --- |
| Throttle **declared** at the configured rate/burst on both routes + usage plan | ✅ stack contract | — |
| Throttle **actually returns 429 on exceed** | — (AWS enforces before Lambda) | ✅ live 429-on-exceed |
| Challenge required on submit (honeypot trip → reject; blank → pass) | ✅ edge tests | — |
| Unknown-slug GET = one keyed lookup, non-probeable 404, never a scan (not amplified) | ✅ consolidating test | — |
| Unknown-slug flood **rate-bounded in production** | — | ✅ 429 under the stage throttle |

## Verification (focused, no deploy, no live AWS)

```
python -m pytest -c sam/pytest.ini \
  sam/tests/test_public_app_edge.py \
  sam/tests/test_public_api_hardening_stack_contract.py -q
→ 83 passed in 0.35s
```

(The single added test on its own:
`sam/tests/test_public_app_edge.py::test_unknown_slug_get_burst_resolves_by_one_keyed_lookup_and_is_not_amplified`
→ 1 passed.)

## Outcome

Task 10.3's verification battery is **complete and coherent** across the 10.1 stack-contract tests
(item 1 — throttle declared at the configured rate/burst on both routes + usage plan; the live 429
is the 9.4 edge assertion), the honeypot edge tests (item 2 — challenge required on submit, real
human passes), and the 10.2 no-scan tests plus **one added consolidating assertion** (item 3 — an
unknown-slug burst costs one keyed lookup each, returns the non-probeable 404, never a scan → not
amplified; the rate-limited half is the stage throttle). Nothing was duplicated; nothing was
deployed; no live AWS call; the Flask landing module untouched. **This completes Task 10 and all
account-agnostic (PARALLEL-track) work** — the only remaining Task-10 dependency, the live
429-on-exceed, is an edge behaviour in the GATED task 9.4 runbook.
