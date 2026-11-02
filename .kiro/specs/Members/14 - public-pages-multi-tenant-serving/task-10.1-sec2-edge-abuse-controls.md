# Task 10.1 — SEC-2 (edge abuse controls): throttle + "equivalent challenge" reconciliation

> **CONFIRM + RECONCILE + RECORD** (R10.2, R10.6; part of the GATED Task 10 edge hardening,
> pairs with Task 9's live public API). The per-source-ish rate limit / throttle and the
> submit-time challenge that SEC-2 demands are **already built**; this note confirms that
> wiring against `sam/members/template.yaml` + `samconfig.toml`, states honestly where the
> stage throttle is NOT literally per-IP, and records that the honeypot + throttle are the
> sanctioned **"equivalent challenge"** (R10.2 wording) with a full WAF rate-based rule /
> CAPTCHA as the documented deferred add-on (D17). No deploy, no live AWS call, no Flask
> landing-module change — inspection + two focused tests only. Matches the spec-folder
> decision-record convention (`task-1.1-slug-marker-decision.md`,
> `task-7.3-hosting-backlog-reconciliation.md`, `task-9.3-sec7-framing-defaults-closed.md`).

## Confirmation 1 — per-source rate limit / throttle on the public GET/POST routes — **CONFIRMED by inspection + test**

Evidence: `sam/members/template.yaml`, the `MembersPublicApi` (`AWS::Serverless::Api`) —
the plane's only unauthenticated surface (D27) — carries a **stage throttle**:

```yaml
MembersPublicApi:
  Type: AWS::Serverless::Api
  Properties:
    StageName: !Ref Stage
    MethodSettings:
      - HttpMethod: "*"           # every method …
        ResourcePath: "/*"        # … on every path → BOTH public routes (GET + POST {slug})
        ThrottlingRateLimit:  !Ref PublicApiThrottleRateLimit
        ThrottlingBurstLimit: !Ref PublicApiThrottleBurstLimit
```

plus a managed, inspectable **usage plan** bound to that same stage, carrying the SAME
rate/burst, bound to the PUBLIC api only (never the token-gated `MembersApi`):

```yaml
MembersPublicApiUsagePlan:
  Type: AWS::ApiGateway::UsagePlan
  DependsOn: MembersPublicApiStage
  Properties:
    ApiStages:
      - ApiId: !Ref MembersPublicApi     # the public API, NOT MembersApi
        Stage:  !Ref Stage
    Throttle:
      RateLimit:  !Ref PublicApiThrottleRateLimit
      BurstLimit: !Ref PublicApiThrottleBurstLimit
```

- **Both public routes covered.** The wildcard `HttpMethod: "*"` / `ResourcePath: "/*"`
  applies the cap to every method on every path of the public stage — so `GET {slug}` AND
  `POST {slug}` are both throttled.
- **Fail-safe low defaults.** `PublicApiThrottleRateLimit` default `10`/s (min 1, max 10000),
  `PublicApiThrottleBurstLimit` default `20` — a bare deploy is BOUNDED, never unlimited.
- **Per-env, re-tunable without code** (`samconfig.toml`, steering 36/43): **TEST runs tighter**
  (`PublicApiThrottleRateLimit=5`, `PublicApiThrottleBurstLimit=10`, sharing the account's API
  Gateway budget) than **PROD** (`=10` / `=20`). TEST ≠ PROD confirms the per-env knob.
- **Usage plan is NOT keyed.** No API key is required on the public routes (an applicant carries
  none), so the plan throttles the STAGE; it is the documented attach point where a per-key quota
  or rate-based rule would later hang.

### HONEST SCOPE — "per-source" vs stage-wide (NOT fully per-IP)

The task text says "per-source". An API Gateway **stage throttle + usage plan is
ACCOUNT/STAGE-WIDE, not strictly per-source-IP** — the rate + burst bucket is shared across
ALL callers of the stage, so one abuser consuming the bucket also throttles legitimate callers
(a coarse bound, not isolation). A **true per-IP rate limit is a WAF rate-based rule**, which
D17 deliberately defers (see below). So "per-source" is **met as a proportionate stand-in, not
literally**: the stage throttle bounds the aggregate flood (the economic-DoS / SEC-6 backstop)
at a member-application form's low, human-paced volume; strict per-IP isolation is the deferred
WAF add-on. This is stated plainly rather than claiming full per-source coverage.

## Confirmation 2 — submit-time "equivalent challenge" on POST {slug} — **CONFIRMED (honeypot), CAPTCHA reconciled as deferred**

Evidence: `sam/members/handler/public_app.py` — the public POST runs pre-write **abuse guards**
(`_guard_abuse`, order: payload cap → malformed body → honeypot) BEFORE any tenant resolution
or write. The honeypot (`HONEYPOT_FIELD = "website"`, a visually hidden field a real browser
leaves empty; a naive spam bot that fills every input trips it) rejects a bot with a **neutral
400** (`errors.api.badRequest`) that is byte-identical to the malformed/oversized rejection, so
the trap is not discoverable. A tripped honeypot is rejected at the edge even for an
allow-listed slug — a flood never reaches the resolver/service.

## Reconciliation — CAPTCHA requirement vs D17 — **NO HARD CONFLICT; "equivalent challenge" is satisfied**

The hinge is the **exact requirement wording**. R10.2 (SEC-2) requires, before the write and
before going live:

> "a per-source rate limit / throttle; **a CAPTCHA or equivalent challenge**; a payload SIZE CAP;
> and PER-FIELD type / allowed-value validation …"  — requirements.md R10.2

and the design SEC-2 bullet mirrors it: "(b) **a CAPTCHA or equivalent challenge** on the submit".
**Neither text mandates a CAPTCHA specifically** — both admit an *equivalent challenge*. So a
CAPTCHA is **NOT a hard, un-deferrable acceptance criterion**; it is one of two accepted ways to
satisfy the obligation. There is therefore **no conflict to escalate to a human** — the design
and requirement were written to accommodate exactly this choice.

> **Note on "D17".** design.md has no literal `D17` labelled section or standalone WAF-deferral
> paragraph; the operative, testable text is R10.2's "or equivalent challenge" (above) and the
> SEC-2/SEC-6 risk-register rows. The "D17" label is, in practice, carried in the **template +
> test comments** (`template.yaml` lines ~410–446 / ~1402–1446, and
> `test_public_api_hardening_stack_contract.py`), which already internalise the decision:
> *"D17 deliberately provisions NO WAF (rate-based rule / CAPTCHA is the one material recurring
> cost, deferred until real abuse appears)"* and *"the proportionate control at a member-
> application form's low, human-paced volume (R10.4) is API Gateway's native throttle + a usage
> plan."* This note treats D17 as that recorded decision, not as a verbatim design section.

