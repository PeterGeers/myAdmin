# Design — 13. Public application-form rendering polish

## Overview

A presentation-only refactor of the PUBLIC application-form rendering path. R1–R4 are pure frontend
rendering changes (zero contract change). R5 (logo) resolves the tenant's ONE branding logo from the
single source `branding.company_logo_s3_key` (via a small reusable branding-logo read), so the same
logo can be reused across features — NOT gated on a published landing page. Nothing about the field
model, submit contract, validation, or readiness gate changes.

### The rendering path (as-is, confirmed by reading the code)

```
ApplicationFormBlock.tsx / PublicApplicationFormRoute
  └─ PublicApplicationPage         (fetch by slug; loading / 404 / "not accepting" states)
       └─ ApplicationFormPage.tsx  (page chrome: Heading, locale <Select>, consent, submit, 422 map)
            └─ ApplicationFormRenderer.tsx   (config-driven: groups → fields → widgets)
                 └─ applicationForm.model.ts (pure: groupFieldsByFunctionalGroup, resolveLabel, show_when)
```

- `groupFieldsByFunctionalGroup` buckets by `functional_group`, orders fields by `(order, key)`,
  and orders GROUPS by **first appearance** across the field list (not a sequence param).
- `ApplicationFormRenderer` draws each group as a `<fieldset>`/`<legend>` with a single-column
  `VStack` of `FormControl`s (label ABOVE control). `groupHeading` returns the raw group key and an
  EMPTY string for the `__default__` bucket.
- Enum/reference fields render a Chakra `<Select>` using the DEFAULT app theme (orange accent).
- No logo is rendered anywhere on the public APPLICATION form; `ApplicationFormPage` opens with
  `<Heading>`. (The public LANDING page DOES render a tenant logo from `landing.json` — that is the
  source R5 reuses; see R5 below.)
- The public application contract `PublicFieldConfig` = `{ fields, locales?, notice? }` — NO group
  label, NO group order, NO branding/logo. (R5 does NOT add one — it reads `landing.json`.)

## Per-requirement design

### R1 — group sectioning + readable headings (frontend only)

