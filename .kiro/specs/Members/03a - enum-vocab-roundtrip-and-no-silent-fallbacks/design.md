# Enum-Vocabulary Round-Trip & No-Silent-Fallbacks Bugfix Design

## Overview

A tenant selectable field's option vocabulary round-trips **asymmetrically**: it is written
under one attribute name and read from another, so it disappears from the Members config editor
on reload — intermittently — because a one-sided fallback hides the mismatch on the member-form
path but not on the editor path. The same two-names disease shows up in a scope-specific variant
(the field's `options` and `FieldScope.values` are tracked in two places; only one survives).

Per the owner directive, this design does NOT special-case enum, reference, and scope-backed
fields. It unifies them on **ONE vocabulary model**: every selectable field resolves to ONE
canonical `options` list in the SAME shape `[{value, label?, roles?}]`, read by every consumer
with **no field-kind branching**. The kinds differ ONLY in the **source** that populates
`options` — inline (enum), live catalog (reference), or scope dimension (scope-backed). `choices`
is retired (legacy rows migrated), every silent fallback is removed, and "declares selectable but
resolves to no source" becomes a loud, uniform, caller-safe error.

**Where the unification lives (purity preserved).** `FieldResolver` (`field_resolver.py`) stays a
PURE, storage-agnostic resolver (steering 35/39): it does NOT read the catalog or DB. It already
consumes vocabulary as INJECTED inputs — scope arrives as a `scope_vocab={field_key: values}` map
built by the caller (`_membership_writes_fieldconfig._scope_vocab`, from the scope-config
provider). Reference options are NOT populated inside the resolver at all today: the READ-ASSEMBLY
layer does `config = resolver.resolve(...)` then separately attaches `_active_membership_type_options`
to the `membership_type` field. So the "one `options` shape, one read contract, no per-kind branch
in CONSUMERS" principle is enforced at that **read-assembly seam** (`get_field_config` /
`_membership_writes_fieldconfig`) — the one place that already injects `scope_vocab` and merges the
catalog — NOT by making the resolver fetch anything. (`catalogChoices`/`listMembershipTypes` are
frontend TS, not callable from the Python resolver — further reason population cannot live there.)

Scope is `config#fields` on the SAM plane only. Writes still flow through the spec-03 Change-Op
path (no whole-record replace). The Flask `field_overlay`/projection builders are out of scope
(separate spec-02 cleanup), as is the `user_tenant_scope` write bug (user scope, not config
scope). Scope RESOLUTION for access control still consumes `config#scope` / `ScopeConfig`
(spec context R2.3) — this design touches only a scope field's DISPLAY vocabulary, not access
evaluation.

## Glossary

- **Selectable field**: any field whose UI offers a fixed option list — enum, reference, or
  scope-backed. All three are the SAME model here.
- **Source**: WHERE a selectable field's vocabulary comes from. The ONLY thing that differs by
  kind. Inline overlay `options` (enum) / injected catalog-options map (reference) / injected
  `scope_vocab` dimension (scope). All three are INJECTED into / present at the read-assembly
  layer — none is a resolver catalog/DB read.
- **`options`**: the ONE canonical vocabulary — rich `[{value, label?, roles?}]`. Written for
  enum; POPULATED at the read-assembly seam for reference (from the injected catalog-options map)
  and scope (from `scope_vocab`). Every consumer reads this, uniformly.
- **Read-assembly seam**: `get_field_config` / `_membership_writes_fieldconfig` — the read layer
  that calls the pure `resolver.resolve(..., scope_vocab=...)` then uniformly populates each
  selectable field's `options` from its injected source. The resolver stays pure (no catalog/DB
  read); this seam is where "one `options`, no per-kind branch in consumers" is realized.
- **Bug_Condition (C)**: a selectable field that, through its declared source, resolves to NO
  populated `options` where it should have one — so `configEditorRead(afterPut(X))` disagrees
  with the member-form read (asymmetry), OR a scope field whose `options` and `scope.values`
  diverge because they are two copies.
- **Property (P)**: a selectable field ALWAYS resolves to a populated `options` from its declared
  source, and the editor and member form ALWAYS see the SAME `options`.