### The sanctioned "equivalent challenge" for v1

**Stage throttle + usage plan (Confirmation 1) + the honeypot bot-trap on POST (Confirmation 2)
= the "equivalent challenge" that satisfies SEC-2's edge half** at this volume. A managed
CAPTCHA / WAF rate-based rule is the **documented deferred add-on** (D17 — "the one material
recurring cost, deferred until real abuse appears"), whose attach point already exists: the
usage-plan / stage is where a per-key quota or rate-based rule hangs when abuse appears. The
server-side payload cap + per-field validation half of SEC-2 is Task 4.2 (separate, done).

## Verification (focused, no deploy, no live AWS)

- `python -m pytest -c sam/pytest.ini sam/tests/test_public_api_hardening_stack_contract.py -q`
  → **13 passed**. Asserts: wildcard stage throttle bound to the per-env params; a usage plan
  bound to the PUBLIC api's stage only (never `MembersApi`) with the same rate/burst; fail-safe
  low defaults; samconfig supplies a concrete rate+burst per env; and **NO WAF** provisioned
  (`AWS::WAFv2::WebACL`/association absent) per D17/R10.4.
- `python -m pytest -c sam/pytest.ini sam/tests/test_public_app_edge.py -q -k "honeypot or abuse_guard"`
  → **5 passed**. Asserts: a populated honeypot (nested + top-level) → neutral 400; a blank
  honeypot falls through to a 200; the rejection body does not reveal which guard tripped; the
  guard runs BEFORE slug resolution.

## Outcome

Task 10.1's SEC-2 edge controls are **in place and confirmed**, with the per-source caveat stated
honestly (stage-wide throttle as the proportionate stand-in; true per-IP = the deferred WAF rule).
The "CAPTCHA or equivalent challenge" obligation is **satisfied by the honeypot + throttle**, with
a full CAPTCHA / WAF rate-based rule deferred per D17 until real abuse appears — **no hard conflict
requiring a human decision**. Nothing was deployed; no live AWS call; no third-party CAPTCHA
integration built; the Flask landing module untouched.