`groupHeading(config, groupKey, lang)` currently returns the raw key / empty for `__default__`.
Change:
- Resolve a presentable heading: if a group label becomes available (see note), use it; else
  present the raw `functional_group` key as-is (it is already a human-authored string on this
  tenant's config, e.g. `address`, `motor`, `financial`).
- The `__default__` bucket (fields with no `functional_group`): render its fields WITHOUT an empty
  `<legend>` artifact — either omit the legend for that one bucket or give it a neutral localized
  heading ("Overig" / "Other"). Omitting the empty legend is the lighter choice and avoids inventing
  a label; pick that unless the default bucket commonly holds fields (then use the neutral heading).

No contract change. The public schema carries no group-label catalog (design §3.1 of spec 10), so
this stays a frontend presentation decision. Heading styling (size/weight/spacing) is a Chakra prop
pass so sections read as sections.

### R2 — group AND field sequence (frontend only, pure helper)

Fields already order by `(order, key)` — keep. The gap is GROUP order. Options considered:

- **(A) Derive group order from the minimum field `order` within each group.** Contract-free: a
  tenant already authors field `order`, so the group a tenant "put first" is the group whose
  earliest field has the lowest order. Deterministic, stable tiebreak by group key.
- (B) Add a group-order field to the contract. Rejected for this spec — it crosses into the SAM
  serializer + the TenantAdmin authoring surface + the projection, far beyond a rendering polish,
  and R2 can be satisfied without it.

**Decision: (A).** Change `groupFieldsByFunctionalGroup` so `groupOrder` is sorted by
`min(field.order)` per group (then group key as tiebreak), with the `__default__` bucket pinned
LAST (preserve today's "surfaced, never dropped, trailing" behavior). Stays a pure function — one
focused unit test for the new group ordering, and the existing field-order tests keep asserting
`(order, key)` within a group.

> Note: this makes group order a FUNCTION of field order, which matches how a tenant reasons about
> sequence ("this field comes first, so its section comes first"). If a future need arises to order
> a group independently of its fields, that is the (B) contract addition — out of scope here, noted
> for a later spec.

### R3 — de-emphasize dropdown styling (frontend theme/prop)

The orange is the Chakra theme accent applied to `<Select>` by default. Make the select match the
text `<Input>` weight:
- Apply a consistent `variant`/style to BOTH `<Input>` and `<Select>` in the renderer (e.g. an
  `outline` variant with a neutral border, accent reserved for focus), so the two controls read at
  the same weight. Prefer setting this once (a shared style object or a theme component override for
  the public form) over per-field props so R3.2 "uniform" holds.
- Keep a clear dropdown affordance (the chevron) and a visible FOCUS ring — the softening is the
  resting fill/border, not the focus state (R3.3, HC2 contrast).
- Scope the styling to the public application form so the rest of the app's orange theme is
  untouched (the renderer/page is the boundary).

### R4 — responsive one-line + multi-column layout (frontend, Chakra responsive)

Two coupled layout changes inside `ApplicationFormRenderer`, both via Chakra's responsive array/object
props (no viewport sniffing, R4.3):

1. **Label beside control on wide screens, stacked on mobile.** Replace the per-field
   `FormControl`'s default vertical stack with a responsive layout: on `base` keep label-above
   (today), on `md`+ put label and control side-by-side (e.g. `FormControl` with
   `display={{ base: 'block', md: 'flex' }}` + an aligned `FormLabel` width, or a responsive
   `SimpleGrid`/`Grid` of label|control). Preserve `htmlFor`/`id` association (HC2).
2. **Multi-column group layout on wide screens.** Replace the group's single `VStack` with a
   responsive `SimpleGrid columns={{ base: 1, md: 2 }}` (≥2 columns on laptop/desktop, 1 on mobile,
   R4.1/R4.2). A field that needs full width (e.g. a `notes`/textarea-like field, if present) can
   set a `gridColumn="1 / -1"` span (R4.3).

Reading + tab order: a `SimpleGrid` lays out in DOM order, so the logical order stays the
config-resolved `(group order → field (order,key))` sequence — the error-summary anchor links keep
focusing the right control (R4.4). The axe gate (spec 10 task 9.5) is re-run against the grid layout.

### R5 — tenant logo at the top (ONE branding logo, reused by every feature)

**Goal (the right design): a tenant has ONE logo, resolved from ONE source, shown everywhere** —
the application form, public pages, internal UI, invoices/email. Today the logo is fragmented across
disconnected systems, which is the real defect this requirement should fix:

- `branding.company_logo_s3_key` — the tenant's logo object in the shared bucket
  (`myadmin-shared-production/<tenant>/branding/…`). This is where a tenant's logo actually lives
  (h-dcn has it set). **This is the single source of truth.**
- `str_branding`/`zzp_branding.company_logo_s3_key` — what `services/logo_resolver.py` reads for
  invoice PDF + email. A DIFFERENT namespace, so it misses the `branding` logo above.
- `landing_page.logo_url` — a separate URL string the landing page / `landing.json` uses, requiring
  the logo to ALSO live in the public-pages bucket and a landing page to be published.

A tenant should not have to configure the same logo in three places. R5 for the application form
should read the ONE branding source, and the broader "reuse one logo everywhere" is the design
direction (see the backlog note below).

**Decision for the application form:** resolve the logo from the single
`branding.company_logo_s3_key` source via a small, reusable branding-logo read — NOT from
`landing.json` and NOT gated on a published landing page (a tenant may have no landing page; the
application form must still show the logo). Concretely:

- Add a tiny **public branding-logo read** addressed by the tenant the form already resolves — it
  returns the tenant's logo as a URL (or inline data URI) from `branding.company_logo_s3_key`,
  reusing the existing `logo_resolver` logic pointed at the `branding` namespace. This is the ONE
  resolver every feature can call, so there is a single logo source.
- `ApplicationFormPage` renders `<Image src={logoUrl} alt={tenantName ?? 'logo'}>` constrained
  (`maxH={{ base: '48px', md: '72px' }}`, auto width, centered) ABOVE the `<Heading>` (R5.1/R5.4).
  Absent/unconfigured logo → render nothing (no broken image, R5.3).

> **Serving caveat (learned the hard way):** the `branding` logo lives in the SHARED bucket, which is
> NOT public and is NOT fronted by the landing CloudFront. So the read either (a) returns an inline
> base64 data URI (what `logo_resolver` already does for invoices/email — simplest, no public-URL
> dependency), or (b) serves it through an authenticated/short-lived URL. Prefer (a) for the public
> application form: it needs no bucket/CDN change and reuses the existing resolver.

> **Backlog — unify the logo across features (the user's actual ask).** Today's three logo configs
> (`branding.*`, `str_/zzp_branding.*`, `landing_page.logo_url`) should collapse to ONE tenant
> branding logo that every surface resolves from. That convergence is bigger than this rendering
> spec — capture it as its own backlog item (`tenant-branding-logo-single-source`) and have R5 here
> consume the single `branding` source so it's already aligned when the convergence lands.

## Accessibility (HC2) — explicit checks

- Label↔control association preserved through the side-by-side and grid layouts (`htmlFor`/`id`
  unchanged).
- Single logical reading/tab order via DOM-ordered `SimpleGrid`.
- Softer select styling keeps WCAG contrast + a visible focus ring.
- Logo `<Image>` has a non-empty `alt`.
- The existing axe test is extended to cover the new layout + the logo.

## Files touched

- `frontend/src/components/public/application/applicationForm.model.ts` — group-order (R2),
  heading helper (R1).
- `frontend/src/components/public/application/ApplicationFormRenderer.tsx` — headings (R1),
  select/input styling (R3), responsive label+grid layout (R4).
- `frontend/src/components/public/application/ApplicationFormPage.tsx` — render the tenant branding
  logo at the top (R5).
- A small public branding-logo read (R5): reuse `services/logo_resolver.py` pointed at the
  `branding` namespace, exposed on a public, tenant-addressed read the form can call. Resolve the
  exact plane/endpoint in implementation (the simplest is a Flask public read returning the inline
  data URI the resolver already produces).
- Tests: the `applicationForm.model` unit tests, the renderer/page render tests, and the axe test;
  a test for the branding-logo read (configured → logo, unconfigured → none).

## Non-goals / risks

- No change to field model, submit, validation, consent, readiness, or the authenticated form.
- No SAM public field-config contract change.
- R5 is NOT gated on a published landing page — the form shows the logo even when a tenant has no
  landing page.
- Risk: the shared `resolveLabel`/model helpers are also used by the authenticated Members form —
  the R2 group-order change is isolated to `groupFieldsByFunctionalGroup` (public helper), so the
  authenticated form is unaffected; confirm with its existing tests.
- Risk (R5): the logo read must NEVER hard-fail the form — an unconfigured logo is a graceful
  "no logo" (R5.3).
- Data caveat (R5): a tenant may simply have no configured logo (`branding.company_logo_s3_key`
  unset) — then there is nothing to show. Per-tenant config, not a bug in this spec.
