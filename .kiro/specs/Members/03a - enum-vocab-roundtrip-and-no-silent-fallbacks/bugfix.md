# Bugfix Requirements Document

## Introduction

A tenant-authored **enum** field's choice vocabulary **disappears from the Members config
editor after reload** — intermittently. The values are sent in the PUT payload and are
physically stored, yet on reload the editor's choice list is empty. This is the concrete,
user-reported "lousy / unpredictable dynamic-field management": sometimes the choices come
back, sometimes they vanish.

Follow-on to `Members/03 - config-fields-foolproof-crud` (which made config#fields WRITES
isolated/non-truncating). 03a fixes the **enum-vocabulary ROUND-TRIP** across the full
lifecycle and removes the **silent fallbacks** that hide the failure.

Confirmed end-to-end against REAL data (the live `h-dcn` `config#fields` row in
`test_governance_projection`) and the live local-DynamoDB E2E harness (`sam/tests/e2e/`).

### Root cause (evidence-backed — not inferred)

One enum vocabulary is addressed by **two attribute names** that mean the same thing:

- `options` — rich `[{value, label?, roles?}]`.
- `choices` — bare value list `["bigtwin", ...]`. The SAME vocabulary in a lesser shape;
  redundant (an option carries its value). Legacy.

The real `h-dcn` `referral_source` row is stored as `choices: ["bigtwin","internet",...]`
with **`options: None`**. The paths disagree on which name is authoritative, and a
**fallback hides it on one path but not the other**:

- **Write** (`fieldConfigChangeOps.ts` → `definitionAttrs`): emits whichever of
  `choices` / `options` the working overlay happened to carry — possibly BOTH, possibly only
  `choices`. Non-deterministic by input shape.
- **Resolve** (`FieldResolver._as_variable_field` via `_build_overlay_field`): builds
  `options` ONLY from a stored `options` key. A `choices`-only row resolves to
  `options = None` — the `choices`→`options` promotion that `_build_override` (the FIXED
  path) has is MISSING on the VARIABLE-field path.
- **Config editor read** (`MembersFieldModal.optionsToChoices`): seeds the choice editor
  from `options` ONLY ("NOT choices"). So `options = None` → **empty editor**.
- **Member form read**: has an `options or choices` FALLBACK, so the SAME data renders fine
  there — which is exactly why the failure is intermittent and hidden.

So: write under one name, read from the other; one consumer has a fallback, the other does
not. Whether the UI shows the choices depends solely on which name the value landed under →
"sometimes works, sometimes not."

### Principle for the fix (owner directive)

**One vocabulary model; fail loud, never fall back.** Reference and scope fields SHALL reuse
AS MUCH AS POSSIBLE THE SAME LOGIC AS ENUMS — NOT separate code paths or fail-loud exemptions.
Every selectable field resolves to ONE canonical `options` list in ONE shape; the kinds differ
ONLY in the SOURCE that populates it (inline / live catalog / scope dimension). Silent fallbacks
convert a bug into stored-bad-data that detonates later elsewhere (this very bug). The fix
REMOVES the hiding fallbacks and makes "declares selectable but resolves to no source" a LOUD,
diagnosable error — for ANY kind.

**Generalized symmetry invariant (name the tension honestly).** The round-trip invariant is NOT
identical across kinds and the design SHALL say so:
- **enum** — strict PUT == GET of the INLINE vocabulary (the source lives in the row).
- **reference / scope** — NOT "stored inline == read": the source (live catalog / scope
  dimension) lives ELSEWHERE and can legitimately change between PUT and GET. The generalized
  invariant is: a selectable field ALWAYS resolves to a POPULATED `options` from its DECLARED
  SOURCE, and the config editor and member form ALWAYS see the SAME `options`. Fail-loud fires
  when a field declares it is selectable but resolves to NO source at all (the real bug) — for
  ANY kind, no exemptions.

### Scope

