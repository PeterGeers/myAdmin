# Second Thoughts — Identity & Account Model

> Companion to `overall_roadmap.md` and `myadmin_as_base.md`. This doc holds the
> identity and AWS-account decisions the platform rests on. It assumes the settled
> model: **myAdmin is the platform base, evolved in place; additional apps are
> imported as SAM-backed modules.** Analysis + decisions — no code changed here.

## Original notes (items to consider)

- Integrate the Cognito tooling in my personal AWS account as the main access
  function.
- For all generic AWS functions use the nonprofit AWS account (SES, SNS, Secrets,
  Parameters, DynamoDB, S3).
- Keep the Railway backend and MySQL server as the base to manage `tenants`,
  `tenant_modules`, `user_tenant_roles`, and make an actual (read-only) copy in
  DynamoDB.

---

## Assessment of the three items

**Item 1 — Cognito in the personal account.** A real option. The original objection
was migrating live passkey users away from a working pool — but the incoming portal
(h-dcn) is **greenfield**: the only real user is `webmaster@h-dcn.nl`, data is
re-importable from Google Workspace, so there are effectively no end-users to
migrate. The remaining consideration is deliberate: the personal account was
previously flagged "legacy, do not deploy" — that rule is being retired and the
account repurposed as the tenant-neutral **identity account**. For a multi-tenant
platform where tenants come and go, hosting identity in an account that is *yours*
and tenant-neutral is defensible. **Decide on merits, not on migration risk.**

**Item 2 — Generic services in nonprofit.** Strongly agree. Consistent with the
existing guardrails (`nonprofit-deploy` is *the* infra account). One account for all
shared infrastructure, one bucket-separation policy. This also makes Item 1 more
coherent: if all generic services are in nonprofit, identity is the single
intentional cross-account exception.

**Item 3 — MySQL as tenant system-of-record + a DynamoDB copy.** Agree, with one
guardrail: the copy must be **one-directional** (MySQL = truth; DynamoDB = a
read-only synced projection, written only by a sync process, never edited
independently). Two-way writes = split-brain = a security incident waiting to happen.
Also decide it vs. the token projection (S4) deliberately: the token carries the
*resolved per-user answer*; the DynamoDB copy is for *tenant-level* data a SAM
module's Lambda needs that is not user-scoped or is too large for the token. May want
both, or the token alone may suffice.

---

## The incoming portal is greenfield — which shapes the risk profile

The h-dcn domain (the `members`, `events`, `webshop` SAM-backed modules, sharing one
SAM stack) is not in real production. This retires the biggest risk thread for the
module side ("don't break prod / don't migrate live passkey users"):

- Cognito end-user migration is not the hard problem — recreate the end-user pool,
  re-enrol the one real user.
- The portal's DynamoDB data is re-importable — moves can be light (wipe +
  re-import) rather than careful copy-verify. (S3 uploads / non-re-importable data
  still need care.)

**But the platform base — myAdmin/Railway — is live** with real tenants, real
financial data, and a real (small) user base. So the discipline splits cleanly:

- **Risky construction lands first on the greenfield portal-module side**, proven
  with one user, then generalized.
- **myAdmin changes stay careful.** Because myAdmin is the base we evolve in place,
  its identity, data, and deploys are treated as production throughout. The
  environments-and-testing discipline (test Cognito pool + Docker MySQL + `test_`
  DynamoDB, then gated promotion to production) is how myAdmin changes stay safe —
  see `environments_and_testing.md`.

---

## Identity model rethink — TWO pools by audience (not one)

Instead of a single pool, split identity by **audience**:

- **Pool A — Admin / staff pool.** People who *operate* tenants: users with
  `user_tenant_roles`, tenant admins, sysadmins, finance staff, webmaster. Small,
  high-privilege population. Carries roles + `custom:tenants` + entitlement
  projection. ≈ the myAdmin/admin world.
- **Pool B — End-user pool.** People who *consume*: club members (self-service) and
  webshop customers. Large, low-privilege population. Carries only "valid
  member/customer + which tenant." ≈ the portal member/webshop world.

### Why this is better than one pool

1. **Structural blast-radius boundary.** Admin claims literally do not exist in Pool
   B, so the large, less-controlled end-user population can never hold an admin role —
   a boundary by construction, not by policy.
