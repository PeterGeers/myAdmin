# ADR 0008 — Public unauthenticated intake on the SAM module edge: one fenced, token-less application-form path (companion to ADR 0007)

- Status: Accepted
- Date: 2026-10-13
- Relates to: ADR 0007 (active-tenant resolution at the SAM edge — the "deny without a
  verified token" invariant this ADR carves a single exception to), ADR 0004 (verified-JWT-only),
  ADR 0006 (resolved entitlement in the token via PreTokenGen). Introduced by the Member
  Application Form feature. Spec: `.kiro/specs/Members/application-app/`
  (`requirements.md` R13.2, `design.md` §1/§2/§13, decision D27).

## Context

ADR 0007 fixed active-tenant resolution at the SAM Members edge and, with ADR 0004, locked in
the module-plane invariant: **every request to a SAM module API is denied unless it carries a
cryptographically verified Cognito JWT.** Auth runs at the edge (`sam/members/handler/app.py`,
`_authenticate_and_authorize`) before any dispatch; the members API is a single
`AWS::Serverless::Api` with `Auth.DefaultAuthorizer: CognitoAuthorizer`, and `RouteSpec` has no
per-route auth-skip field. There has never been a token-less path on the module plane.

The Member Application Form feature needs exactly that. A prospective member filling in a public
application form **has no account and no token** — the whole point of the form is that they are
not yet a member. The form must load and accept a submission from an anonymous browser. This is
the module plane's first unauthenticated HTTP surface, and it sits in direct tension with the
ADR 0007 invariant.

The requirement is narrow: a single public intake path (load the tenant's field config, submit
one application) that writes a `status=application` record and offloads a best-effort
notification. It is not a general relaxation of edge auth, and it must not become one.

## Decision

**Open a SINGLE, fenced, token-less edge for public member-application intake — and fence it so
tightly that the absence of a verified token is compensated for by other controls rather than
left as a hole.** ADR 0007's deny-by-default remains the rule for every other module route;
this is the one documented exception.

Structure of the exception (decided as D27):

- **A separate public API, not a carve-out on the authenticated one.** The public endpoints live
  on their OWN `AWS::Serverless::Api` with **NO `DefaultAuthorizer`** — its own stage, own invoke
  URL, own throttle/usage plan — routed to a **dedicated public Lambda entrypoint**
  (`handler/public_app.py`) that **never calls `_authenticate_and_authorize`**. The authenticated
  members API and its `handler()` are untouched. This gives the cleanest blast-radius isolation:
  the unauthenticated surface cannot reach, weaken, or share routing with the authenticated one.
  (The rejected alternative was an `Auth: {Authorizer: NONE}` route on the existing API, which
  would have put a token-less path inside the authenticated app's handler.)
- **Token-less entrypoint, only two routes.** `GET /public/members/{slug}/field-config` (readiness
  gate + filtered schema) and `POST /public/members/{slug}/applications` (submit). Nothing else is
  public.
- **Tenant comes from a slug allow-list — verify-before-trust, not grant.** With no token there is
  no verified `tenant_keys` to select from, so the tenant carrier is the tenant's existing
  landing-page slug (`<slug>.jabaki.nl`; custom domains via the CloudFront KVS
  `myadmin-domain-slug-mapping`), resolved to `tenant_id` through a thin SAM-plane projection of
  that mapping (D19). The slug **selects** a tenant from an allow-list; it never grants one. An
  unknown or forged slug returns a non-probeable **404** — indistinguishable from no endpoint.
  This mirrors ADR 0007's "select, never grant" discipline, with the verified allow-list standing
  in for the verified `tenant_keys`.

Because the auth gate is deliberately absent, a set of **compensating controls** stands in for it.
These are not optional hardening — they ARE the fence, and the exception is only acceptable with
all of them in place:

- **Honeypot field** — a decoy field; a filled value trips a neutral 400 (bot signal).
- **Payload cap** — oversized bodies rejected at the handler before any work (400).
- **Fail-closed CORS** — responses carry CORS headers only for the configured form origin(s);
  a disallowed origin is not served. CORS restriction is enforced on both success and error paths.
- **API Gateway throttle + usage plan** on the public stage — bounds request volume at the edge
  (no WAF now — D17/R10.4 record it as an easy add-on IF real abuse appears).
- **Least-privilege IAM for the public function** — scoped to exact ARNs: members-table write,
  governance-projection read, mail-send queue enqueue. No wildcards, no cross-account grants.
- **Readiness gate** — the form only opens (and a submit only lands) for a tenant whose mail is
  send-ready (`config#mail` `mail_certified` + `mail_domain`); otherwise a neutral 409 with a
  stable code and NO record written. Submit re-checks the gate (defense-in-depth): a non-ready
  tenant can never produce an un-notifiable accepted application.

Downstream of the edge, nothing is special-cased: `create_application` reuses the authenticated
`create_member` spine, forces `status=application`, strips client-supplied privileged fields
(`status` / `tenant_id` / `member_id` are server-authoritative), and the repository remains the
sole DynamoDB touch-point with `tenant_id` as the partition key. The **record is authoritative;
email is best-effort** — the application is persisted first, and the staff + applicant
notifications are offloaded to the existing mail-send queue/worker. A failed send never rolls
back the record; the `status=application` inbox is the authoritative review channel, not the
email.

## Rationale

- **The invariant is fenced, not weakened.** ADR 0007/0004's deny-by-default still governs every
  authenticated module route unchanged. The exception is one isolated API with two routes; it
  cannot be reached from, and does not alter, the authenticated handler.
- **Verify-before-trust is preserved in spirit.** With no token to verify, the verified
  slug→tenant allow-list plays the role `tenant_keys` plays in ADR 0007: the request can only ever
  resolve to a tenant that is explicitly allow-listed, and a forged carrier is denied (as a
  non-probeable 404). The edge still trusts only what it can verify against a server-side list.
- **Compensating controls replace the gate deliberately.** Each control addresses a threat the
  auth gate would otherwise have covered (abuse volume, spoofed origins, oversized payloads, bot
  spam, over-broad permissions, silently un-notifiable submissions). Together they make the
  token-less edge a bounded, observable surface rather than an open door.
- **Blast-radius isolation over convenience.** A separate API is slightly more template wiring
  than an unauthenticated route on the existing API, but it guarantees the unauthenticated code
  path and the authenticated one never share a handler, authorizer, or stage — the safer default
  for the plane's first anonymous surface.
- **Record-authoritative, email-best-effort** keeps the applicant's request path fast and
  resilient: persistence is synchronous and transactional-enough (session-keyed conditional
  write), while notification — the part that depends on SES and recipient resolution — is
  offloaded and cannot fail the submission.

## Consequences

- **The exception is fenced to this one intake path.** Exactly one public API, one dedicated
  entrypoint, two routes. It does **not** relax ADR 0007 for any other module route — the
  authenticated members API, and every future module API, keep deny-by-default with a verified JWT.
- **Future public edges must earn their own fence.** Any later unauthenticated surface
  (another module's public form, a public webhook, etc.) MUST follow the public-intake pattern now
  recorded in `35-sam-module-architecture-sam.md` (separate no-authorizer API + allow-list
  resolver + the compensating-control set) AND get its own ADR entry. A new public edge is never
  added by flipping an authorizer off in place.
- **A standing abuse-hardening follow-up.** No WAF is provisioned now (D17/R10.4); if real abuse
  appears, a rate-based rule / CAPTCHA attaches at this public edge. The throttle + usage plan are
  the interim bound.
- **Operational posture is explicit.** Because the record is authoritative and email is
  best-effort, staff review happens off the `status=application` inbox, not the inbox email; a
  `NO_NOTIFY` / `DUP` note on the record surfaces the degraded cases without blocking intake.
- **Deployed via the codified pipeline.** The public API, its stage/throttle/usage plan, the
  duplicate-flag GSI, the second queue consumer, and the public-function IAM ship through
  `sam/members/template.yaml` + `samconfig.toml` via `deploy-sam-members.yml`
  (`NonprofitDeployRole`, OIDC) — never a hand-typed deploy (steering 35/43).
- **Governance definition-of-done.** Per steering 40 / 00-index, this feature was not done until
  both this ADR and the steering extension landed in the same change set as the code.

## Related

- **ADR 0007** (`0007-active-tenant-resolution-sam-edge.md`) — the "deny without a verified token"
  module-edge invariant this ADR carves a single, fenced exception to; its "select, never grant"
  discipline is mirrored here by the slug allow-list. **ADR 0004** (verified-JWT-only — the
  Property-2 invariant), **ADR 0006** (`custom:entitlements` via PreTokenGen).
- **Steering:** `.kiro/steering/35-sam-module-architecture-sam.md` — extended with the
  public/unauthenticated intake edge pattern + its compensating controls (Member Application Form
  task 10.1); this ADR is the companion decision record for that pattern.
- **Spec:** `.kiro/specs/Members/application-app/` — `requirements.md` R13.2 (this ADR),
  R10/R10.4 (abuse hardening, no WAF now), R5.4/R9.4 (readiness gate); `design.md` §1
  (architecture), §2 (data flow), §13 (security model); decisions D15, D17, D19, D27.
- **Code as built:** `sam/members/handler/public_app.py` (token-less entrypoint),
  `sam/members/domain/tenant_directory.py` (slug→tenant allow-list resolver),
  `sam/members/template.yaml` (separate public `AWS::Serverless::Api`, throttle/usage plan,
  least-privilege public-fn IAM).