- **Preservation**: a field already resolving correctly renders identically in both reads;
  `application_choices` (public-form SUBSET) is untouched; scope ACCESS resolution unchanged.
- **`choices`**: LEGACY bare value list — the same vocabulary in a lesser shape. Retired (C7).
- **`application_choices`**: a SEPARATE SUBSET concept — NOT retired, unchanged (R3.2).

## Bug Details

### Bug Condition

The unified bug: a selectable field resolves to no populated `options` from its declared source
where it should have one, so the two read paths disagree. Three confirmed manifestations (harness
evidence, live local DynamoDB — do not re-derive):

1. **enum** bare-`choices` / `options`-absent → config editor reads `[]` (primary bug; RED gate
   `test_roundtrip_symmetry_choices_only_legacy_row`).
2. **scope** field authored with inline options → `options`/`choices` round-trip, BUT
   `FieldScope(values=())` came back EMPTY: `options` and `scope.values` are tracked in TWO
   places and only one survived — a scope variant of the same two-names disease.

**Not a bug (by design, unified model handles it):**
3. **reference** `membership_type` resolves with EMPTY inline options BECAUSE its vocabulary is
   the live catalog. Under the unified model the READ-ASSEMBLY seam populates `options` from the
   injected active-catalog map (`_active_membership_type_options`), so it is neither empty nor a
   fail-loud case. (The pure resolver never reads the catalog.)

**Formal Specification:**
```
FUNCTION isBugCondition(X)
  INPUT:  X = a selectable field (enum | reference | scope-backed)
  OUTPUT: boolean
  RETURN  isSelectable(X)
          AND ( (declaredSourceExists(X) AND assembledOptions(X) is empty)  // present source didn't propagate (asymmetry)
                OR configEditorRead(afterPut(X)) != memberFormRead(X)       // the two reads disagree
                OR (isScopeBacked(X) AND X.scope.values != [o.value for o in X.options]) ) // values not derived from options
END FUNCTION
```
`assembledOptions` is populated at the ONE read-assembly seam; `declaredSource(X)` selects inline /
injected catalog map / injected `scope_vocab` — the only per-kind input. The pure resolver reads no
catalog/DB. No consumer branches on kind. A source that is legitimately empty-by-design (no
`declaredSourceExists`) is NOT the bug (G5).

### Examples

- enum `referral_source`: stored `choices: [...]`, `options: None` → editor reads `[]`; member
  form renders 6. (RED gate.)
- scope field: inline options round-trip, yet `FieldScope(values=())` empty — `options` and
  `scope.values` diverged.
- reference `membership_type`: inline `options` empty by design → read-assembly seam fills from
  the injected active catalog (`_active_membership_type_options`); populated, NOT fail-loud.
- a field already resolving to populated `options` round-trips in both reads (preservation).

## Expected Behavior

### Preservation Requirements

**Unchanged behaviours:**
- A selectable field already resolving to populated `options` renders identically in editor AND
  member form.
- `application_choices` (public-form subset) behaves exactly as before — different concept.
- Scope ACCESS resolution still consumes `config#scope` / `ScopeConfig` — unchanged. This design
  touches only the scope field's DISPLAY vocabulary.
- Spec-03 Change-Op guarantees: isolated, non-truncating, server-owned placement, no
  whole-record replace. The `options` write still goes through the Change-Op path.

**Scope:** every input that is NOT a selectable-field vocabulary resolution is unaffected — other
field attributes, functional groups, the application-form subset, non-selectable fields.

The expected CORRECT behaviour for buggy inputs is defined in Correctness Properties (P1).

## Hypothesized Root Cause

One vocabulary is addressed by multiple names/places that mean one thing, and the paths disagree
on which is authoritative — plus a per-kind split where there should be one seam:

1. **Per-kind branching + split population instead of one assembly seam.**
   `field_resolver._as_variable_field` (VARIABLE path) sources `options` from inline `options`
   only; `_apply_override` (FIXED path) coalesces differently. The reference catalog is merged in
   a SEPARATE step (`get_field_config` attaching `_active_membership_type_options`) and scope
   arrives via `scope_vocab` — three populations with no single uniform assembly point, so
   `_fields_overlay_reader._build_overlay_field` / `_build_override` / `_build_options` and the
   consumers still branch by kind.

