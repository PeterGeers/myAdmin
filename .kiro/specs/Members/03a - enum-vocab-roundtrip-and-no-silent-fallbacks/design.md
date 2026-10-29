# Enum-Vocabulary Round-Trip & No-Silent-Fallbacks Bugfix Design

## Overview

A tenant selectable field's option vocabulary round-trips **asymmetrically**: it is written
under one attribute name (`choices`) and read from another (`options`), so it disappears from the
Members config editor on reload — intermittently — because a one-sided fallback hides the mismatch
on the member-form path but not on the editor path. The same two-names disease has a scope variant
(the field's `options` and `FieldScope.values` tracked in two places; only one survives).

Per the owner directive, this design does NOT special-case enum, reference, and scope-backed
fields. It unifies them on **ONE vocabulary model**: every selectable field resolves to ONE
canonical `options` list in the SAME shape `[{value, label?, roles?}]`, read by every consumer
with **no field-kind branching**. The kinds differ ONLY in the **source** that populates
`options` — inline (enum), live catalog (reference), or scope dimension (scope-backed). `choices`
is retired (legacy rows migrated), every silent fallback is removed, and "declares selectable but
resolves to no source" becomes a loud, uniform, caller-safe error. The mechanics of each
manifestation live in **Bug Details**; this section states only the shape of the fix.

### Definitions (G-numbers and R-numbers)

The `R2.x` / `R3.x` numbers below are the bugfix requirements in `bugfix.md` (Expected/Unchanged
Behavior clauses). The `G`-numbers are the recurring design guarantees this document relies on,
defined once here and referenced inline:

- **G2 — scope `values` is DERIVED, never a second copy.** `FieldScope.values` is the projection
  `[o.value for o in options]` computed at the single read-assembly seam, never an independently
  stored list (kills the `FieldScope(values=())` divergence by construction).
- **G3 — the Fix-Checking symmetry is carved out per kind.** "PUT == GET" is literal only for
  inline enum (source in the row); for reference the compare is against the CURRENT live catalog
  and for scope against `scope_vocab` — because those sources live elsewhere and change
  independently. All kinds still satisfy "both reads agree".
- **G5 — fail-loud fires on the ASYMMETRY only, never on a legitimately-empty source.** A declared
  source that is PRESENT but did not propagate into `options` raises; a source that is empty/absent
  by design (a scope dimension with zero values yet, a not-yet-populated new field, an empty active
  catalog on a new tenant) is a valid in-progress state and does NOT raise.
- **G4 — scope options carry a bare label.** Projecting a bare scope dimension value to a rich
  option yields `{value, label: {}}`; labels/roles are legitimately absent because scope display
  vocabulary is bare by nature (the dimension value is its own label). Not a defect.
- **G6 — the C8 mechanical guard flips to BLOCKING only after the tree is clean.** It runs
  report-only first; the blocking flip happens only after C7 + C1–C6 land and the baseline is
  green, so it never reddens a valid in-flight state on day one.

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
- **Write-edge invariant (the authoritative fail-loud contract)**: **a selectable inline-source
  (enum) field CANNOT be saved with zero `options`.** The write surface (C2/C3) rejects an
  inline-source selectable field whose canonical `options` is empty. With this invariant enforced
  at the write edge, "an inline-source enum resolves to EMPTY `options` on read" is ALWAYS the
  asymmetry — it could only have happened if the vocabulary failed to propagate (an un-migrated /
  bare-`choices` legacy row) — so it is the clean read-time discriminator for fail-loud. The
  `choices`-present-but-`options`-empty sentinel the current C6 code keys off is only the
  MIGRATION-WINDOW special case of this invariant (a legacy row written before the invariant
  existed); once C7 backfills, the write-edge invariant is the contract and the `choices` sentinel
  is obsolete.
- **`declaredSourceExists(field, src)`**: the concrete predicate that separates the asymmetry from
  a legitimately-empty source (G5). It is TRUE when the field's declared source is both present and
  capable of populating:
  - **inline enum**: the write-edge invariant holds, so a saved inline-source field with empty
    `options` means the source was PRESENT but did not propagate → `declaredSourceExists` is TRUE
    → raise. (During the migration window, an un-migrated row carrying bare `choices` with empty
    `options` is this same TRUE case.)
  - **reference**: the catalog fetch SUCCEEDED and returned ≥1 active type. A fetch ERROR is loud
    (the source is unreachable — raise), but an EMPTY RESULT (the fetch succeeded and the tenant
    simply has zero active types yet) is a legitimately-empty source → `declaredSourceExists` is
    FALSE → do NOT raise. The distinction is fetch-error-vs-empty-result, not just "options empty".
  - **scope-backed**: the dimension is PRESENT in the injected `scope_vocab` (the field's key is
    bound to an enabled dimension). A present dimension with zero values yet is legitimately-empty
    (`declaredSourceExists` FALSE — in-progress); a key NOT in `scope_vocab` is simply not
    scope-backed.

## Bug Details

### Bug Condition

The unified bug: a selectable field resolves to no populated `options` from its declared source
where it should have one, so the two read paths disagree. The harness surfaced three cases — **two
bugs and one by-design case** (harness evidence, live local DynamoDB — do not re-derive):

**Bug 1 — enum** bare-`choices` / `options`-absent → config editor reads `[]` (primary bug; RED
   gate `test_roundtrip_symmetry_choices_only_legacy_row`).
**Bug 2 — scope** field authored with inline options → `options`/`choices` round-trip, BUT
   `FieldScope(values=())` came back EMPTY: `options` and `scope.values` are tracked in TWO
   places and only one survived — a scope variant of the same two-names disease.

**By-design case (NOT a bug — the unified model handles it):**
**Reference** `membership_type` resolves with EMPTY inline options BECAUSE its vocabulary is
   the live catalog. Under the unified model the READ-ASSEMBLY seam populates `options` from the
   injected active-catalog map (`_active_membership_type_options`), so it is neither empty nor a
   fail-loud case. (The pure resolver never reads the catalog.)

**Formal Specification:**

The input domain of a selectable field splits into TWO DISJOINT sets by whether the declared
source CAN populate. P1 fixes the first; P3 fails-loud on the second. They never overlap:

```
FUNCTION isBugCondition(X)
  INPUT:  X = a selectable field (enum | reference | scope-backed)
  OUTPUT: boolean
  RETURN  isSelectable(X) AND ( inP1Set(X) OR inP3Set(X) )
END FUNCTION

// P1-set: the declared source CAN populate (a non-empty vocabulary exists at the source),
//         but today the two reads DISAGREE — the asymmetry that must be FIXED to non-empty.
FUNCTION inP1Set(X)
  RETURN  sourceCanPopulate(X)                           // source present AND holds >=1 value
          AND ( assembledOptions(X) is empty             //   editor read sees nothing (bug)
                OR configEditorRead(afterPut(X)) != memberFormRead(X)  // reads disagree
                OR (isScopeBacked(X) AND X.scope.values != [o.value for o in X.options]) )
END FUNCTION

// P3-set: the source is DECLARED but CANNOT populate (nothing to propagate) — the asymmetry
//         that must RAISE, never degrade. Keyed off the write-edge invariant.
FUNCTION inP3Set(X)
  RETURN  declaredSourceExists(X)        // source is DECLARED & reachable (write-edge invariant:
                                         //   inline-saved ⇒ was non-empty; ref fetch SUCCEEDED or ERRORED, not empty-result)
          AND assembledOptions(X) is empty   // yet no options propagated — the asymmetry
          AND NOT sourceCanPopulate(X)   // and the source holds no value NOW to have propagated
END FUNCTION
```

`sourceCanPopulate(X)` is TRUE when the declared source currently holds ≥1 value (inline options
present / catalog returned ≥1 active type / scope dimension has ≥1 value). `declaredSourceExists`
is the write-edge-invariant predicate from the Glossary (inline-source-with-empty-options is
structurally the asymmetry; reference distinguishes fetch-error from empty-result; scope requires
the dimension present). `assembledOptions` is populated at the ONE read-assembly seam;
`declaredSource(X)` selects inline / injected catalog map / injected `scope_vocab` — the only
per-kind input. The pure resolver reads no catalog/DB. No consumer branches on kind. A source that
is legitimately empty-by-design (NOT `declaredSourceExists`: an empty active catalog on a new
tenant, a scope dimension with zero values yet, a not-yet-populated new field) is in NEITHER set —
it is not the bug and does not raise (G5).

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

### Write-side vocabulary invariants (new guards)

Because the C1 editor now seeds from `options` IDENTICALLY for all kinds, the write edge must
stop a stale CATALOG snapshot from being re-frozen as inline `options`. These are WRITE-EDGE
rules enforced in C2 (the uncommitted C2 code must gain them):

1. **A REFERENCE field never persists `options`.** The write edge rejects an inline-`options`
   payload on a reference field. Rationale: a reference field's `options` are a snapshot of the
   LIVE catalog populated at the read seam (C4); if those get saved back as INLINE options on the
   next edit, we re-freeze a stale copy of the live catalog — the two-copies disease on the WRITE
   side. The source of truth for reference is the catalog; it is never persisted inline.
2. **W2 REMOVED (Option A) — a SCOPE-backed field is a NORMAL enum for authoring.** An earlier
   revision rejected an inline-`options` payload on a scope-backed field. That was wrong: the
   inline `options` payload is the ONLY authoring path (the editor round-trips the dimension's
   options back on save), so the rejection blocked the sole way to save the field (the live symptom
   `set_field: field 'region' is scope-backed — inline options rejected (W2)`). The write surface
   now ACCEPTS a scope-backed field's `options` (point 3 / W3 still applies to an explicit empty
   list). Its dropdown may ALSO be sourced from the `config#scope` dimension at READ time — the
   pre-existing S5j read path, UNCHANGED — and the dimension values are kept in sync with the
   field on the Flask authoring plane, so the two sources do not diverge.
