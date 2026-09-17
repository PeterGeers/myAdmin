# ADR 0006 — Resolved entitlement projected into the token via a Pre-Token-Generation Lambda that reads the DynamoDB projection

- Status: Accepted
- Date: 2026-09-16
- Relates to: ADR 0003 (platform base; SAM-backed modules), ADR 0004 (verified-JWT-only;
  per-issuer JWKS), ADR 0005 (two-pool identity; MySQL system-of-record; one-directional
  MySQL→DynamoDB projection). S4 builds on all three: it fills the *per-user* half of the
  S1 "Data ownership" seam (S3 filled the tenant-level half).

## Context

A SAM-backed module's Lambda must answer "what may this user do in this tenant?" on the
request path **without** querying MySQL (the S1 contract; a Lambda cannot afford a
request-time MySQL hop, and the Flask plane's `role_cache.py` cannot serve the Lambda
plane). S4's job is to make that answer travel in the verified token.

Two design questions had to be settled during S4:

1. **Where does the resolved entitlement come from at token issuance?** The obvious
   reading of the original design had a Cognito Pre-Token-Generation Lambda read MySQL
   directly. But MySQL is on **Railway**; a Lambda in AWS reaching it means the Railway
   public TCP proxy, on every cold start, inside Cognito's ~5-second trigger budget —
   an operational risk that also bends the S1 "a module Lambda never opens a MySQL
   connection" rule.

2. **Is S4 a production deployment step, or a capability?** Attaching a live trigger to
   production Pool A in isolation adds risk without a consumer. The first real consumer is
   the h-dcn app migration (S5).

## Decision

**Project each user's resolved per-tenant entitlement into the Pool A token at issuance
via a Cognito V2 Pre-Token-Generation Lambda that reads the S3 DynamoDB projection (not
MySQL); ship it as a vendored toolkit modules adopt, and defer wiring the live production
trigger to the first app migration.**

- **The claim.** A compact, versioned `custom:entitlements` claim carrying
  `{tenant → [capabilities]}`, stamped **additively** into both the ID and access token
  generations — `cognito:groups` / `custom:tenants` are never touched.

- **One resolver, two carriers (R4.1).** A single **pure** resolver
  (`backend/src/auth/entitlement_resolver.py`) computes `roles ∩ active modules →
  capabilities`. The token claim and the Flask plane's `role_cache.py` decision both run
  that one rule, so they cannot disagree for the same state.

- **The Lambda reads the DynamoDB projection, not MySQL (Option A).** The
  Pre-Token-Generation Lambda gets its source rows from the S3 `governance_projection`
  table — keyed by the user's own `custom:tenants` partitions — using boto3 + an IAM role.
  No `mysql-connector` in the bundle, no Railway egress, single-digit-ms reads inside the
  5s budget. This honors the S1 contract and is consistent with S3's purpose. An **empty**
  projection yields an **empty** entitlement (`{v:1,t:{}}`) — a valid, handled outcome, not
  an error (and the expected state until the projection is populated).

- **Account placement (per `aws-accounts.md`).** Cognito pools live in the identity
  account (344561557829); Lambda + DynamoDB live in the data account (506221081911). The
  Pre-Token-Generation Lambda therefore runs in the **data account** (same-account
  projection read), and **Pool A attaches its trigger cross-account** — the *invoke* is
  cross-account, the *data read* is not.

- **Fail-safe + fail-fast.** A runtime resolution failure **omits** the claim (login still
  succeeds; readers fall back to their own source of truth) and logs the user identity +
  exception type only (no secrets). A genuine misconfiguration (missing projection
  table/region) **fails fast** and is never swallowed into a per-request omit.

- **Bounded staleness + revocation.** The token reflects the projection at issuance;
  staleness is bounded by the access-token TTL (Pool A: 60 min today). A named
  sensitive-capability subset (tenant/global admin, destructive ops) is re-validated
  server-side rather than trusted to expiry (the reader's three-state `has_capability`
  `None` = "consult server/S3"); severe cases use forced global sign-out. See
  `staleness-and-revocation.md`.

- **Delivered as an adoption toolkit; live trigger deferred.** S4 ships the entitlement
  functions as the vendored `sam/shared` toolkit — `get_verified_claims` / `get_groups`
  (S2) + `get_entitlements` / `has_capability` + the vendored `entitlement_claim` decoder —
  that a SAM-backed module **adopts** (replacing its own unverified auth, reusing its
  business-authz + HTTP plumbing). The functions are built, tested (property + integration),
  and available. **Wiring the live production Pool A Pre-Token-Generation trigger is
  deferred to the first app migration (S5),** so it is driven by a real consumer rather
  than done in a vacuum.

## Rationale

- Reading the projection instead of MySQL removes the only hard operational risk in the
  token path (Railway-from-Lambda, cold-start budget) and keeps the S1 "no MySQL from a
  module Lambda" invariant intact — the projection is exactly the data plane S3 built for
  this.
- A single pure resolver shared by both carriers is what guarantees the token and the
  server never disagree; it is also trivially property-testable.
- Deferring the live trigger to S5 avoids a production auth change with no consumer, and
  lets the first app migration validate the whole path (including the cross-account
  trigger) against real usage before it is relied upon.
- Empty-is-valid semantics mean the mechanism can go live before the projection is
  populated without breaking anyone: users simply carry no elevated entitlement, and the
  Flask plane keeps authorizing as today.

## Consequences

- **The entitlement toolkit is available now** for SAM modules to vendor and adopt; the
  h-dcn Members migration (S5) is its first consumer and will wire the trigger if/when it
  needs live token entitlement (it can validate against the test pool first).
- **The production projection must carry the token-relevant governance** for real tokens to
  be non-empty. S3's projection builder currently gates on SAM-backed-module tenants;
  widening it for ordinary Pool A tenants is an S3/S5 coordination item. Until then the
  reader correctly returns empty (handled), and the Flask plane remains authoritative.
- **The MySQL-reading reader was built first, then superseded** by the DynamoDB reader
  (Design amendment A). The pure resolver, codec, fail-safe/fail-fast handler wiring, and
  both-plane readers are unchanged by the swap — only the source of the rows changed.
- Later steps build on this: S5 (Members-first migration) adopts the toolkit and decides
  the live-trigger wiring; further app migrations are gated behind S5's Go/No-Go.

## Related

- ADR 0003, ADR 0004, ADR 0005 — this builds on all three.
- Steering: `.kiro/steering/architecture.md` (entitlement-in-token invariants),
  `authentication.md`, `identity.md`, `aws-accounts.md` (account placement).
- Spec `.kiro/specs/multi-tenant/s4-token-entitlement-projection/`:
  `requirements.md`, `design.md` (+ "Design amendment A" — read the projection, not MySQL),
  `staleness-and-revocation.md`, `claim-contract.md`.
- Next: `.kiro/specs/multi-tenant/s5-members-first-migration/` (the first consumer +
  Go/No-Go).