2. **Scope vocabulary tracked twice.** `FieldScope.values: Sequence[str]` (`_field_models.py`,
   BARE strings) and the field's rich `options` are two separately-stored copies. A write/resolve
   can populate one and leave the other empty (`FieldScope(values=())`). The code comments assert
   a single-vocabulary rule the data model does not enforce.

3. **Reference vocabulary populated OUTSIDE the uniform path.** The active catalog is attached to
   `membership_type` only by `get_field_config`'s separate `_active_membership_type_options` merge
   (the pure resolver correctly never reads the catalog). Because that merge is a one-off step, not
   part of a uniform per-field assembly, consumers cannot treat reference like the other kinds.

4. **Config editor reads `options` only.** `MembersFieldModal.optionsToChoices` /
   `formFromResolvedField` seed from `options` → empty when `options` is None/empty. The member
   form has an `options or choices` fallback → renders anyway, hiding the asymmetry.

## Correctness Properties

Property 1: Bug Condition — Unified Selectable-Vocabulary Resolution & Read Symmetry

_For any_ selectable field (enum, reference, or scope-backed) where the bug condition holds
(`isBugCondition` returns true), the fixed system SHALL populate a POPULATED `options` from the
field's DECLARED SOURCE (inline overlay / injected catalog map / injected `scope_vocab`) at the
ONE read-assembly seam, and the config editor read and member-form read SHALL both return the
SAME `options` — with NO field-kind branching in any consumer. For a scope-backed field,
`FieldScope.values` SHALL be the DERIVED projection `[o.value for o in options]` of that same
`options` (one derivation point, never an independent copy), so the two can never diverge.

**Validates: Requirements 2.1, 2.2, 2.6**

Property 2: Preservation — Already-Resolving & Separate-Concept Behavior

_For any_ input where the bug condition does NOT hold (a field already resolving to populated
`options`, a non-selectable field, `application_choices` usage, or scope ACCESS resolution), the
fixed system SHALL produce the same result as the original, preserving both reads, the
`application_choices` subset, scope access evaluation, and the spec-03 Change-Op guarantees.

**Validates: Requirements 3.1, 3.2, 3.3**

Property 3: Fail-Loud — Declared-Selectable-But-No-Source Raises, Uniformly, Never Degrades

_For any_ field that DECLARES a selectable source which EXISTS but whose vocabulary did NOT
propagate into `options` (the asymmetry) — for ANY kind, no exemptions — the fixed read path SHALL
raise a LOUD, caller-safe, diagnosable error at the boundary and SHALL NOT silently fall back,
substitute an empty list, or coerce the shape. Fail-loud fires on the asymmetry (declared source
present, `options` empty), NOT on a source that is legitimately empty/absent-by-design. So: an
un-migrated null/malformed row IS an error; an enum with no inline options AFTER migration IS;
a reference whose non-empty catalog failed to attach IS. But a scope dimension with ZERO values
yet, or a newly-created not-yet-populated field (no declared source populated at all), is a
LEGITIMATE in-progress state and does NOT raise — it is not the asymmetry. (A reference whose
catalog correctly populates `options` is also not this case.)

**Validates: Requirements 2.3, 2.6**

Property 4: Write-Edge Duplicate-Value Rejection

_For any_ `options` payload containing a duplicate `value`, the write SHALL reject it with a
caller-safe 400 (steering 30; no `str(e)` leak) BEFORE any repository call.

**Validates: Requirements 2.4**

## Fix Implementation

### The selectable-vocabulary assembly (the heart of the fix)

The fix is ONE "selectable-vocabulary assembly" at the **read-assembly seam** (`get_field_config`
/ `_membership_writes_fieldconfig`) — the place that already calls the pure resolver and injects
both vocabulary sources. It populates every selectable field's `options` from its INJECTED source;
the resolver stays pure (no catalog/DB read).