3. **Selectable inline-source field cannot be saved with zero `options`** (the write-edge
   invariant, Glossary / point 1) — rejected with a caller-safe 400. This is what makes
   "inline-source enum reads back empty" ALWAYS the asymmetry, hence the clean fail-loud
   discriminator.
4. **Scope `asOptions` label handling.** Projecting a bare scope dimension value to a rich option
   yields `{value, label: {}}` — the bare value carries no per-value label or roles, so the `label`
   is an empty i18n map. This is ACCEPTABLE: scope display vocabulary is bare by nature (a
   dimension value is its own label), so dropping labels/roles on `asOptions(scope_vocab[key])` is
   the intended, lossless-for-scope handling, not a defect.

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

Property 1: Bug Condition — Source CAN Populate → Non-Empty Options, Both Reads Agree

_For any_ selectable field (enum, reference, or scope-backed) in the **P1-set** — where the
declared source CAN populate (`sourceCanPopulate(X)` is true: a non-empty vocabulary exists at the
inline overlay / live catalog / scope dimension) — the fixed system SHALL populate a NON-EMPTY
`options` from that source at the ONE read-assembly seam, and the config editor read and
member-form read SHALL both return the SAME `options` — with NO field-kind branching in any
consumer. For a scope-backed field, `FieldScope.values` SHALL be the DERIVED projection
`[o.value for o in options]` of that same `options` (one derivation point, never an independent
copy), so the two can never diverge. This property covers ONLY inputs whose source can populate;
the case where a declared source CANNOT populate is Property 3 — the two sets are disjoint.

