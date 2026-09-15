# Second Thoughts — Identity & Account Model

## Original notes (items to consider)

- Integrate the Cognito tooling in my personal AWS account as the main access
  function.
- For all generic AWS functions use the nonprofit AWS account (SES, SNS, Secrets,
  Parameters, DynamoDB, S3).
- Keep the Railway backend and MySQL server as the base module to manage
  `tenants`, `tenant_modules`, `user_tenant_roles`, and make an actual copy in
  DynamoDB.

---

## Assessment of the three items

**Item 1 — Cognito in the personal account.** Now a real option (not just
"reconsider"). The original objection was migrating live passkey users away from a
working pool — but H-DCN is **greenfield**: the only real user is
`webmaster@h-dcn.nl`, data is re-importable from Google Workspace, so there are
effectively no users to migrate. The remaining consideration is deliberate: the
personal account was previously flagged "legacy, do not deploy" — that rule is
being retired and the account repurposed as the tenant-neutral **identity
account**. For a multi-tenant platform where tenants come and go, hosting identity
in an account that is *yours* and tenant-neutral is defensible. **Decide on
merits, not on migration risk.**

**Item 2 — Generic services in nonprofit.** Strongly agree. Consistent with the
existing guardrails (`nonprofit-deploy` is *the* infra account). One account for
all shared infrastructure, one bucket-separation policy. This also makes Item 1
more coherent: if all generic services are in nonprofit, identity is the single
intentional cross-account exception.

**Item 3 — MySQL as tenant system-of-record + a DynamoDB copy.** Agree, with one
guardrail: the copy must be **one-directional** (MySQL = truth; DynamoDB = a
read-only synced projection, written only by a sync process, never edited
independently). Two-way writes = split-brain = a security incident waiting to
happen. Also decide it vs. the token projection (S4) deliberately: the token
carries the *resolved per-user answer*; the DynamoDB copy is for *tenant-level*
data a Lambda needs that is not user-scoped or is too large for the token. May
want both, or the token alone may suffice.

---

## Greenfield changes the whole risk profile

