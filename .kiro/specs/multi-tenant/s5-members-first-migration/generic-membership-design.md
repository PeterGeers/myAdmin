# S5 — Generic membership administration + how a tenant (h-dcn) uses it

- Status: Draft (design of record for the Members migration)
- Companions: `members-wireframe.md` (current h-dcn scope + fixed/variable-field + layering), `scope-dimension-design.md` (region generalization),
  layering principles), `migration-plan.md` (the deployable steps), ADR 0003–0006.
- Governing steering: `.kiro/steering/sam-module-architecture.md` (handler=adapter;
  logic in domain services; DynamoDB=integrity), `identity.md`, `architecture.md`.

This answers three questions: (1) what makes the membership administration **generic**,
(2) how the **h-dcn** tenant uses that generic module, and (3) how genuinely
**tenant-specific** requirements are handled **without** forking the generic core.

## Principle: generic core is tenant-agnostic; differences are DATA, then RULES, then HOOKS

> The generic Members module contains **no `if tenant == "h-dcn"`**. Every tenant
> difference is expressed, in this order of preference:
> **1) config/data → 2) declarative rules → 3) registered hooks → 4) (last resort) a
> separate tenant service.** Reaching for a lower-preference rung is a signal, and the
> pilot **measures how often** each rung was needed (a key Go/No-Go input).

## 1. The generic membership administration

One consolidated **Members module** (single SAM Lambda, layered handler→service→
repository per the steering) owning what is the same for any club/association:

### Fixed domain (platform-owned, identical for every tenant)
- **Personal data** — name, contact, address, birthdate… (the base field **registry**).
- **Membership data** — member number, status, join/leave dates; the **membership
  lifecycle state machine** (e.g. application → pending → active → suspended → lapsed),
  delegates, and payment linkage.