```
// Read-assembly layer (NOT the pure resolver):
config := resolver.resolve(tenant_id, scope_vocab=scopeVocab)   // pure; scope injected
catalogOpts := activeMembershipTypeOptions(tenant_id)           // injected catalog map

FUNCTION assembleSelectableOptions(field, scopeVocab, catalogOpts)
  src := declaredSource(field)        // the ONLY per-kind decision
  options := CASE src OF
    inline    -> field inline overlay options        // enum
    catalog   -> catalogOpts[field.key]              // reference (injected, not resolver-read)
    scope     -> asOptions(scopeVocab[field.key])    // scope-backed → rich options
  IF declaredSourceExists(field, src) AND options is empty THEN  // the ASYMMETRY only
    RAISE loud caller-safe error (tenant + field key)            // uniform fail-loud (C6/G5)
  field.options := options            // canonical, same shape, all kinds
  IF isScopeBacked(field) THEN
    field.scope.values := [o.value for o in options]  // DERIVED projection, single point
  RETURN field
END FUNCTION
```

Every consumer (editor read, member-form read, symmetry gate, fail-loud) reads `field.options`
with NO kind branching. `declaredSourceExists` is what keeps a legitimately-empty source (scope
dimension with no values yet, newly-created field) from tripping fail-loud — only a PRESENT source
that failed to propagate raises (G5). The resolver is UNCHANGED in its purity; the only new code is
this seam's uniform population + the scope derivation.

### Components (C1..C7)

**C1 — Frontend author/read `options` only, no kind branch** (`fieldConfigChangeOps.ts`,
`MembersFieldModal.tsx`). Remove `choices` from `DEFINITION_ATTRS` so the write emits ONLY
`options`. `MembersFieldModal.optionsToChoices` / `formFromResolvedField` seed the editor from the
single `options` the seam returns — identically for enum, reference, and scope (no reference/scope
special-case); C6 makes a propagated-but-empty source an error, not a silent empty.

**C2 — Write surface accepts `options` only** (`config_fields_crud_service.py`). Remove `choices`
from `FIELD_DEFINITION_ATTRS`. Storage key stays `overrides`, served under wire key
`fixed_overrides` (one-key contract preserved). Write remains a Change-Op on a single path — no
whole-row replace (R3.3).

**C3 — Write-edge duplicate-`value` guard** (`config_fields_crud_service.py`, before any repo
call). Reject an `options` list with a duplicate `value` via `ConfigFieldsCrudError` (subclasses
`ValueError`); the edge maps it to a caller-safe 400 (R2.4, steering 30).

**C4 — Read-assembly seam populates `options` uniformly; resolver stays pure**
(`_membership_writes_fieldconfig.py` `get_field_config`; `field_resolver.py` unchanged in
purity). `get_field_config` already does `config = resolver.resolve(tenant_id,
scope_vocab=self._scope_vocab(tenant_id))` then merges `_active_membership_type_options`. Replace
that one-off reference merge + the implicit per-kind handling with a UNIFORM pass that, for every
selectable field, sets `options` from its injected source — inline from the overlay (enum),
`_active_membership_type_options` (reference), `scope_vocab` (scope) — and derives
`FieldScope.values` from it (G2). The pure `FieldResolver` is NOT given catalog/DB access and does
NOT read `listMembershipTypes`/`catalogChoices` (those are frontend TS anyway); it continues to
consume `scope_vocab` as today. `_as_variable_field` / `_apply_override` keep sourcing inline
`options` purely; the reference/scope population lives at the seam, not in the resolver.
The STAFF config-editor read serializer `_serialize_field` (`_membership_catalog.py`) and the
SAM PUBLIC-form read serializer `_public_field_options` (`_membership_writes_fieldconfig.py`) are
the two consumers OF this seam: collapse the `membership_type` per-kind branch + drop the
`choices` fallback in `_serialize_field` (F9) so it serializes the ONE `options` the seam
populated, and drop the `field.choices` fallback in `_public_field_options` (F10) while PRESERVING
its R3.2 public-subset filter (`application_choices` ⊆ `options` stays; only the fallback goes).

**C5 — Reader build collapses split handling** (`_fields_overlay_reader.py`, `_field_models.py`).
`_build_overlay_field` / `_build_override` / `_build_options` stop carrying enum/scope vocabulary
through split paths and surface ONE `options`. Drop the `options or choices` coalesce (F1), the
separate-`choices` carry (F2), and the bare-string coercion / degrade-to-None branch (F3). Scope
is built so `FieldScope.values` is the DERIVED projection `[o.value for o in options]` of the
canonical `options` — one derivation point at the seam, never an independently stored copy (G2);
this removes the `FieldScope(values=())` divergence by construction.

