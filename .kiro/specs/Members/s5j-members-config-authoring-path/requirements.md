# S5j — Members config authoring path: scope-dimension dropdowns + editor load

## Problem

During s5d PHASE D browser testing, the Members page renders a shrunken table with an empty
`region` column, and clicking a member opens an **empty modal** (only Save/Cancel). Two
independent defects cause this:

1. **`GET /members/field-config` returns 502.** h-dcn's `region` overlay field is declared
   `type: enum` with **no `choices`**. The SAM field resolver rejects any enum field with no
   choices, so the whole field-config resolve throws. The SPA fetches field-config once to
   learn the tenant's fields/labels/order/options/view-contexts; with it down, the table
   columns and the modal have nothing to render.

2. **The Tenant-Admin → Members config editor fails to load** with `TypeError: Failed to
   fetch`. `getMembersParameterDefinitions()` builds an absolute URL via `buildApiUrl(...)`
   and then passes it to `authenticatedGet(...)`, which prepends the base URL **again** →
   a doubled URL (`https://host` + `https://host/api/...`). So the admin cannot author the
   config through the UI.

These are symptoms of one structural gap: the Members config **authoring → projection →
consumption** path was never verified end-to-end.

## Model (settled with the user)

`region` on a member record is **just a string** ("it is what it is"). Data ENTRY uses a
**dropdown of limited options**. Those options are the tenant's region vocabulary, which is
authored **once** in `scope_dimensions.values` (the same list the scope filter uses). The
scope filter is a separate concern (canonical-equal, or wildcard `*` = no filter) and is NOT
changed by this spec.

## Requirements

### R1 — Scope-dimension enum fields get their choices from the dimension
- **R1.1** `scope_dimensions` is a LIST and each dimension declares the member field it binds
  to via its `field` attribute (which defaults to the dimension `key` but MAY differ). When the
  field resolver resolves an OVERLAY `enum` field whose key matches an enabled dimension's
  `field`, it MUST populate that field's `choices` from that dimension's `values`. The match is
  on the dimension's `field` attribute, NOT an assumption that `field == key`.
- **R1.2** MULTIPLE scope dimensions are supported: a tenant may bind several fields (e.g.
  `region` and, for another club, `team`/`season`). The resolver MUST fill choices for EVERY
  overlay enum field that matches an enabled dimension's `field` — build a
  `{dimension.field: values}` map over all enabled dimensions and apply it to each match.
- **R1.3** This is the SINGLE source of truth for each vocabulary: no duplicate `choices` list
  is stored on the overlay field. (h-dcn's `region` stays as-is in MySQL — no data migration.)
- **R1.4** A non-scope-dimension enum field is unchanged: it still requires its own inline
  `choices`/`options` (e.g. `motor_brand`), and is still rejected if it declares none.

### R2 — field-config resolves (no 502)
- **R2.1** With R1 applied, `GET /members/field-config` for h-dcn MUST return 200, and the
  resolved config MUST include `region` with its 10 region values as choices.
- **R2.2** Resilience (design decision): a single invalid overlay field SHOULD NOT blank the
  entire field-config. (Scope: decide in design — either the scope-dimension case removes the
  only real trigger, or the resolver degrades one field instead of failing all. Keep minimal.)

### R3 — Entry is dropdown-driven; validation is change-gated (ALREADY EXISTS — verify)
- **R3.1** The member EDIT/CREATE modal renders `region` as a dropdown of the resolved choices
  (falls out of R1, presentation-only).
- **R3.2** On save: if `region` is **unchanged** from the stored value, accept it as-is (even a
  legacy value not in the list). If **changed** (or set on create), it MUST be one of
  `scope_dimensions.values`, else reject (422). This rule ALREADY exists in
  `MembershipService._reject_invalid_overlay_enum_values` ("enforce for new, tolerate legacy")
  but never fired for `region` because `region` had no `choices`. Once R1 gives it choices,
  this activates automatically. This spec VERIFIES it with a test; it does not add new
  validation logic.
- **R3.3** Change detection for the gate compares the submitted vs. stored `region` LITERALLY
  (any byte difference = changed → must be in list). Scope FILTERING remains canonical and is
  untouched.

### R4 — The config editor loads (frontend URL bug)
- **R4.1** `getMembersParameterDefinitions()` MUST build the request URL with the base prefix
  applied exactly once (fix the double-prepend). A regression test MUST assert the URL is
  single-based.

### R5 — Verify end-to-end before "done"
- **R5.1** SAM domain/unit tests green (resolver + the change-gated enum validation for a
  scope-dimension field, using h-dcn's real overlay + scope shapes).
- **R5.2** Frontend type-check/build green; the URL regression test green.
- **R5.3** After deploy: the editor loads; the Members table shows the `region` column
  populated; the modal renders fields incl. the `region` dropdown. (Manual browser confirm.)

## Out of scope
- Changing the scope filter / access model.
- Any h-dcn data migration (legacy region strings stay as-is).
- The broader fallback-mess code-quality track, projection reconcile, tenant-switch menu
  refresh (separate backlog items).
