# S5j — Design

## Overview

Two independent fixes, one spec. Both are small and land at a single seam each.

- **A (SAM):** the field resolver sources a scope-dimension enum field's `choices` from
  `scope_dimensions.values` at resolve time. This unblocks field-config (no 502), renders the
  `region` dropdown, and activates the already-existing change-gated validation.
- **B (frontend):** fix the doubled-base-URL bug so the Tenant-Admin Members editor loads.

No new validation logic, no scope/access change, no h-dcn data migration.

## Key facts established from the code

- The SAM `MembersProjectionReader` implements BOTH provider seams: `get_scope_config`
  (carries each dimension's `values`) AND `get_overlay`. So the scope vocabulary is reachable
  wherever the overlay is resolved.
- Today `FieldResolver` is constructed with ONLY the overlay provider —
  `FieldResolver(overlay_provider)` in `MembershipService.__init__`. It has no scope config,
  so it cannot see `region`'s values. This is the one wiring gap to close.
- `scope_dimensions` is a LIST; each `ScopeDimension` binds to a member field via `.field`
  (defaults to `.key`, but MAY differ — the binding is explicit and configurable). A tenant may
  declare MULTIPLE dimensions binding MULTIPLE fields. So "this overlay enum IS a scope
  dimension" = the overlay field's key matches an enabled dimension's `.field` (not an
  assumption that `.field == .key`). h-dcn happens to have one dimension where `region`→`region`,
  but the design must not hardcode that.
- The change-gated enum rule ALREADY exists: `MembershipService._reject_invalid_overlay_enum_
  values` — "enforce for new, tolerate legacy" — but it early-returns when `field.choices` is
  empty, so it never ran for `region`. Give `region` choices → it activates. No new code.
- Flask save-time validator (`members_config_validation.validate_field_overlay`) has the SAME
  "enum needs choices" rule. It is NOT hit by this design (we do not add choices to the stored
  overlay; the choices are derived at read time on the SAM side). The stored h-dcn overlay is
  unchanged, so the Flask validator's view of it is unchanged.

## D1 — Where to source the choices (the design decision)

**Decision: source at RESOLVE time in the service composition, keyed by the scope dimension's
`field`.** The `FieldResolver` stays a pure overlay→config transform; the SERVICE (which has
both the overlay and the scope config) injects the dimension values into the resolved config.

Two implementation shapes considered:

- **D1a (chosen): resolver gains an optional scope-vocabulary input.** `FieldResolver.resolve`
  (or a thin service wrapper) receives a `{dimension.field: values}` map built over ALL of the
  tenant's ENABLED scope dimensions (the list may bind several fields). For EACH overlay enum
  field whose key is a key in that map and which has no inline choices, it fills `choices` from
  the map. Keys are the dimensions' `.field` values (which may differ from `.key`). Keeps the
  "enum needs choices" invariant intact for genuine config bugs (a non-dimension enum with no
  choices still fails), while a dimension-backed enum is legitimately choice-less in storage.
- D1b (rejected): give `FieldResolver` a `ScopeConfigProvider` dependency. Rejected — couples
  the field resolver to the scope subsystem; the service already holds both, so pass data, not
  another provider.

**Why not populate the stored overlay (option "a" from earlier discussion):** that duplicates
the vocabulary into two MySQL places that drift. Sourcing at resolve time keeps
`scope_dimensions.values` the single source of truth (R1.2).

## D2 — Resilience (R2.2)

With D1, the ONLY field that triggered the 502 (region) is fixed at the root, so the 502 goes
away without changing the fail-fast contract. **Decision: keep the resolver fail-fast for a
GENUINE bad overlay** (a non-dimension enum with no choices is still a real config bug worth
surfacing) — do NOT broadly swallow overlay errors. Rationale: silent per-field degradation
hides real misconfig (the fallback-mess anti-pattern the user flagged). So R2.2 is satisfied
by removing the trigger, not by making the resolver lenient. (If later we want graceful
degradation, it is its own decision — out of scope here.)

## D3 — The change-gated validation (R3.2/R3.3) — verify, don't build

`_reject_invalid_overlay_enum_values(config, record, errors, previous=...)` already implements:
- CREATE (`previous is None`): every present overlay-enum value must be in `choices`.
- UPDATE: only enforce when the value CHANGED vs `previous` (literal `==`); unchanged legacy
  values pass. This is exactly R3.2/R3.3.
Once `region` carries resolved choices (D1), this fires for `region` automatically. This spec
adds a TEST that drives it with a scope-dimension `region` field; it changes no logic.

## D4 — Frontend URL fix (R4)

`getMembersParameterDefinitions()` currently: `buildApiUrl(endpoint)` → absolute URL →
`authenticatedGet(absoluteUrl)` → base prepended again → doubled URL. Fix: pass the RELATIVE
endpoint to `authenticatedGet` (which prepends the base once). Remove the now-unused
`buildApiUrl` import. Add a unit test asserting the request URL has the base applied exactly
once. (This edit is already drafted; the spec formalizes + tests it.)

## Seams touched

| Seam | File(s) | Change |
| --- | --- | --- |
| Resolve composition | `sam/members/domain/membership_service.py` (+ maybe `field_resolver.py`) | Inject scope-dimension vocabulary into the resolved config (D1a) |
| Validation (verify only) | tests in `sam/tests/` | Prove the change-gate fires for a scope-dimension enum |
| Frontend | `frontend/src/services/membersConfigService.ts` (+ a test) | Single-base URL (D4) |

## Non-goals (unchanged)
- The scope/access FILTER (which members a user may see): untouched.
- Stored h-dcn overlay / scope_dimensions data: unchanged (no migration).
- `FieldResolver` gaining a scope provider dependency (D1b): rejected.