**C6 — Fail-loud boundary, uniform across kinds, on the ASYMMETRY only** (seam, G5). Fail-loud
fires when a field's DECLARED source EXISTS but its vocabulary did not propagate into `options`:
an un-migrated null/malformed row, an enum with no inline options AFTER migration, a reference
whose non-empty catalog failed to attach. It does NOT fire for a source that is legitimately
empty/absent-by-design — a scope dimension with zero values yet, a newly-created not-yet-populated
field — which stays a valid in-progress state. A reference whose catalog populates `options` is
not this case. No per-kind exemption. Generic client message per steering 30; full detail logged
server-side under a correlation id.

**C7 — Small targeted `choices`→`options` backfill (right-sized)** (migration script). Real usage
is LIMITED — essentially the one h-dcn `referral_source` row carries bare `choices`. So this is a
SMALL idempotent targeted backfill, NOT the spec-03 heavy version-guarded prod-copy machinery:
enumerate the few `config#fields` rows carrying bare `choices`, rewrite each to value-only
`options` (`[{value: v} for v in choices]`), drop `choices`. Idempotent (re-running is a no-op
once a row has `options` and no `choices`) and verified by a read→migrate→read check on the REAL
h-dcn row (the 6 `referral_source` values survive as `options`). A one-shot script — or even
manual-with-verification given the scale — is sufficient; NOT a flag-day, NOT a PITR-backed
prod-copy rehearsal. Acceptable alternative: **fix-forward** — the next normal `set_field` write
re-stores the row as `options`. Must run (or the row be fixed-forward) BEFORE C8 flips to BLOCKING
so no live bare-`choices` row trips the guard.

**C8 — Mechanical anti-reintroduction guard** (`scripts/check_sam_config_crud.py` +
`sam/tests/test_check_sam_config_crud.py`, pre-commit + CI). Deletion alone is insufficient —
the old path must FAIL THE BUILD if re-added (spec 03 lesson). EXTEND the existing AST guard
(same mechanism: real code only, not comments/docstrings; allow-list discipline; never
`--no-verify`) with four new rules: (a) a `choices` key on the config#fields WRITE path;
(b) an `options or choices` / `choices or options` fallback expression in reader/resolver OR a
read of `field.choices` as a fallback vocabulary SOURCE in a serializer — this covers the
`_serialize_field` fallback (F9), the `_public_field_options` fallback (F10), AND the write-side
`_field_choice_values` coalesce (F12), which is why F12 is MIGRATED to `options`-only rather than
allow-listed; (c) a per-field-KIND branch in a vocabulary CONSUMER where the uniform read-assembly
`options` must be used — targets the `_serialize_field` `membership_type` branch (F9) and the
`_public_field_options` per-kind branch (F10). TWO documented CARVE-OUTS from rule (c): the R3.2
public-SUBSET FILTER in `_public_field_options` (filtering `options` down to the declared
`application_choices` is a legitimately different projection, NOT a forbidden read-shape branch —
only the `choices` FALLBACK is retired, F10); and the frontend picker-SOURCE adapter
`resolveChoiceSource` (`applicationChoiceSource.ts`, F11), which only SELECTS the declared source
and does not branch the resulting `options` read shape; (d) `FieldScope.values` populated
independently of `options` (not as the derived projection). Each rule gets a PLANTED-VIOLATION
test (plant → guard fails; clean → passes).
Rollout: REPORT-ONLY → clear baseline → BLOCKING, and the flip to BLOCKING happens only AFTER C7
+ C1–C6 land and the gate is green (G6; see Deployment ordering). This is the enforcement layer
that makes the structural fixes (C1–C7) un-regressable.

### Scope single-vocabulary collapse (C5 detail)

The two shapes DIFFER — the field's `options` is rich `[{value, label?, roles?}]`, while
`FieldScope.values: Sequence[str]` (`_field_models.py`, a FROZEN dataclass) is BARE strings. So
"same list" is not literal. The rule is: **`options` is canonical**, and `FieldScope.values` is a
DERIVED projection `[o.value for o in options]`, computed at the seam at resolve/serialize time —
never an independently stored second copy. There is a SINGLE derivation point (the seam, C4/C5),
so the two can never diverge: a scope field cannot carry `options` populated while `scope.values`
is empty (the observed `FieldScope(values=())` bug) because `values` is not stored, it is projected
from `options` every time. Scope ACCESS resolution continues to read `config#scope` / `ScopeConfig`
separately — that boundary is unchanged; this collapse is DISPLAY vocabulary only.

