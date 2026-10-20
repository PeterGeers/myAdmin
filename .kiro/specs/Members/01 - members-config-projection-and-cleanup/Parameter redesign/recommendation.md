# Members config & field-structure — Kiro recommendation

> **Status: RECOMMENDATION (opinion).** Built on `analysis.md` (Track 3). This is Kiro's view of
> the best-practice target and the pragmatic path to it — not yet requirements/design/tasks.
> Read `analysis.md` first for the grounded findings this rests on.

## 1. The situation in one paragraph

The Members runtime is excellent; the **config/authoring model behind it is the problem**. Config
lives as four `members.*` params in Flask (`field_overlay`, `scope_dimensions`, `view_contexts`,
`mail_enabled`), is projected Flask → DynamoDB for the SAM edge, and is authored through a
confusing UI (overlay-vs-fixed split, two editing surfaces, opaque "unresolved columns"). Several
of these surfaces are **redundant** with the generic filter/pivot UI the user already loves, and
the projection path has a reliability/visibility gap (#6/#7/#8). The real need is a **single,
coherent field model** — functional groups → fields → attributes — authored in one place, with
the projection made trustworthy and inspectable.

## 2. What a greenfield best-practice solution looks like

If we rebuilt this today with no legacy, the design would be:

1. **One field model, one list.** Every member attribute is a **field** in a single catalog. No
   user-facing "fixed vs overlay" split — provenance is just a `built-in | custom | calculated`
   badge. The only immovable field is `member_id` (UUIDv4); everything else is a configurable
   field with sensible defaults.

2. **A canonical attribute catalog as the backbone.** A field is fully described by a declared set
   of attributes: `key`, `type` ∈ {str, num, enum, boolean} (+ `enum-values` when enum), `label`,
   `required`, `visible`, `permission_roles`, optional `alias/display-name`, optional
   `scope-binding`, `calculated`. Required vs optional is explicit. This catalog is a
   **first-class, versioned artifact** — the backbone of both the data model and the UI.

3. **Functional groups as the organizing unit.** Groups are **first-class objects** (key, label,
   explicit order, optional role gating); each field references its group. The UI is
   **group → field → attribute**: pick a group, see its fields, edit a field's attributes from the
   catalog. Groups and fields carry explicit display order.

4. **No separate view-context object.** Column choice, filterability, and sort are runtime
   behaviours of the generic table + per-user column prefs — not stored config. The only genuine
   residual, **pagination**, becomes a simple tenant/field default (or a user pref), not a whole
   `view_contexts` surface.

5. **Scope as a field attribute, not a separate param.** A field flagged `scope-binding` drives
   row-level subset access; the filtering is derived from that flag + user grants. No standalone
   `scope_dimensions` list to author.

6. **No "analytics params" surface.** Analytics needs are met by existing/flattened fields,
   **calculated fields** (e.g. jubilee years, age bands), and **pivot filters** (e.g. magazine =
   paper/digital). A thing is only promoted to config if it provably can't be a calculated field
   or a filter.

7. **One home, one writer, with an inspectable projection.** Config is authored once and reaches
   the SAM edge through a projection that **auto-versions** and exposes **delivered/loaded status**
   (last-synced, version in effect, items loaded) so stale/failed syncs are diagnosable, not
   silent.

8. **i18n handled deliberately.** Labels are either a catalog attribute (`label{nl,en}`) **or**
   managed by i18n resources — picked once, consistently, not both.

## 3. Current vs greenfield — the gaps that matter

| Dimension        | Today                                              | Greenfield target                                 |
|------------------|----------------------------------------------------|---------------------------------------------------|
| Field model      | fixed ⊕ overlay ⊕ calculated (user sees the split) | one field list + provenance badge                 |
| Organizing unit  | overlay + groups as two unlinked sections          | functional groups as first-class, ordered         |
| Attributes       | implicit across code + schemas                     | explicit, versioned attribute catalog             |
| View contexts    | stored `view_contexts` param                       | retired; only pagination residual remains         |
| Scope            | separate `scope_dimensions` param                  | a `scope-binding` field attribute                 |
| Analytics        | "params" + #6/#7/#8 symptom                         | calculated fields + pivot filters, no param surface |
| Authoring surface| typed editor **and** raw Advanced params           | one authoring surface                             |
| Projection       | manual, version-bump trap, no read-side visibility | auto-versioned + delivered/loaded status          |

## 4. The one gating decision: config home (A / B / C)

The greenfield picture is mostly **writer-agnostic** — it describes the *model and UX*, not where
the bytes live. Where it is authored is the pivotal, steering-level choice from `analysis.md` Q3:

- **A — status quo** (Flask authors, projects to DynamoDB). Compliant, but keeps the pain.
- **B — Flask authors, projection made first-class** (auto-bump + delivered/loaded status).
  Steering-36 compliant, removes the operational pain **without** a second writer. **Kiro's
  recommended default.**
- **C — author natively in the SAM plane.** Cleanest "one home" story and the user's lean, **but
  it contradicts steering 36** (single MySQL writer). It is an architecture change, not a refactor
  — only pursue it with an explicit steering-36 revision.

**Recommendation:** adopt the greenfield **model and UX** (groups → fields → attribute catalog,
retire view_contexts, scope-as-attribute, no analytics params) regardless of home, and pick
**Option B** for the home unless you decide to revisit steering 36 for C. Model simplification
delivers most of the value and is not blocked by the A/B/C decision.

> **DECISION (user, 2026-10-12): Option B.** The tenant-administrator function for SAM apps
> stays in **Flask with the projection**; the projection is made **first-class** (auto-bump +
> delivered/loaded status). Steering-36 compliant, removes the operational pain **without** a
> second writer — Kiro's recommended default. **Option C is rejected; keep steering 36 as-is**
> (no steering-level revision). The config home is therefore settled — downstream work no longer
> waits on the A/B/C gate.

## 5. Suggested sequencing (pragmatic path, not a task list)

1. **Author the attribute catalog** (backbone; unblocks everything). Resolve the i18n label
   question here.
2. **Settle group identity + ordering** (first-class object vs field attribute).
3. **Decide config home A/B/C** — ✅ **DECIDED = B (2026-10-12):** Flask authors, projection
   made first-class; keep steering 36 (C rejected).
4. **Make the projection first-class** — auto-version + delivered/loaded status (fixes #6/#7/#8
   diagnosability).
5. **Collapse to one field list + provenance badge**; fold scope into a field attribute.
6. **Retire `view_contexts`** once the generic UI is confirmed to cover everything but pagination;
   decide the pagination model.
7. **Rebuild the authoring UI** (group → field → attribute) on the settled catalog.

## 6. What this is explicitly NOT

- Not a storage move — member data stays in `sam-members`.
- Not a decision on `mail_enabled` or Sender Addresses (separate specs).
- Not a change to user↔tenant↔roles authoring (stays Flask).
- Not requirements/design/tasks — this is a recommendation to steer those.

## 7. Best-practice gaps for Members + the three SAM modules (Members, Events, Webshop)

The platform's **architecture** best practices are already well-covered by steering: four-seam
layering (35), one-directional config projection (36), own-table tenancy + rule 5a (35),
verified-JWT + active-tenant resolution (20/22, ADR 0007), and the building-block registry (37).
What is **not yet covered** is the **operational / domain-correctness** layer. Those gaps barely
touch Members (config + records) but are exactly where **Webshop** and **Events** get expensive if
improvised. The three SAM-plane modules are confirmed as **Members, Events, Webshop** (the h-dcn
stack, `20-platform-architecture.md`); Members is the S5 pilot.

**Guiding principle:** steering 35's "build per-module first, extract on the second consumer (rule
of three)" is right for *mechanisms* (filter framework, analytics). The exceptions below —
idempotency, money, PII — should be **standardized up front**, because retrofitting them after an
order double-charges or a member exercises erasure is far costlier than extracting a shared helper.