H-DCN is not in real production. This retires the biggest risk thread in the
analysis ("don't break prod / don't migrate live passkey users / a prior deploy
deleted prod data"):

- Cognito user migration is no longer the hard problem — recreate the pool
  wherever, re-enrol yourself.
- DynamoDB data is re-importable — moves can be light (wipe + re-import) rather
  than careful copy-verify. (S3 uploads / non-re-importable data still need care.)
- The roadmap's "both live systems must keep working" constraint relaxes for
  H-DCN; it still fully applies to the **myAdmin/Railway** side, which has real
  tenants, real data, and a real (small) user base.

**Reframing:** rather than "migrate two live systems together," it is "build the
unified multi-tenant target on the greenfield H-DCN side, prove it with myself as
the only user, then fold myAdmin's real tenants/data into the proven model."

> **Refined later (see `overall_roadmap.md` S1b / S6b + `environments_and_testing.md`):**
> the "greenfield-first" instinct here was about *avoiding production risk early*.
> The roadmap now achieves that without deferring the myAdmin work: the admin
> **code** is lifted into `mysaas/admin/` early (S1b) but runs only against the
> **test environment** (test Cognito pool + Docker MySQL + `test_` DynamoDB), and the
> **production CI/CD cutover is a separate, late, gated step** (S6b). So early work is
> safe because it is test-environment work, not because myAdmin is deferred. The
> spirit of this reframing holds — risky *production* change stays late — while the
> admin code still moves onto the trunk up front. This is a refinement, not a
> reversal.

---

## Identity model rethink — TWO pools by audience (not one)

Instead of a single survivor pool, split identity by **audience**:

- **Pool A — Admin / staff pool.** People who *operate* tenants: users with
  `user_tenant_roles`, tenant admins, sysadmins, finance staff, webmaster. Small,
  high-privilege population. Carries roles + `custom:tenants` + entitlement
  projection. ≈ the myAdmin/admin world.
- **Pool B — End-user pool.** People who *consume*: club members (self-service)
  and webshop customers. Large, low-privilege population. Carries only "valid
  member/customer + which tenant." ≈ the H-DCN member/webshop world.

### Why this is better than one pool

1. **Structural blast-radius boundary.** Admin claims literally do not exist in
   Pool B, so the large, less-controlled end-user population can never hold an
   admin role — a boundary by construction, not by policy.
2. **Right auth posture per audience.** Pool A wants strong auth (MFA, threat
   protection). Pool B wants low friction (passkeys, Google login, self-register).
   One pool forces one policy on both; two pools let each be correct.
3. **Different lifecycle/scale.** End-users self-register/churn in the thousands;
   admins are provisioned deliberately in the dozens. Cleaner, more auditable.
4. **Cleaner token contracts.** Pool A tokens are rich (roles + tenants +
   entitlement); Pool B tokens are simple. The SAM plane treats each safely.

### Tier choice resolves neatly

- **Pool A → Plus** (threat protection worth it for privileged users; tiny
  population so cost is trivial).
- **Pool B → Essentials** (passkeys included — WebAuthn is NOT Plus-only; 10,000
  free MAU; cheap at member scale).
- Financial impact of Plus at our scale is negligible either way (pennies now;
  ~$20–100/month even at realistic club/multi-tenant scale). Tier is a
  feature/security choice, not a cost choice.

### Mapping onto current pools

- **Pool A ≈ existing myAdmin pool `eu-west-1_Hdp40eWmu`** (personal/identity
  account) — already holds admin/tenant users and `custom:tenants`.
- **Pool B ≈ a NEW clean end-user pool** — greenfield, so create it right, no
  migration.
- Legacy pools still decommissioned: `eu-west-1_OAT3oPCIm`
  (H-DCN-Authentication-Pool), `eu-west-1_VtKQHhXGN` (Leden),
  `eu-west-1_fcUkvwjH5` (nonprofit H-DCN).

### Costs / open questions of the two-pool model

1. **Two verifiers.** Each backend must know which pool a token came from, verify
   against both pools' JWKS, and apply the right claim interpretation. Bounded,
   but it is two issuers / two app-client sets.
2. **The "admin AND member" person** (e.g. `webmaster@h-dcn.nl` administers *and*
   is a member). Must be designed explicitly: either such people live only in
   Pool A with member-like access granted there, or they hold two accounts. Do
   not leave ambiguous — this is the classic pain point of audience-split
   identity.
3. **`user_tenant_roles` scope.** It naturally governs Pool A users. Member→tenant
   membership for Pool B is a simpler, separate mapping. Two directory concepts —
   arguably cleaner, but two things to model.
4. **Pool-aware login/routing.** The merged frontend already routes by UI need, so
   admin screens authenticate via Pool A and member/webshop via Pool B — fits, but
   the login flow becomes pool-aware.

### Guardrail

Split by **audience only** (admin vs end-user). Do **not** split per-tenant or
per-app — that reintroduces the fragmentation the whole analysis avoids.

### Verdict

The two-pool (audience) model is **better than the single-survivor-pool plan** for
a multi-tenant product: the audiences differ so much in privilege, scale, and auth
needs that one pool forces bad compromises. Price is bounded: two verifiers + a
deliberate rule for the admin-and-member person. Worth it.

---

## Impact on other docs (to reconcile if this is adopted)

- `myadmin_as_base.md` — identity plane becomes two pools; token-contract section
  splits into Pool A (rich) vs Pool B (simple).
- `migration_plan.md` / `overall_roadmap.md` S3 — "survivor pool" becomes "Pool A =
  myAdmin pool; Pool B = new end-user pool."
- `aws-dynamodb.md` steering — record both pools, tiers (A=Plus, B=Essentials), and
  the admin-and-member open question.
- New ADR — "audience-split identity: admin pool vs end-user pool."

---

## Right-sizing: Pool B is a per-tenant option, not a platform given

Earlier reasoning over-indexed on H-DCN (members everywhere). Correction: myAdmin's
finance tenants (GoodwinSolutions, PeterPrive, InterimManagement) have **no
end-users at all** — only a few admins. So:

- **Pool A (admins) is the universal, always-present plane.** Every tenant has
  admins. This is the platform core.
- **Pool B (end-users) is an optional capability a tenant enables** — maps
  directly onto myAdmin's existing `tenant_modules` ("has webshop / member
  self-service" is just a module flag). Admin-only tenants never enable it.
- **The `person_id` linking / member→admin promotion / cross-pool SSO material is
  NOT core.** It only matters for tenants that enable Pool B *and* promote their
  own members to admins (an H-DCN-shaped case). **Defer it.** Note as open items,
  do not design now.

Mental model: **Pool A is the platform; Pool B is a per-tenant option.** A person
is an admin (Pool A) or an end-user (Pool B), or — only in tenants with both —
occasionally both, handled per-tenant, not as a base rule.

### Managing Pool B tenant relationships (kept simple)

Pool B tenancy is deliberately **simpler than Pool A's** — do not reuse Pool A
machinery:

- **Token (Pool B):** a single `tenant_id` claim (singular), not the
  `custom:tenants` list Pool A uses. No roles, no entitlement projection.
- **Relationship of record:** the member/customer row in that tenant's DynamoDB
  data (already carries `tenant_id` via S5). No `user_tenant_roles` equivalent
  needed — the member record *is* the relationship.
- **Established at registration:** the tenant is determined by the portal/shop the
  user enters through and stamped onto the Pool B identity + member record (with
  admin approval where the tenant requires it, e.g. H-DCN's `verzoek_lid`).
- **Default one tenant per Pool B user.** Multi-tenant membership (same human is a
  member of two clubs) is a deferred edge case, not base design — if ever needed,
  handle it the Pool A way (list + per-tenant record).
- **Enforced** like all portal data: SAM plane verifies the token, scopes DynamoDB
  by `tenant_id` (+ IAM LeadingKeys).

---

## Workspace strategy: build a NEW target workspace (do not merge the two)

The original S1 ("merge the two workspaces") is rejected. Merging first means
inheriting both codebases' legacy mess (two `.kiro/steering`, two skills, two spec
trees, two frontends, two backends) and reconciling artifacts of the past before
deciding what the target should be.

**Better approach:**

- **Create a new, clean workspace = the target platform trunk.** It represents the
  target, not either legacy system.
- **Seed it from the analysis, not the old code.** `.kiro/specs/multi-tenant/`
  (this Analysis folder) becomes the founding content. Author **fresh steering +
  skills** for the merged reality (two planes, two pools, MySQL-truth + token
  projection, tenant-key conventions) — governance is *authored*, not *merged*.
  This dissolves the old "reconcile two governances" (S1b) problem.
- **Keep the h-dcn and myAdmin workspaces alive** as the live systems; they get
  only migration-driven or keep-the-lights-on changes. Their real changes are
  reflected back into the target workspace's governance (keep-governance-current
  rule).