### Fallback-Removal List (each hiding fallback / divergence → unified path + loud error)

| # | Fallback / divergence (today) | Location | Replacement |
|---|---|---|---|
| F1 | `_build_override`: `_build_options(options) or _build_options(choices)` | `_fields_overlay_reader.py` | seam reads from declared source only; legacy `choices` migrated (C7) or loud error (C6) |
| F2 | `_build_overlay_field` carries `choices` as a separate vocabulary attr | `_fields_overlay_reader.py` | one `options` via seam |
| F3 | `_build_options` coerces bare string; degrades malformed → `None` | `_fields_overlay_reader.py` | canonical entries only; unexpected shape → loud error (C6) |
| F4 | `_as_variable_field`: inline `options` only, no other source (silently → None) | `field_resolver.py` | resolver stays pure (inline only); read-assembly seam populates reference/scope; propagated-but-empty is loud, not empty |
| F5 | Member-form read: `options or choices` | member-form read path (frontend) | read the one `options` the seam returns |
| F6 | `optionsToChoices` empty-on-absent (editor) | `MembersFieldModal.tsx` | one `options` is the sole source; a propagated-but-empty source is loud/diagnosable, not silent empty |
| F7 | Scope `FieldScope.values` and `options` tracked as TWO copies (`FieldScope(values=())`) | `_field_models.py`, `_fields_overlay_reader.py` | `values` is the DERIVED projection `[o.value for o in options]` at a single seam point — not a stored copy |
| F8 | Reference inline `options` empty, active catalog merged one-off outside the uniform path | `_membership_writes_fieldconfig.py` (`get_field_config`) | READ-LAYER assembly populates `options` from the injected `_active_membership_type_options` map — NOT a resolver catalog read (resolver stays pure) |
| F9 | `_serialize_field`: a per-field-KIND branch (`membership_type` special-case) PLUS an `options → choices` fallback (`elif field.choices is not None: payload["options"] = list(field.choices)`) — on the STAFF config-editor read serializer that `get_field_config` (the C4/F8 read-assembly seam) calls for EVERY field | `_membership_catalog.py` (`CatalogMixin._serialize_field`, ≈300–309) | collapse the per-kind branch and drop the `choices` fallback; serialize the ONE canonical `options` the seam (C4/F8) populated — this is the serializer the "editor reads `options` only" symptom flows through, so the C4 collapse is incomplete if this per-kind branch + `choices` fallback survives here |
| F10 | `_public_field_options`: a per-field-KIND branch + reads `field.choices` as a fallback vocabulary source (`if field.choices is not None: ... list(application_subset_choices(field))`) on the SAM PUBLIC-form read serializer | `_membership_writes_fieldconfig.py` (`_public_field_options`, ≈342–390) | remove the `field.choices` fallback here (read the seam's ONE `options`), while PRESERVING the public-subset projection (the `application_choices` ⊆ `options` filter) — the subset FILTER is a legitimately different projection per R3.2 and stays; only the `choices` FALLBACK is retired |
| F11 | `resolveChoiceSource`: an explicit reference/scope/enum KIND branch in the frontend picker-SOURCE adapter | `applicationChoiceSource.ts` (`resolveChoiceSource`, ≈104–123) | **LEGITIMATE SOURCE-SELECTOR CARVE-OUT, not a removal.** Confirmed by reading the file: `resolveChoiceSource` ONLY selects the declared source (reference→live catalog, scope→own `options`, enum→own `options`) and normalizes it — it does NOT branch the consumer READ SHAPE of the resulting `options`. Choosing the declared SOURCE this way mirrors the SAM seam's `declaredSource` and is allowed. The rule that remains forbidden (C8 rule (c)) is any per-kind branching of the resulting `options` READ shape in a consumer — which this file does not do. No code change; documented so the C8 guard does not false-positive on it |
| F12 | `_field_choice_values`: a write-side `_collect(spec.get("options")) or _collect(spec.get("choices"))` coalesce, used to validate an `application_choices` subset against the field's vocabulary | `config_write_service.py` (`_field_choice_values`, :542) | migrate to read `options` only (drop the `choices` fallback) now that C7 backfills every live row and C2 drops `choices` on the write — so the write-side validator reads the ONE canonical vocabulary. Prefer this migration over a C8 allow-list carve-out (the migration is clean: C7 guarantees `options` is present before C8 flips to BLOCKING) |

### Deployment ordering

1. **C7 backfill FIRST** (or fix-forward the one h-dcn row), verified against the real row, so no
   live bare-`choices` row remains.
2. **THEN C1–C6 land** — the uniform assembly, scope derivation, and fail-loud. This prevents a
   window where a not-yet-migrated bare-`choices` row trips C6 in production.
3. **C8 flips REPORT-ONLY → BLOCKING LAST** — only AFTER C7 + C1–C6 have landed and the gate is
   green (G6). Flipping the blocking guard earlier would redden valid in-flight states (a
   half-authored field, a scope dimension not yet populated, an un-migrated row); the guard goes
   blocking once the tree is clean, never on day one (spec-03 discipline).

## Testing Strategy

### Validation Approach

Two-phase: surface the counterexample on UNFIXED code (the enum RED gate exists), then verify the
unified seam resolves populated `options` for all three kinds and both reads agree. The acceptance
invariant is the generalized one — a selectable field always resolves to a populated `options`
from its declared source, and editor and member form see the SAME `options`.

### Exploratory Bug Condition Checking

**Goal:** surface the counterexamples before the fix; confirm the unified root cause.

**Primary gate** `sam/tests/e2e/test_enum_vocab_roundtrip_e2e.py` — container-gated E2E against
local DynamoDB (:8000), extended to run ALL kinds through the ONE read path:
- `test_roundtrip_symmetry_options_authored` — PASSES today (enum options-authored round-trips).
- `test_roundtrip_symmetry_choices_only_legacy_row` — FAILS today (enum bare-`choices` → `[]`).
  RED acceptance gate.
- **NEW scope case** — authored scope-backed field; asserts `options` AND `scope.values` are the
  SAME populated list (catches the `FieldScope(values=())` divergence). FAILS today.
- **NEW reference case** — `membership_type` field; asserts `options` is POPULATED from the
  injected active catalog (`_active_membership_type_options`) and that BOTH reads agree with each
  other AND with the current catalog (see the G3 carve-out below — NOT PUT==GET).

**Expected counterexamples:** enum reads back `[]`; scope `options` populated but
`FieldScope(values=())`; reference inline options empty with no catalog population — all three the
same disease (no populated `options` from the declared source, read split by kind).

### Fix Checking (per-kind invariant — the symmetry is NOT identical across kinds, G3)

The round-trip invariant differs by SOURCE location, so the Fix-Checking assertion is carved out
per kind. The common part is "both reads agree"; what each is compared AGAINST differs:

```
FOR ALL input WHERE isBugCondition(input) DO
  editor := configEditorRead(afterPut(input));  form := memberFormRead(input)
  ASSERT editor == form                                    // reads ALWAYS agree (P1)
  CASE declaredSource(input) OF
    inline  (enum):  ASSERT editor.options == normalize(input.options)   // strict PUT == GET
    scope:           ASSERT editor.options derived-from scope_vocab[input.key]
                     AND editor.scope.values == [o.value for o in editor.options]
    catalog (ref):   ASSERT editor.options == CURRENT active catalog for input.key
                     // NOT == what was PUT: the catalog lives elsewhere and changes
                     // independently of the field config; both reads agree with each
                     // other AND with the current catalog
END FOR
```

**Why the carve-out (G3):** a reference field's options come from the LIVE catalog, which can
change between PUT and GET independently of the field config — so asserting `options == what was
PUT` is literally false by design. Enum keeps strict inline PUT==GET (its source lives in the
row). Scope asserts `options` derived-from `scope_vocab` AND `scope.values == [o.value...]`. After
the fix, all three cases PASS through the one read path.

### Preservation Checking

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT read_original(input) == read_fixed(input)   // P2
END FOR
```
PBT recommended: generate already-resolving selectable fields + `application_choices` usage,
observe current output on UNFIXED code, assert unchanged after the fix. Confirm spec-03 isolation
and scope ACCESS resolution still hold.

### Fail-Loud Checking

```
// Fail-loud fires on the ASYMMETRY only: declared source PRESENT but options did not propagate.
FOR ALL fields F WHERE isSelectable(F)
                   AND declaredSourceExists(F)        // source is present/declared
                   AND assembledOptions(F) is empty DO // yet nothing propagated
  ASSERT read_fixed(F) raises a diagnosable, caller-safe error   // uniform across kinds
         AND read_fixed(F) != emptyVocabulary                    // P3
END FOR
// NOT in this set (must NOT raise — legitimate, G5):
//   - a scope dimension with ZERO values yet
//   - a newly-created not-yet-populated field (no declared source populated by design)
//   - a reference field whose catalog correctly populates options
```

### Strengthened Isolation Test (R2.5 — test-debt)

Strengthen spec-03's `test_set_enum_choices_on_field_is_isolated` from isolation-ONLY to:
1. **isolation** (unchanged — a vocabulary write does not clobber siblings), PLUS
2. **round-trip symmetry** — PUT == GET of the vocabulary via the editor read path, PLUS
3. **real stored shapes** — cover the bare-`choices` / `options`-absent legacy row (the shape
   whose isolation-only coverage let this bug pass 48 green E2E cases).

### Unit / Property-Based / Integration

- **Unit:** the read-assembly seam populates `options` from inline / injected catalog map /
  injected `scope_vocab` and raises ONLY on the asymmetry — a present-but-unpropagated source —
  while a legitimately-empty source does NOT raise (C4/C6/G5); the pure resolver is asserted to
  take NO catalog/DB dependency; `_build_override` / `_build_overlay_field` / `_build_options`
  surface one `options`, no split, raise on unexpected shape (C5/C6); `FieldScope.values` equals
  `[o.value for o in options]` derived at the seam (F7/G2); reference fills from the injected
  catalog map (F8); duplicate-`value` guard rejects (C3).
- **Property-based:** preservation over already-resolving selectable fields + `application_choices`;
  symmetry over generated vocabularies of each kind.
- **Integration / E2E:** the extended symmetry gate (enum + scope + reference, all through the one
  read path, with the G3 per-kind assertion) + the strengthened spec-03 isolation case,
  container-gated against local DynamoDB. The small C7 backfill verified read→migrate→read against
  the real h-dcn `referral_source` row (and idempotent on re-run).

## Requirements Traceability

| Requirement | Delivered by |
|---|---|
| R2.1 one canonical `options` end-to-end; retire `choices` | C1, C2, C4 (read-assembly seam), C5, C7 |
| R2.2 round-trip symmetry is the acceptance invariant | Symmetry gate (P1), Fix Checking (per-kind, G3) |
| R2.3 no silent fallbacks — fail loud on the asymmetry | C6 (G5 predicate), F1–F12 (F9/F10 serializer fallbacks, F12 write-side coalesce; F11 is a documented source-selector carve-out), Fail-Loud Checking (P3) |
| R2.4 write-edge duplicate-`value` 400 before repo call | C3 (P4) |
| R2.5 strengthen isolation test → + symmetry + real shapes | Strengthened Isolation Test |
| R2.6 one vocabulary model; kinds differ only in source; uniform fail-loud; scope `values` derived from `options` | Read-assembly seam C4 (resolver stays pure), C5/C6, F7, F8, F9 (`_serialize_field` collapse), F10 (`_public_field_options` fallback drop, R3.2 subset preserved), F11 (source-selector carve-out), scope collapse (G2), extended gate (P1, P3) |
| R2.7 mechanical guard fails the build on re-introduction of a retired path | C8 (extended `check_sam_config_crud.py` + planted-violation tests, report-only→blocking AFTER C1–C7, G6) |
| R3.1 already-resolving fields render identically | Preservation (P2) |
| R3.2 `application_choices` unchanged (separate subset) | Preservation (P2) |
| R3.3 spec-03 Change-Op guarantees preserved | C2 (Change-Op path, no whole-row replace) |