**Validates: Requirements 2.1, 2.2, 2.6**

Property 2: Preservation — Already-Resolving & Separate-Concept Behavior

_For any_ input where the bug condition does NOT hold (a field already resolving to populated
`options`, a non-selectable field, `application_choices` usage, or scope ACCESS resolution), the
fixed system SHALL produce the same result as the original, preserving both reads, the
`application_choices` subset, scope access evaluation, and the spec-03 Change-Op guarantees.

**Validates: Requirements 3.1, 3.2, 3.3**

Property 3: Fail-Loud — Source Declared But CANNOT Populate Raises, Uniformly, Never Degrades

_For any_ field in the **P3-set** — where a selectable source is DECLARED and EXISTS
(`declaredSourceExists` true, by the write-edge invariant) but CANNOT populate so nothing
propagated into `options` (the asymmetry) — for ANY kind, no exemptions — the fixed read path
SHALL raise a LOUD, caller-safe, diagnosable error at the boundary and SHALL NOT silently fall
back, substitute an empty list, or coerce the shape. Because the write-edge invariant forbids
saving an inline-source enum with zero `options`, "an inline-source enum resolves to EMPTY
`options` on read" is ALWAYS this asymmetry (it could only arise from a vocabulary that failed to
propagate — an un-migrated / bare-`choices` legacy row). For reference, a fetch ERROR (source
unreachable) is this asymmetry and raises; a non-empty catalog that failed to attach is this case.

This set is DISJOINT from P1: P1 covers inputs whose source CAN populate (must resolve to non-empty
options, both reads agree); P3 covers inputs whose source is declared but CANNOT populate (must
raise). A source that is legitimately empty/absent-by-design is in NEITHER set and does NOT raise
(G5): an EMPTY active catalog on a new tenant (fetch succeeded, zero active types — an empty
RESULT, not a fetch error), a scope dimension with ZERO values yet, or a newly-created
not-yet-populated field (no declared source at all). A reference whose catalog correctly populates
`options` is P1, not this case.

**Validates: Requirements 2.3, 2.6**

Property 4: Write-Edge Duplicate-Value Rejection

_For any_ `options` payload containing a duplicate `value`, the write SHALL reject it with a
caller-safe 400 (steering 30; no `str(e)` leak) BEFORE any repository call.

**Validates: Requirements 2.4**

Property 5: Write-Edge Source Integrity — Reference Never Persists Options (W2 removed)