2. **Right auth posture per audience.** Pool A wants strong auth (MFA, threat
   protection). Pool B wants low friction (passkeys, Google login, self-register).
   One pool forces one policy on both; two pools let each be correct.
3. **Different lifecycle/scale.** End-users self-register/churn in the thousands;
   admins are provisioned deliberately in the dozens. Cleaner, more auditable.
4. **Cleaner token contracts.** Pool A tokens are rich (roles + tenants +
   entitlement); Pool B tokens are simple. The SAM module plane treats each safely.

### Tier choice resolves neatly

- **Pool A → Plus** (threat protection worth it for privileged users; tiny population
  so cost is trivial).
- **Pool B → Essentials** (passkeys included — WebAuthn is NOT Plus-only; 10,000 free
  MAU; cheap at member scale).
- Financial impact of Plus at our scale is negligible either way (pennies now;
  ~$20–100/month even at realistic club/multi-tenant scale). Tier is a
  feature/security choice, not a cost choice.

### Mapping onto current pools

- **Pool A ≈ existing myAdmin pool `eu-west-1_Hdp40eWmu`** (personal/identity account)
  — already holds admin/tenant users and `custom:tenants`.
- **Pool B ≈ a NEW clean end-user pool** — greenfield, so create it right, no
  migration.
- Legacy pools still decommissioned: `eu-west-1_OAT3oPCIm`
  (H-DCN-Authentication-Pool), `eu-west-1_VtKQHhXGN` (Leden), `eu-west-1_fcUkvwjH5`
  (nonprofit H-DCN).

### Costs / open questions of the two-pool model

1. **Two verifiers.** Each plane must know which pool a token came from, verify
   against both pools' JWKS, and apply the right claim interpretation. Bounded, but it
   is two issuers / two app-client sets.
2. **The "admin AND member" person** (e.g. `webmaster@h-dcn.nl` administers *and* is a
   member). Must be designed explicitly: either such people live only in Pool A with
   member-like access granted there, or they hold two accounts. Do not leave
   ambiguous — this is the classic pain point of audience-split identity.
3. **`user_tenant_roles` scope.** It naturally governs Pool A users. Member→tenant
   membership for Pool B is a simpler, separate mapping. Two directory concepts —
   arguably cleaner, but two things to model.
4. **Pool-aware login/routing.** The merged frontend already routes by UI need, so
   admin screens authenticate via Pool A and member/webshop via Pool B — fits, but the
   login flow becomes pool-aware.

### Guardrail

Split by **audience only** (admin vs end-user). Do **not** split per-tenant or
per-app — that reintroduces the fragmentation the whole analysis avoids.

### Verdict

The two-pool (audience) model is **better than a single-pool plan** for a
multi-tenant product: the audiences differ so much in privilege, scale, and auth
needs that one pool forces bad compromises. Price is bounded: two verifiers + a
deliberate rule for the admin-and-member person. Worth it.

---

## Right-sizing: Pool B is a per-tenant option, not a platform given

Earlier reasoning over-indexed on h-dcn (members everywhere). Correction: myAdmin's
finance tenants (GoodwinSolutions, PeterPrive, InterimManagement) have **no end-users
at all** — only a few admins. So:

- **Pool A (admins) is the universal, always-present plane.** Every tenant has
  admins. This is the platform core.
- **Pool B (end-users) is an optional capability a tenant enables** — maps directly
  onto myAdmin's existing `tenant_modules` ("has webshop / member self-service" is
  just a module flag). Admin-only tenants never enable it.
- **The `person_id` linking / member→admin promotion / cross-pool SSO material is NOT
  core.** It only matters for tenants that enable Pool B *and* promote their own
  members to admins (an h-dcn-shaped case). **Defer it.** Note as open items, do not
  design now.

Mental model: **Pool A is the platform; Pool B is a per-tenant option.** A person is
an admin (Pool A) or an end-user (Pool B), or — only in tenants with both —
occasionally both, handled per-tenant, not as a base rule.

### Managing Pool B tenant relationships (kept simple)

Pool B tenancy is deliberately **simpler than Pool A's** — do not reuse Pool A
machinery:

- **Token (Pool B):** a single `tenant_id` claim (singular), not the `custom:tenants`
  list Pool A uses. No roles, no entitlement projection.
- **Relationship of record:** the member/customer row in that tenant's DynamoDB data
  (already carries `tenant_id` via S5). No `user_tenant_roles` equivalent needed — the
  member record *is* the relationship.
- **Established at registration:** the tenant is determined by the portal/shop the
  user enters through and stamped onto the Pool B identity + member record (with admin
  approval where the tenant requires it, e.g. h-dcn's `verzoek_lid`).
- **Default one tenant per Pool B user.** Multi-tenant membership (same human is a
  member of two clubs) is a deferred edge case, not base design — if ever needed,
  handle it the Pool A way (list + per-tenant record).
- **Enforced** like all module data: the SAM plane verifies the token, scopes
  DynamoDB by `tenant_id` (+ IAM LeadingKeys).

---

## Base / codebase strategy: evolve myAdmin in place (do NOT start a new codebase)

An earlier plan proposed starting a fresh codebase (`mysaas`) as the platform trunk
and lifting myAdmin's admin code into it. **That plan is abandoned.** It was tried and
did not work: standing up a new trunk meant re-hosting proven, live code before
delivering anything, and the "new workspace as definition of record from day one"
discipline was not sustainable — real work stayed in myAdmin anyway.

**Settled position: myAdmin IS the platform base, and we evolve it in place.**

- **myAdmin is the trunk.** It already carries the multi-tenant machinery the whole
  platform needs (tenant key `administration`, `@tenant_required`,
  `tenant_context.py`, provisioning, `jwt_verifier.py`, `tenant_modules` /
  `module_registry.py`, `tenant_template_config`). Building on it means building on
  proven, live code, not reconstructing it.
- **Additional apps come in as MODULES, not as a new trunk.** myAdmin's module system
  (`tenant_modules` + `MODULE_REGISTRY`, today FIN/ZZP/STR/TENADMIN) is generalized so
  a module can be **backed by an AWS SAM app** (Lambda + DynamoDB). The h-dcn domain
  becomes **three such modules — `members`, `events`, `webshop` — sharing one SAM
  stack**, each entitled independently via `tenant_modules`. This is roadmap S1.
- **The h-dcn domain stays on its optimal stack.** Importing it as SAM-backed modules
  keeps it serverless/DynamoDB — it is not dragged into Flask/MySQL. The two planes
  (Flask/MySQL admin+finance, SAM/Lambda/DynamoDB modules) are a deliberate
  design, not accidental (see `rewrite_vs_refactor.md`, `myadmin_as_base.md`).
- **Governance is myAdmin's existing `.kiro/steering`, extended in place.** New
  platform rules fold into the current steering (or add narrowly-scoped `fileMatch`
  files); we do not author a rival governance set.

### Why evolve-in-place beats a new trunk

1. **myAdmin is the one live production system** — but it is also the one with the
   proven tenancy machinery. Evolving it in place keeps that machinery working rather
   than re-deriving it in a fresh repo. Production risk is managed by the
   test-environment discipline (`environments_and_testing.md`), not by moving the code
   somewhere new.
2. **No trunk to keep "the definition of record."** With myAdmin as the base, there is
   no second workspace that risks becoming an aspirational graveyard while work stays
   in the real one. There is one place.
3. **The h-dcn domain stays serverless.** Importing it as SAM-backed modules
   (members/events/webshop) preserves the two-plane / DynamoDB decision; a merge into
   a Flask trunk would have undone it.
4. **The module system already exists.** Extending `tenant_modules` to back a module
   with a SAM app is an increment on proven code, not a new architecture.

---

## Naming (no rename)

- **The platform is myAdmin.** There is no separate `mysaas` workspace or name.
- **Do NOT rename the live system.** Renaming the live Railway/AWS system (pool,
  `.env`, CI, git remotes, connection strings) is risky production surgery for a
  cosmetic gain and would invert the meaning of "myAdmin" across all the analysis
  docs. The name stays.
- Incoming apps keep being described by their domain (the "portal" / "h-dcn" module),
  and are hosted as modules of the myAdmin platform.