### Cross-cutting gaps (all three modules)
1. **Idempotency at the write edge.** Projection writes are idempotent; **user-facing mutations are
   not**. Checkout (Webshop) and booking (Events) are double-submit/retry hazards. Need an
   `Idempotency-Key` convention + dedup record so a retried mutation is a no-op. *(Highest-priority
   missing practice for Webshop.)*
2. **Money / decimal handling.** No rule on monetary representation. Webshop prices/totals live in
   DynamoDB where floats are a trap. State it: integer minor units or `Decimal`, never float;
   explicit rounding; currency on every amount.
3. **Observability** — structured logging with a correlation id, failure metrics, and alarms on the
   Lambda plane. The Members "delivered/loaded status" gap (§4/impact #6) is a symptom of this same
   missing discipline.
4. **Data lifecycle: retention, soft-delete, PII/GDPR, audit trail.** Members holds member PII;
   nothing states retention, right-to-erasure, soft- vs hard-delete, or who-changed-what auditing.
   An EU membership + payments system needs this as an obligation, not an option.
5. **Pagination contract.** Settle a platform standard — **cursor/`LastEvaluatedKey`**, which
   DynamoDB favours, over offset. All three modules list data; `page_size` is already the
   view_contexts residual (§3).
6. **Accessibility (WCAG).** `32-frontend-ui.md` has UI conventions but no explicit a11y standard;
   Events landing pages and Webshop checkout are public-facing. *(Full compliance needs manual
   assistive-tech testing + expert review — tooling is only partial.)*

### Webshop-specific (heaviest domain, highest risk)
- **Payment integration boundary** — where the PSP sits, async webhook handling, and an order state
  machine (pending → paid → fulfilled → refunded) with **idempotent** webhook handlers. Deserves its
  own ADR before building.
- **Inventory invariants under concurrency** — stock reservation vs decrement, oversell prevention,
  abandoned-cart TTL, on top of steering-35 rule 2's conditional-write guarantee.
- **Order → FIN integration** — Webshop produces revenue; FIN is `mutaties`-centric. Define whether
  a paid order projects into `mutaties` (a SAM → Flask/MySQL flow) **without** violating rule 5a —
  do not improvise it.

### Events-specific
- **Time / timezone / recurrence** — store UTC, render local; a stated recurrence-rule convention
  for calendar + planning.
- **Landing pages reuse boundary** — reuse the existing landing-page capability
  (`infrastructure/landing-pages.tf` + the LandingPage editor) rather than rebuild (verify fit when
  Events starts); public pages add caching + SEO + the a11y point above.
- **Budget → FIN integration** — same question as Webshop→FIN: does event budget/actuals tie back to
  `mutaties`? Define it.

### Members-specific (the pilot — fix while cheap)
- The config reliability + observability gaps (version-bump trap, delivered/loaded status) are
  already in the impact analysis — they **are** the missing operational-correctness practice here.
- **PII / retention / audit** (cross-cutting #4) lands first on Members, since it holds the member
  records.

### Recommendation
- **Standardize now, as steering extensions** (not per-module reinvention): idempotency, money
  handling, pagination contract, and a PII/retention/audit baseline. Fold each into the relevant
  steering file (e.g. idempotency + money + pagination → a `3x` convention; PII/retention → platform
  architecture or a new narrowly-scoped file), per the "fold, don't fork" governance rule.
- **ADR before build** for the Webshop payment boundary and the order/budget → FIN integration.
- **Defer to rule-of-three** anything that is a reusable *mechanism* rather than a correctness
  obligation (shared analytics library, shared table toolkit).
- **For Members specifically**, the gaps are already captured; the only addition is to treat
  PII/retention/audit as a first-class requirement when the redesign reaches design.