_For any_ write to a selectable field: (a) a REFERENCE field SHALL NOT persist an `options`
payload — the write edge rejects an inline-`options` payload on a reference field with a
caller-safe 400 (steering 30), so a stale catalog snapshot can never be re-frozen inline (no
two-copies disease on the write side); and (b) an inline-source (enum) field SHALL NOT be saved
with an EXPLICIT empty `options` list — the write edge rejects it with a caller-safe 400, which is
the write-edge invariant that makes "inline-source enum reads back empty" always the P3 asymmetry.
A SCOPE-backed field is NOT covered by (a): W2 was removed (Option A) — its inline `options` are
ACCEPTED by the write surface (that is the only authoring path), and its dropdown may ALSO be
sourced from the `config#scope` dimension at read time (the S5j read path, UNCHANGED).

**Validates: Requirements 2.4, 2.6**

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
    scope     -> asOptions(scopeVocab[field.key])    // scope-backed → {value, label:{}} (G4 label note)
    none      -> RETURN None                         // no declared source → legitimately sourceless (G5)
  // Fail-loud on the ASYMMETRY only (P3). The discriminator is the WRITE-EDGE INVARIANT:
  //   - inline: a saved inline-source enum CANNOT have empty options, so options-empty here means
  //             the vocabulary failed to propagate (un-migrated / bare-`choices` legacy row) → RAISE.
  //             (Migration window: a bare-`choices`-present row with empty options is this same case.)
  //   - catalog: a FETCH ERROR raises (source unreachable); an EMPTY RESULT (fetch ok, zero active
  //              types yet) is legitimately-empty → return the empty list, do NOT raise (G5).
  //   - scope: a dimension PRESENT in scopeVocab with zero values yet is legitimately-empty → do NOT raise.
  IF src = inline AND options is empty THEN
    RAISE loud caller-safe error (tenant + field key)   // uniform fail-loud (C6/G5), the asymmetry
  field.options := options            // canonical, same shape, all kinds
  IF isScopeBacked(field) THEN
    field.scope.values := [o.value for o in options]  // DERIVED projection, single point (G2)
  RETURN field
END FUNCTION
```

Every consumer (editor read, member-form read, symmetry gate, fail-loud) reads `field.options`
with NO kind branching. The write-edge invariant (an inline-source enum cannot be saved with zero
options) is what makes the inline `options is empty` check an unambiguous asymmetry signal; the
`choices`-present sentinel the current C6 code keys off is only the migration-window encoding of
this same case (a legacy row written before the invariant). A legitimately-empty source (empty
active catalog on a new tenant, scope dimension with no values yet, newly-created field) does NOT
raise (G5) — for reference the seam distinguishes a fetch ERROR (raise) from an empty RESULT
(return empty). The resolver is UNCHANGED in its purity; the only new code is this seam's uniform
population + the scope derivation. (G4: `asOptions` on a bare scope value yields `{value,
label:{}}` — labels/roles are legitimately absent for scope, see Write-side invariants §4.)

### Components (C1..C7)

**C1 — Frontend author/read `options` only, no kind branch** (`fieldConfigChangeOps.ts`,
`MembersFieldModal.tsx`). Remove `choices` from `DEFINITION_ATTRS` so the write emits ONLY
`options`. `MembersFieldModal.optionsToChoices` / `formFromResolvedField` seed the editor from the
single `options` the seam returns — IDENTICALLY for enum, reference, and scope (no reference/scope
special-case); C6 makes a propagated-but-empty source an error, not a silent empty. **Latent-bug
note:** because the editor now seeds from `options` identically for all kinds, a REFERENCE field's
catalog-derived `options` could be emitted back as inline `options` on the next save. C2's W1
write-side source-integrity guard (below) is what prevents that re-freeze for reference fields — the
read-side uniformity is safe for reference ONLY with the W1 guard in place. (A SCOPE-backed field
is intentionally NOT guarded this way — W2 was removed (Option A): saving its dimension-derived
`options` back inline is the sanctioned authoring round-trip, and its read-time dropdown may still
be dimension-sourced via the UNCHANGED S5j path, which keeps the two in sync.)

**C2 — Write surface accepts `options` only, with source-integrity guards**
(`config_fields_crud_service.py`). Remove `choices` from `FIELD_DEFINITION_ATTRS`. Storage key
stays `overrides`, served under wire key `fixed_overrides` (one-key contract preserved). Write
remains a Change-Op on a single path — no whole-row replace (R3.3). The C2 code carries
TWO write-side guards (Write-side invariants; Property 5) — W2 was REMOVED (Option A):
- **A REFERENCE field never persists `options` (W1).** Reject an inline-`options` payload on a
  REFERENCE field with a caller-safe 400 — a reference field's `options` are a live-catalog
  snapshot populated at the read seam (C4); persisting them inline re-freezes a stale copy (the
  two-copies disease on the write side). Reference vocabulary lives in the catalog, never inline.
- **W2 REMOVED (Option A) — a scope-backed field is a NORMAL enum for authoring.** An earlier
  revision rejected an inline-`options` payload on a scope-backed field, but that inline payload is
  the ONLY authoring path (the editor round-trips the dimension's options back on save), so the
  rejection blocked the sole way to save the field (live symptom `set_field: field 'region' is
  scope-backed — inline options rejected (W2)`). The write surface now ACCEPTS a scope-backed
  field's `options`; its dropdown may ALSO be sourced from the `config#scope` dimension at read
  time (the S5j read path, UNCHANGED). W3 still applies if saved with an explicit empty list.