- **Generic operations** — member CRUD, list/filter, export, membership transitions,
  delegate management. (The union of h-dcn's ~18 handlers, as internal routes.)

### Generic extension mechanisms (customize without forking)
- **Variable field overlay** — per-tenant "club details" fields via the field-config /
  `tenant_template_config` mechanism. Extends the **data shape** with **no schema change**.
- **Config-driven behavior** — per-tenant settings the generic engine reads at runtime:
  allowed statuses + transitions, required/visible fields per context, member-number
  format, whether the region model is enabled, approval-required flags, etc. Behavior is
  extended **by data, not code**.
- **Tenant scoping** — every record keyed by `tenant_id`; enforced in the repository
  (`tenant_id` PK + IAM `LeadingKeys`), so no layer above can cross tenants.

### What the generic module exposes (contract)
- A stable API (the routes the frontend calls) and a **resolved field config** endpoint
  (fixed base ⊕ tenant overlay) so a presentation-only React frontend renders per tenant.
- A **domain service layer** with the business rules, storage-agnostic and testable.
- A **repository** as the only DynamoDB touch-point.

## 2. How the h-dcn tenant uses the generic module

h-dcn becomes **tenant `h-dcn`** — a *configuration + data instance*, not a special build:

| h-dcn thing | Expressed generically as |
| --- | --- |
| Member personal/membership records | The **fixed base fields** (mapped during backfill) |
| Motor / club-specific fields | The **variable overlay** configured for tenant `h-dcn` |
| h-dcn membership states + transitions | The generic **transition config** for `h-dcn` |
| h-dcn regions + regional access | The generic **region model**, enabled + populated for `h-dcn` |
| Roles / who-can-do-what | Standard entitlement via `tenant_modules` + `sam/shared` for `h-dcn` |
| Data isolation | `tenant_id = "h-dcn"` partition + `LeadingKeys` |

So **supporting h-dcn = seed a tenant config + field overlay + backfill its data** into the
new tenant-scoped tables. Live h-dcn keeps running in parallel until cutover. Adding a
second club later is another config + overlay + backfill — **zero generic-code change**.

## 3. Handling genuinely h-dcn/tenant-specific requirements

Not everything fits config + overlay. The generic module handles the spectrum with
**declared extension points**, never tenant conditionals in core:

### Rung 1 — Config / data (preferred; most cases)
The difference is just *values*: which fields, which statuses/transitions, formats,
region on/off, approval flags. Expressed in the tenant's config + overlay. **No code.**

### Rung 2 — Declarative rules (config the generic engine interprets)
The difference is a *rule* expressible in a config schema the generic engine runs:
- "field X required when status = Y", conditional visibility,
- allowed transition graph (which state → which state, with guards),
- region-visibility rules (which regions a role sees).
The generic engine evaluates these; the rule set is tenant config. **Still no per-tenant code.**

### Rung 3 — Registered hooks / plugins (for truly bespoke behavior)
When behavior genuinely cannot be generalized, the generic core defines **named extension
points** and a tenant registers an implementation against its `tenant_id`, e.g.:
- `validate_member(tenant, record) -> errors`
- `on_transition(tenant, member, from_state, to_state)`
- `resolve_visible_regions(tenant, user) -> [region]`
- `derive_member_number(tenant, record) -> str`

The generic service calls the hook; the h-dcn-specific logic (e.g. a Motor-specific
validation, an h-dcn regional-access nuance) lives in a **tenant-scoped package/module**
registered for `h-dcn` — **not** in the generic core. Reuses h-dcn's existing business
logic (regional access, workflow) as the *body* of these hooks, cleanly separated.

### Rung 4 — Separate tenant service (last resort / escape hatch)
If a requirement fits none of the above cleanly, that is a **signal** the generic model may
not cover it — carve it into a separate tenant-specific service and **record it as a
Go/No-Go lesson** (does the generic approach actually hold, or does it leak?).

### The discipline
Always try to move a difference **up** the rungs (hook → rule → config). Every hook is a
question: "could this be declarative config instead?" The **pilot counts** how many h-dcn
requirements landed on each rung — that ratio is direct evidence for the Go/No-Go on
whether the generic membership model scales to the next club and the next app.

## Cross-club pressure test — does the generic model hold beyond h-dcn?

> **General domain knowledge, not repo fact.** Common membership-admin patterns across
> soccer / hockey / tennis / gym / scouting / multi-site clubs, used to stress-test the
> generic model. Each is mapped to the generic/tenant-specific rung (§3). This is input to
> the Go/No-Go — knowing them now lets us shape the model so club #2 fits without a redesign.

| Pattern (typical club) | Generic handling | Rung |
| --- | --- | --- |
| **Sub-grouping** differs by club — region (h-dcn) / team / section / location / chapter / none | The **scope dimension** (`scope-dimension-design.md`): tenant sets `key`/`values`, or disables it | 1 (config) |
| **Role × sub-group** (coach/manager scoped to a team; h-dcn regional roles) | role capability × `resolve_scope_access` | 1–2 |
| **Membership types/categories** (playing/non-playing/honorary/youth/family) with different rights/fees/required fields | `membership_type` = fixed field with **tenant enum**; per-type required-fields via **declarative rules** | 1–2 |
| **Age-based lifecycle / auto-transitions** (youth→senior at 18; season renewal) | the generic **lifecycle state machine** + date/age **declarative rules**; auto-promotion via `on_transition`/scheduled hook | 2–3 |
| **Approval / registration flows** (self-signup + approval — h-dcn `verzoek_lid`; waitlists; federation transfers) | lifecycle states + `approval_required` config; waitlist/transfer as tenant states + hooks | 1–3 |
| **Fees / payments** (per-type, per-season, family discount, SEPA direct debit, pro-rata) | payment linkage is fixed-domain; **fee calculation** is club-specific → `calculate_fee(tenant, member, period)` **hook** | 3 |

### Three generalization decisions this surfaces (design now, confirm at Go/No-Go)

These are common across clubs and **stress the current model** — h-dcn alone may not
surface them, but a soccer/hockey/tennis tenant will. Designing for them now avoids a
club-#2 rewrite:

1. **Member in MULTIPLE sub-groups** (two teams; team + committee). h-dcn is single-valued
   region; most sports clubs are not. → The scope model is therefore designed as a **list
   of dimensions, each optionally `multi_valued`** (`scope-dimension-design.md`), not a
   scalar. **Decision: build the multi-capable shape, wire h-dcn as the single/simple case.**
2. **Household / family membership** (one family, several linked members, one payer/contact).
   Very common in soccer/hockey/tennis; effectively a **member-relationship / grouping**
   concept, which is *data-model*, not just config. → **Open decision:** promote a generic
   "household/group of members with a designated contact" into the fixed domain, or handle
   as a Rung-3 relationship hook. Flagged for the pilot to decide with evidence.
3. **Season / period model** (soccer/hockey run Aug–Jun; teams + fees season-scoped; tennis
   calendar-year; gyms rolling). → Likely a **second scope dimension** (`key:"season"`) or a
   lifecycle-period config. **h-dcn (a federation) may not exercise this**, so the Members
   pilot might not surface it — noted explicitly so it is not mistaken for "proven covered."

### What the pilot records for the Go/No-Go

- The **rung distribution** for h-dcn (how much was config vs. rules vs. hooks vs. escape).
- A **design-review verdict** (even if not built) on whether a hypothetical soccer/hockey
  club — teams (multi-valued scope) + seasons + family membership + per-type fees — would
  fit the same generic model at Rung 1–3, or expose a gap. That verdict is the real test of
  "does the generic membership administration generalize," and it directly informs whether
  to proceed to Events/Webshop and to a second club.

## How this maps onto the layers (steering `sam-module-architecture.md`)

- **Frontend (React):** renders the resolved field config (fixed ⊕ overlay); no rules.
- **Handler (thin):** verified auth + entitlement (`sam/shared`) + tenant context; routes.
- **Application/domain service:** the generic engine — runs the lifecycle state machine,
  evaluates declarative rules, and **calls registered tenant hooks**. Tenant-agnostic core
  + a hook registry keyed by `tenant_id`.
- **Repository/DynamoDB:** tenant-scoped persistence + integrity (conditional writes for
  invariants like unique member number per tenant).

## What the Members pilot must therefore demonstrate (feeds Go/No-Go)

1. h-dcn runs entirely as **tenant config + overlay + hooks**, with the generic core free
   of tenant conditionals.
2. The rung distribution (how much was config vs. rules vs. hooks vs. escape hatch).
3. A **hypothetical second club** could be added by config/overlay alone for the common
   case — validated by design review even if not built in the pilot.