- **Migrate in thin vertical slices** — each roadmap step lands something real in
  the new workspace, pulling proven code from the legacy ones.

**Risk to manage:** the new workspace must be the definition of record (owns
roadmap + ADRs) from day one, or it becomes an aspirational graveyard while all
real work stays in the two old workspaces. Rule: target/migration work → new
workspace; keep-the-lights-on fixes → legacy workspaces.

### myAdmin: base for PATTERNS + the admin plane, NOT the single trunk

"Use myAdmin as the base" is right for the *ideas* and mostly right for the *admin
plane code*, but wrong as the single trunk. Separate the two meanings:

- ✅ **New workspace = trunk.** Neither legacy system is the base repo.
- ✅ **myAdmin = primary source of multi-tenant patterns** (tenant key,
  `@tenant_required`, provisioning, JWT verifier, `tenant_modules`,
  `tenant_template_config`). The new workspace leans toward myAdmin's patterns
  over H-DCN's.
- ✅ **myAdmin's code = the admin service plane** (stays Flask/MySQL), lifted in
  and adapted — as *a plane within the platform*, not the platform's foundation.
- ✅ **H-DCN = source of portal-domain code**, rebuilt tenant-aware on the
  serverless/DynamoDB plane (patterns from myAdmin, not its Flask code).
- ❌ **Not: myAdmin's codebase as the single trunk everything merges into.**

**Why not myAdmin-as-single-trunk:**
1. It is the one **live production system** (real tenants/financial data) — do the
   risky construction on the disposable (greenfield H-DCN) side, not the live one.
2. It would drag the serverless portal domain toward **MySQL/Flask**, undoing the
   deliberate two-plane / DynamoDB decision (`rewrite_vs_refactor.md`).
3. Its 307 backend files are mostly **finance-domain** logic, not reusable platform
   scaffolding — making it the trunk makes the platform myAdmin-domain-centric (the
   mirror of the H-DCN-centric bias already rejected).
4. It would bake myAdmin's naming/steering/role vocabulary in as defaults instead
   of deciding them fresh for the platform.

### Redefined S1 (replaces merge-first S1a/S1b)

- **S1 (new):** establish the target workspace — seed with
  `.kiro/specs/multi-tenant/`, author fresh steering + skills from the analysis,
  make it own the roadmap + ADRs. Keep h-dcn and myAdmin as live systems for
  migration-driven changes.

### New ADRs implied

- "New target workspace seeded from analysis; legacy workspaces remain live during
  migration."
- "myAdmin is the pattern source and admin-plane codebase, not the single trunk."

---

## Naming decisions

- **Target platform workspace name: `mysaas`** (at `/home/peter/projects/mysaas`,
  workspace file `mysaas.code-workspace`). Neutral — describes the multi-tenant
  SaaS platform, not any tenant's domain. Distinct from `myAdmin` and `h-dcn`, so
  no old-vs-new collision during migration.
- **Do NOT reuse the name "myAdmin" for the new platform, and do NOT rename the
  live system mid-migration.** Reasons: (1) name collision near production
  operations is exactly the data-loss failure mode the guardrails exist to
  prevent; (2) renaming the live Railway/AWS system (pool literally named
  `myAdmin`, `.env`, CI, git remotes, connection strings) is risky
  production surgery for a cosmetic gain; (3) it would invert the meaning of
  "myAdmin" across all existing analysis docs; (4) it would re-anchor the neutral
  platform to the finance system's identity.
- **Reusing myAdmin's CODE and PATTERNS is fine and is the plan** — only reusing
  its NAME while the original is alive is the risk. Lift the code into `mysaas`
  without touching the original's name.
- The "myAdmin" name can be reclaimed later **only after** the old system is fully
  decommissioned, if still desired.