- **Selectable inline-source field cannot be saved with zero `options` (W3).** An EXPLICIT empty
  `options` list is rejected with a caller-safe 400. This is what makes the read-time fail-loud
  discriminator (inline-source enum reads back empty ⇒ asymmetry) unambiguous. W3 applies to any
  enum, scope-backed or not.

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

**C6 — Fail-loud boundary, uniform across kinds, on the ASYMMETRY only, asymmetric by consumer**
(seam, G5). Fail-loud fires when a field's DECLARED source EXISTS but CANNOT populate so its
vocabulary did not propagate into `options` (P3): an un-migrated / bare-`choices` legacy row, an
inline-source enum that resolves to empty (impossible for a correctly-saved row under the write-edge
invariant — hence always the asymmetry), a reference whose catalog FETCH ERRORED, a non-empty
catalog that failed to attach. It does NOT fire for a source that is legitimately
empty/absent-by-design — a scope dimension with zero values yet, a newly-created not-yet-populated
field, an EMPTY active catalog on a new tenant (fetch succeeded, zero active types — an empty
RESULT, distinct from a fetch error) — which stay valid in-progress states. No per-kind exemption.
The discriminator is the write-edge invariant (Glossary / `declaredSourceExists`); the current C6
`choices`-present-but-`options`-empty check is the MIGRATION-WINDOW encoding of the same asymmetry,
retired once C7 backfills. Generic client message per steering 30; full detail logged server-side
under a correlation id.

**Blast-radius policy — DELIBERATE and asymmetric by CONSUMER.** `get_field_config` raising would
take down the whole config response, including the PUBLIC application form, for one bad field. So
the policy splits by consumer:
- **STAFF config-editor read**: FAIL THE FIELD LOUDLY — raise. The editor is exactly where a
  config bug must surface; a staff admin seeing the loud error is the intended signal.
- **PUBLIC application path**: FAIL THE ONE FIELD, not the whole page — DROP the offending field
  from the served config, and emit an error LOG + METRIC + ALERT (same correlation id as the
  server-side detail). One misconfigured field must never black out a tenant's public application
  form. The raise still happens at the seam; the public serializer CATCHES it per-field, drops
  that field, and records the alert, while the staff serializer lets it propagate.

**Hard gate before C6 goes live (Deployment ordering).** An all-tenant scan confirming ZERO
un-migrated bare-`choices` rows MUST pass before C6's fail-loud is enabled — not "essentially one
row" by assumption. A single missed un-migrated row would, under fail-loud, be an outage (staff
read raises; public read drops a real field). The scan is a precise read→count across every
tenant's `config#fields`, run as a blocking step in Deployment ordering, not an inference.

**C7 — Small targeted `choices`→`options` backfill (right-sized)** (migration script). Real usage
is LIMITED — essentially the one h-dcn `referral_source` row carries bare `choices`. So this is a
SMALL idempotent targeted backfill, NOT the spec-03 heavy version-guarded prod-copy machinery:
enumerate the few `config#fields` rows carrying bare `choices`, rewrite each to value-only
`options` (`[{value: v} for v in choices]`), drop `choices`. Idempotent (re-running is a no-op
once a row has `options` and no `choices`) and verified by a read→migrate→read check on the REAL
h-dcn row (the 6 `referral_source` values survive as `options`). A one-shot script — or even
manual-with-verification given the scale — is sufficient; NOT a flag-day, NOT a PITR-backed
prod-copy rehearsal. Run the backfill and verify; with one row there is no fix-forward fallback to
reason about. Must run BEFORE C6 fail-loud is enabled and C8 flips to BLOCKING, and the all-tenant
zero-un-migrated-rows scan (C6 hard gate) must confirm it, so no live bare-`choices` row trips
either guard.

**C8 — Mechanical anti-reintroduction guard** (`scripts/check_sam_config_crud.py` +
`sam/tests/test_check_sam_config_crud.py`, pre-commit + CI). Deletion alone is insufficient —
the old path must FAIL THE BUILD if re-added (spec 03 lesson). EXTEND the existing AST guard
(same mechanism: real code only, not comments/docstrings; allow-list discipline; never
`--no-verify`) with THREE blocking rules — **(a), (b), (d)** — which are mechanical and stable:
- **(a)** a `choices` key on the config#fields WRITE path;
- **(b)** an `options or choices` / `choices or options` fallback expression in reader/resolver OR
  a read of `field.choices` as a fallback vocabulary SOURCE in a serializer — this covers the
  `_serialize_field` fallback (F9), the `_public_field_options` fallback (F10), AND the write-side
  `_field_choice_values` coalesce (F12), which is why F12 is MIGRATED to `options`-only rather than
  allow-listed;