- **In scope:** the config#fields enum-vocabulary round trip on the SAM plane — write op,
  stored shape, resolve, and BOTH read paths (config editor + member form). Collapse to ONE
  canonical attribute (`options`); retire `choices` (migrate legacy `choices`→`options`).
- **Out of scope (separate finding, do NOT solve here):** the Flask/MySQL `user_tenant_scope`
  write bug ("added ~10 region scope items → stored 3 → then 0") — a different plane
  ("user scope" ≠ "config scope").
- Do NOT remove Flask `field_overlay` / projection builders: all config#* rows are
  SAM-authored (spec 02); that retired-but-kept code is a separate spec-02 cleanup.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a tenant enum field's vocabulary is stored under `choices` (bare values, `options`
absent) THEN `FieldResolver` resolves `options = None` (the variable-field read path does NOT
promote `choices`→`options`), so the served field carries no `options`.

1.2 WHEN the config editor reloads such a field THEN it seeds its choice editor from `options`
ONLY and shows an EMPTY vocabulary — the authored choices disappear from the UI though they
are in storage.

1.3 WHEN the SAME field is read by the member-form path THEN its `options or choices` FALLBACK
renders the choices correctly — so the failure is INTERMITTENT and HIDDEN (two read paths,
only one with a fallback).

1.4 WHEN a field is authored THEN the write op may emit the vocabulary under `choices`,
`options`, or BOTH (which can disagree), and the write performs no content validation (a
duplicate `value` is stored verbatim).

### Expected Behavior (Correct)

2.1 WHEN an enum field's vocabulary is authored THEN the system SHALL use ONE canonical
attribute (`options`) end-to-end — written, stored, resolved, and read by BOTH the config
editor and the member form from the SAME attribute. `choices` SHALL be retired (legacy rows
migrated `choices`→value-only `options`).

