# Implementation Plan: Address labels from a pivot result (R6)

## Overview

> **Scope note:** a SUBTASK of `.kiro/specs/Members/pivot-output-actions` implementing R6.
> Frontend-only (jsPDF client-side). NO `analytics.config` (parked). Reuse the existing Avery
> generator. Output = download/print; emailing the PDF is DEFERRED. Grounding: `analysis.md`,
> `requirements.md`, `design.md`.
>
> Marker meaning: `[x]` = done + unit-tested; a task is only verified-working once driven in the
> browser against TEST (local dev frontend), per the parent spec's honest-status rule.

## Tasks

### Phase 0 — Label-template model (lines of fields) in the existing store
- [x] 0.1 Add a `kind: "label"` label-template shape to the template model/types + the
  `memberTemplateService` DTO: `{ template_id, name, kind:"label", lines: string[][] }`. Mail
  templates keep their existing kind. **[R-L1]**
- [x] 0.2 Persist/read label templates through the EXISTING `template#` store (same CRUD the mail
  templates use), tenant-pinned; the list/get carry `kind` + `lines`. **[R-L1]**

### Phase 1 — Compose lines from the template (no analytics.config)
- [x] 1.1 `composeLabelLines(rows, fieldConfig, template)` in `addressLabelService.ts`: per row,
  per `template.lines[i]`, resolve each field key via `valueFor` and join non-empty values with a
  space → the `{ lines: string[] }` the generator consumes. Pure; takes NO `analytics`. **[R-L3, P1/P2/P4]**
- [x] 1.2 Add per-line truncation to the cell inner width in the layout (measure via
  `doc.getTextWidth`; cut + ellipsis) so a long field never overflows the Avery box. **[R-L3, P5]**
- [x] 1.3 OPTIONAL per-sheet shrink-to-fit: compute the largest font (≤ the user's chosen size)
  at which EVERY label fits (all lines ≤ cell inner width; line block ≤ cell inner height) and
  apply that one uniform size across the sheet. Only shrinks, never grows. Wrap stays DEFERRED.
  **[R-L3, P6]**
- **Testing (P1):** vitest — N lines → N label lines; multi-field join order; empty values dropped;
  truncation; composer never reads `analytics`.

### Phase 2 — Label-template editor (same "templates" home)
- [x] 2.1 A small editor (in/beside `MemberTemplateManager`, filtered to `kind:"label"`) to define
  the ordered lines, each line selecting 1+ field keys from the result's available fields; create/
  edit/delete via the existing template CRUD. **[R-L1; steering 32]**
- **Testing (P2):** vitest — the editor builds a `{kind:"label", lines}` record; round-trips.

### Phase 3 — Wire the "Generate address labels" action
- [x] 3.1 Change the labels action gate to `members:export AND ≥1 label template exists`
  (drop the `hasAddressMapping`/`resolveAddressMapping` dependency FOR THE ACTION). **[R-L2, P3]**
- [x] 3.2 The labels modal: pick a LABEL template + an Avery format; compose via
  `composeLabelLines`; `generateAddressLabelPdf` lays it out; download the PDF (and/or print).
  Reuse the ONE `LabelStyleOptions` model (R-L5). **[R-L2/R-L3/R-L4]**
- **Testing (P3):** vitest — action hidden when no label template / no export; shown when both;
  generating downloads a PDF built from the chosen template's lines.

### Phase 4 — Verify end-to-end (browser, local dev vs TEST backend)
- [~] 4.1 As webmaster@h-dcn.nl on the local dev frontend (VITE_APP_ENV=test): create a label
  template (e.g. name / street / postcode+city / country), run a pivot, Generate address labels →
  pick an Avery format → the downloaded PDF shows the template's lines, placed in the Avery grid.
  Only flip 3.1/3.2 to `[x]` after this is observed.

## Notes
- Parent spec: `.kiro/specs/Members/pivot-output-actions` (R6).
- Deferred: emailing the label PDF (`doc.output('arraybuffer')` → SAM send).
- Out of scope: `analytics.config` / `address_mapping` (parked Track 3, bugs-to-solve #6/#7/#8).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2"] },
    { "id": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["3.1", "3.2"] },
    { "id": 4, "tasks": ["4.1"] }
  ]
}
```

**Ordering notes:**
- Phase 0 (model+store) → Phase 1 (compose from the model).
- Phase 2 (editor) needs the Phase-0 model to create records.
- Phase 3 (action) needs Phase 1 (compose) + Phase 2 (a template to pick).
- Phase 4 (browser verify) depends on 0–3; flip 3.x to `[x]` only after it passes.