- **(d)** `FieldScope.values` populated independently of `options` (not as the derived projection).

Each of (a), (b), (d) gets a PLANTED-VIOLATION test (plant → guard fails; clean → passes).

**Rule (c) is DROPPED from the blocking guard.** The proposed per-field-KIND AST rule — "a
per-kind branch in a vocabulary CONSUMER where the uniform read-assembly `options` must be used" —
already needed TWO documented carve-outs (the R3.2 public-SUBSET FILTER in `_public_field_options`,
and the frontend source-selector `resolveChoiceSource` / F11). A rule that needs carve-outs to
avoid flagging legitimate code will false-positive and erode trust in the guard. So (c) is NOT a
blocking AST rule. Instead, the invariant it was meant to protect — "the serializers have NO
per-kind branch in the resulting `options` read shape" — is COVERED BY TESTS: a targeted
unit/integration test asserting `_serialize_field` and `_public_field_options` resolve the one
canonical `options` from the seam with no per-kind read-shape branch (the R3.2 subset filter and
the F11 source selector remain legitimate and are explicitly allowed by those tests). F11 stays a
documented no-change source-selector carve-out; F9/F10's per-kind branches are removed by C4 and
verified by these tests, not by a blocking AST rule.

**Rollout — TWO INCREMENTS.** The work splits into two increments so the guard never reddens an
in-flight state:
- **Increment 1 — the fix: C7 + C1–C6.** The backfill, the uniform read-assembly seam, the
  write-side guards, scope derivation, and fail-loud (with the C6 hard gate).