2.2 WHEN a field is PUT and then GET (via the config editor's own read path) THEN the
returned vocabulary SHALL be IDENTICAL to what was sent — input == output (round-trip
symmetry). This is the primary acceptance test.

2.3 WHEN a stored row carries a shape/name the read path does not expect (e.g. an
un-migrated `choices`-only row after retirement, or a `null`/malformed vocabulary) THEN the
system SHALL surface a LOUD, diagnosable error at the boundary — it SHALL NOT silently fall
back, substitute an empty list, or paper over the mismatch. Fail loud, never hide.

2.4 WHEN a field's `options` contains a duplicate `value` THEN the write SHALL reject it with
a caller-safe 400 (steering 30; no `str(e)` leak) BEFORE any repository call.

2.5 WHEN the test suite guards config#fields enum behaviour THEN the existing E2E case
`test_set_enum_choices_on_field_is_isolated` (spec 03) SHALL be STRENGTHENED from an
ISOLATION-only assertion (a choices write did not clobber siblings) to ALSO assert ROUND-TRIP
SYMMETRY (PUT == GET of the vocabulary) AND cover the real stored shapes — including the bare
`choices` / `options`-absent legacy row. The existing isolation-only test passed while the
real round-trip was broken; that false-confidence gap SHALL be closed so this class of bug
cannot pass the gate again.

2.6 WHEN any SELECTABLE field is resolved and read (enum, reference, or scope-backed) THEN all
three SHALL share ONE canonical `options` vocabulary in the SAME shape `[{value, label?, roles?}]`
and ONE resolve/read path. They SHALL differ ONLY in the SOURCE that populates `options`: enum
from inline authored/stored `options`; reference (e.g. `membership_type`) from the LIVE CATALOG
(`listMembershipTypes` / `catalogChoices`); scope-backed from the scope dimension values
(`scope_vocab` / `config#scope`). No consumer — config editor read, member-form read, PUT==GET
symmetry gate, or fail-loud rule — SHALL branch on field kind. Fail-loud SHALL apply UNIFORMLY
across kinds with no exemptions: a field that DECLARES it is selectable but resolves to NO source
is an error. For a scope-backed field, `FieldScope.values` and the field's `options` SHALL be the
SAME single list, not two copies that can diverge.

2.7 WHEN a future change re-introduces a retired old path or pattern THEN a MECHANICAL guard
SHALL FAIL THE BUILD — deletion alone is insufficient (spec 03's lesson: "a test that is not
gated is how the original regression reached main"). The existing AST guard
`scripts/check_sam_config_crud.py` (pre-commit + CI, allow-list discipline, planted-violation
test) SHALL be EXTENDED to reject, as real code (not comments/docstrings): (a) a `choices` key
written to the config#fields write path; (b) an `options or choices` / `choices or options`
fallback expression in the reader/resolver; (c) a per-field-KIND branch in a vocabulary consumer
(reference/scope special-casing where the unified `resolveSelectableOptions` seam must be used);
and (d) `FieldScope.values` populated independently of the field's `options`. Each rule SHALL
carry a planted-violation test (plant the pattern → guard fails; clean tree → passes) and SHALL
be rolled out REPORT-ONLY first, baseline cleared, then flipped to BLOCKING — never reddening
every branch on day one. A new sanctioned site is a REVIEWED allow-list addition, never a
`--no-verify` suppression.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a field already round-trips correctly today (authored + stored under `options`) THEN
it SHALL CONTINUE TO render identically in both the editor and the member form.

3.2 WHEN `application_choices` (the separate public-form SUBSET) is used THEN it SHALL remain
unchanged — it is a different concept from the field vocabulary and is not retired.

3.3 WHEN config#fields is WRITTEN THEN the spec-03 Change-Op guarantees (isolated,
non-truncating, server-owned placement, no whole-record replace) SHALL be preserved.

### Bug Condition and Properties

**Bug Condition** — the round-trip is asymmetric for a vocabulary stored under the
non-read attribute:

```pascal
FUNCTION isBugCondition(X)
  INPUT:  X = an enum field authored with a choice vocabulary V
  OUTPUT: boolean
  RETURN  configEditorRead(afterPut(X)) != V      // GET != PUT
          OR storedUnderName(X) != readName(X)     // write name != read name
END FUNCTION
```

**Property — round-trip symmetry (primary):**

```pascal
// Fix Checking
FOR ALL X DO
  ASSERT configEditorRead(afterPut(X)) == normalize(X.vocabulary)
END FOR
```

**Property — fail loud, no silent fallback:**

```pascal
// A mismatched/unexpected stored shape must ERROR, not degrade to empty.
FOR ALL rows R WHERE shape(R) is unexpected DO
  ASSERT read(R) raises a diagnosable error
         AND NOT read(R) == emptyVocabulary   // never the silent-empty fallback
END FOR
```

**Preservation:**

```pascal
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT read(X) == read'(X)
END FOR
```

### First task (harness-first, observation)

The FIRST task writes the **PUT→GET symmetry test** over the config editor's own read path
(input == output) and runs it on UNFIXED code against the live local-DynamoDB harness — it
MUST fail for a `choices`-stored field today, proving the asymmetry. Then catalogue every
enum-vocabulary fallback (`_build_override`'s `options or choices`, the member-form fallback,
`optionsToChoices` empty-on-absent, any `_as_variable_field` default) so the fix can replace
each hiding fallback with the canonical single path + a loud error.

The harness work has two parts: (a) the NEW symmetry gate
`sam/tests/e2e/test_enum_vocab_roundtrip_e2e.py` (already RED on the bare-`choices` case,
GREEN on options-authored) is the primary acceptance test; and (b) STRENGTHEN the existing
`test_set_enum_choices_on_field_is_isolated` (spec 03) from isolation-only to isolation +
round-trip-symmetry + the bare-`choices`/`options`-absent shape (R2.5) — that test's
isolation-only scope is exactly why 48 green E2E cases missed this bug.