- **Increment 2 — the guard: C8.** The mechanical anti-reintroduction guard, rolled out
  REPORT-ONLY → clear baseline → BLOCKING. The flip to BLOCKING happens only AFTER increment 1 has
  landed and the gate is green (G6; see Deployment ordering). This is the enforcement layer that
  makes the increment-1 structural fixes un-regressable.

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
| F10 | `_public_field_options`: a per-field-KIND branch + reads `field.choices` as a fallback vocabulary source (`if field.choices is not None: ... list(application_subset_choices(field))`) on the SAM PUBLIC-form read serializer | `_membership_writes_fieldconfig.py` (`_public_field_options`, ≈342–390) | remove the `field.choices` fallback here (read the seam's ONE `options`), while PRESERVING the public-subset projection (the `application_choices` ⊆ `options` filter) — the subset FILTER is a legitimately different projection per R3.2 and stays; only the `choices` FALLBACK is retired. The per-kind read-shape branch is collapsed by C4 and verified by the targeted no-per-kind-branch TEST (C8 rule (c) is DROPPED as a blocking AST rule), not by a blocking guard |
| F11 | `resolveChoiceSource`: an explicit reference/scope/enum KIND branch in the frontend picker-SOURCE adapter | `applicationChoiceSource.ts` (`resolveChoiceSource`, ≈104–123) | **LEGITIMATE SOURCE-SELECTOR CARVE-OUT, not a removal.** Confirmed by reading the file: `resolveChoiceSource` ONLY selects the declared source (reference→live catalog, scope→own `options`, enum→own `options`) and normalizes it — it does NOT branch the consumer READ SHAPE of the resulting `options`. Choosing the declared SOURCE this way mirrors the SAM seam's `declaredSource` and is allowed. No code change. Because the C8 per-kind AST rule (c) is DROPPED (it needed this very carve-out plus the R3.2 one — a sign it would false-positive), there is no blocking guard to false-positive on this file; the "no per-kind read-shape branch in a consumer" invariant is covered by a targeted test instead |
| F12 | `_field_choice_values`: a write-side `_collect(spec.get("options")) or _collect(spec.get("choices"))` coalesce, used to validate an `application_choices` subset against the field's vocabulary | `config_write_service.py` (`_field_choice_values`, :542) | migrate to read `options` only (drop the `choices` fallback) now that C7 backfills every live row and C2 drops `choices` on the write — so the write-side validator reads the ONE canonical vocabulary. Prefer this migration over a C8 allow-list carve-out (the migration is clean: C7 guarantees `options` is present before C8 flips to BLOCKING) |

**New write-side source-integrity guards (additions, not removals — see Write-side invariants &
C2, Property 5).** Beyond retiring the fallbacks above, C2 ADDS two write-edge guards that did
not exist before: (W1) reject an inline-`options` payload on a REFERENCE field — a reference
field's `options` are a live-catalog snapshot populated at the read seam; persisting them inline
re-freezes a stale copy (the two-copies disease on the write side, a latent bug introduced by C1's
identical-seeding). (W3) reject a save of an inline-source enum with ZERO `options` (the write-edge
invariant that makes the read-time fail-loud discriminator unambiguous). Both reject with a
caller-safe 400 (steering 30).

**W2 was REMOVED (Option A).** An earlier revision of this design added a W2 guard that rejected
an inline-`options` payload on a SCOPE-backed field. That was wrong: for a scope-backed field the
inline `options` payload is the ONLY authoring path (the editor round-trips the dimension's options
back on save), so W2 rejected the sole way to save the field and surfaced as the live symptom
(`set_field: field 'region' is scope-backed — inline options rejected (W2)`). A scope-backed field
is therefore treated as a NORMAL enum by the write surface: its `options` are ACCEPTED (W3 still
applies if an inline enum is saved with an EXPLICIT empty `options`). Its dropdown may ALSO be
sourced from the `config#scope` dimension at READ time — the pre-existing S5j read path
(resolver carve-out + `_as_variable_field` `scope_vocab` sourcing + `_assemble_field_options`'s
scope branch), which is UNCHANGED. The dimension values are derived from / kept in sync with the
field on the Flask authoring plane, so the two sources do not diverge.

### Deployment ordering

**Increment 1 — the fix (C7 + C1–C6):**

1. **C7 backfill FIRST**, verified read→migrate→read against the real h-dcn row, so no live
   bare-`choices` row remains. (With one row there is no fix-forward alternative — run and verify.)
2. **Backend TOLERATES `choices` (accept-but-ignore) while the deploy skew clears.** The write
   surface must NOT reject `choices` until the C1 frontend that stops emitting it is deployed. The
   hard deploy order is: **backend tolerates `choices` → frontend stops emitting `choices` (C1
   deployed) → backend REJECTS `choices` (C2 rejection enabled).** The C2 `choices`-rejection MUST
   NOT ship ahead of the deployed C1 frontend, or any cached/older frontend still emitting
   `choices` fails.
3. **THEN the read-assembly seam, scope derivation, and write-side guards land (C4/C5 + C2/C3).**
4. **C6 fail-loud is enabled LAST in increment 1, behind a HARD GATE:** an all-tenant scan
   confirming ZERO un-migrated bare-`choices` rows must PASS before fail-loud goes live — a missed
   row is an outage (staff read raises; public read drops a real field). Enabling fail-loud before
   migration is verified complete would trip C6 on a not-yet-migrated row in production. The
   staff-raise / public-drop split (C6) bounds the blast radius but does not remove the gate.

**Increment 2 — the guard (C8):**

5. **C8 flips REPORT-ONLY → clear baseline → BLOCKING LAST** — only AFTER increment 1 has landed
   and the gate is green (G6). Flipping the blocking guard earlier would redden valid in-flight
   states (a half-authored field, a scope dimension not yet populated, an un-migrated row); the
   guard goes blocking once the tree is clean, never on day one (spec-03 discipline).

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

**Expected counterexamples:** the TWO bugs — enum reads back `[]`; scope `options` populated but
`FieldScope(values=())` — are the two-names disease (no populated `options` from the declared
source, read split by kind). The reference case is the BY-DESIGN case: on unfixed code its inline
options are empty with no catalog population, which the fix resolves at the seam (it was never a
fail-loud case).

### Fix Checking (per-kind invariant — the symmetry is NOT identical across kinds, G3)

The round-trip invariant differs by SOURCE location, so the Fix-Checking assertion is carved out
per kind. The common part is "both reads agree"; what each is compared AGAINST differs:

```
// P1-set ONLY: the declared source CAN populate (non-empty vocabulary exists). The P3-set
// (source declared but cannot populate) is checked in Fail-Loud Checking, not here.
FOR ALL input WHERE inP1Set(input) DO
  editor := configEditorRead(afterPut(input));  form := memberFormRead(input)
  ASSERT editor == form                                    // reads ALWAYS agree (P1)
  ASSERT editor.options is NON-EMPTY                        // source can populate ⇒ non-empty (P1)
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
// P3-set ONLY: declared source EXISTS (write-edge invariant) but CANNOT populate — the asymmetry.
FOR ALL fields F WHERE inP3Set(F) DO       // declaredSourceExists(F) AND options empty AND source cannot populate
  // STAFF read FAILS THE FIELD LOUDLY:
  ASSERT staffRead(F) raises a diagnosable, caller-safe error    // uniform across kinds (P3)
         AND staffRead(F) != emptyVocabulary
  // PUBLIC read FAILS THE ONE FIELD (bounded blast radius, C6):
  ASSERT publicConfig(F.tenant) DROPS F     // the one field removed, page still served
         AND an error log + metric + alert is emitted (same correlation id)
END FOR
// NOT in this set (must NOT raise — legitimate, G5):
//   - an EMPTY active catalog on a new tenant (fetch SUCCEEDED, zero active types — empty RESULT)
//   - a scope dimension with ZERO values yet
//   - a newly-created not-yet-populated field (no declared source populated by design)
//   - a reference field whose catalog correctly populates options (that is P1)
// A reference fetch ERROR (source unreachable), by contrast, IS in the P3-set and raises.
```

The read-time discriminator is the **write-edge invariant** (a saved inline-source enum cannot
carry empty `options`), so an inline-source enum reading back empty is UNAMBIGUOUSLY the asymmetry
— no need to guess "new field vs un-migrated row" from the data. The migration-window
`choices`-present sentinel is the legacy encoding of the same case, retired after C7.

### Strengthened Isolation Test (R2.5 — test-debt)

Strengthen spec-03's `test_set_enum_choices_on_field_is_isolated` from isolation-ONLY to:
1. **isolation** (unchanged — a vocabulary write does not clobber siblings), PLUS
2. **round-trip symmetry** — PUT == GET of the vocabulary via the editor read path, PLUS
3. **real stored shapes** — cover the bare-`choices` / `options`-absent legacy row (the shape
   whose isolation-only coverage let this bug pass 48 green E2E cases).

### Unit / Property-Based / Integration

- **Unit:** the read-assembly seam populates `options` from inline / injected catalog map /
  injected `scope_vocab` and raises ONLY on the asymmetry — a present-but-unpropagated source —
  while a legitimately-empty source does NOT raise (C4/C6/G5), AND a reference fetch ERROR raises
  whereas an empty RESULT (zero active types) does not; the pure resolver is asserted to take NO
  catalog/DB dependency; `_build_override` / `_build_overlay_field` / `_build_options` surface one
  `options`, no split, raise on unexpected shape (C5/C6); `FieldScope.values` equals
  `[o.value for o in options]` derived at the seam (F7/G2); reference fills from the injected
  catalog map (F8); duplicate-`value` guard rejects (C3).
- **Write-side guards (Property 5, C2):** the write edge REJECTS an inline-`options` payload on a
  reference field (no stale-catalog re-freeze, W1) with a caller-safe 400; and REJECTS a save of an
  inline-source enum with an EXPLICIT empty `options` (the write-edge invariant, W3) with a
  caller-safe 400. **W2 was REMOVED (Option A):** a scope-backed field's inline `options` are
  ACCEPTED (the only authoring path), its dropdown may ALSO be dimension-sourced at read time (the
  S5j read path, UNCHANGED).
- **No-per-kind-branch serializer test (covers dropped C8 rule (c)):** a targeted
  unit/integration test asserting `_serialize_field` (F9) and `_public_field_options` (F10)
  resolve the ONE canonical `options` from the seam with NO per-kind read-shape branch — the R3.2
  public-subset FILTER and the F11 source-selector remain legitimate and are explicitly allowed.
  This is the test-based replacement for the dropped blocking AST rule (c).
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
| R2.3 no silent fallbacks — fail loud on the asymmetry (write-edge discriminator; staff-raise / public-drop split) | C6 (write-edge-invariant discriminator, per-consumer blast-radius split, hard gate), F1–F12 (F9/F10 serializer fallbacks, F12 write-side coalesce; F11 is a documented source-selector carve-out), Fail-Loud Checking (P3) |
| R2.4 write-edge duplicate-`value` 400 before repo call; source-integrity guards | C3 (P4), C2 write-side guards (P5) |
| R2.5 strengthen isolation test → + symmetry + real shapes | Strengthened Isolation Test |
| R2.6 one vocabulary model; kinds differ only in source; uniform fail-loud; scope `values` derived from `options`; only inline-source fields persist `options` | Read-assembly seam C4 (resolver stays pure), C5/C6, write-side source-integrity guards C2 (P5, W1 no stale-catalog re-freeze; W2 REMOVED — scope inline options accepted, dimension-sourced at read via the UNCHANGED S5j path), F7, F8, F9 (`_serialize_field` collapse), F10 (`_public_field_options` fallback drop, R3.2 subset preserved), F11 (source-selector carve-out), scope collapse (G2/G4), extended gate (P1, P3) |
| R2.7 mechanical guard fails the build on re-introduction of a retired path | C8 — increment 2 (extended `check_sam_config_crud.py` rules (a)(b)(d) + planted-violation tests; rule (c) DROPPED and covered by a no-per-kind-branch test instead; report-only→blocking AFTER increment 1, G6) |
| R3.1 already-resolving fields render identically | Preservation (P2) |
| R3.2 `application_choices` unchanged (separate subset) | Preservation (P2) |
| R3.3 spec-03 Change-Op guarantees preserved | C2 (Change-Op path, no whole-row replace) |
