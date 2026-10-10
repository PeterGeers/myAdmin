# Design Document

## Overview

R6 "Print address labels from a result" as a frontend-only feature (jsPDF is client-side). A
LABEL TEMPLATE (ordered lines of pivot-result field keys) is stored in the existing `template#`
store with `kind="label"`. The "Generate address labels" action composes the current result rows
through the chosen label template and reuses the existing `generateAddressLabelPdf` to lay the
lines onto a user-picked Avery format; the PDF is downloaded/printed. NO `analytics.config` is
read or written. Grounding: `analysis.md`, `requirements.md`.

## Architecture

```
Pivot result (current rows) ─┐
Label template (kind=label)  ├─▶ composeLabelLines() ─▶ { lines: string[] } per row
Avery format (predefined)    ┘                           │
                                                          ▼
                               generateAddressLabelPdf(rows→lines, format, options)
                                   (existing jsPDF A4 grid; height ÷ lines; truncate)
                                                          │
                                                          ▼
                                        doc.save() download / doc.output('bloburl') print
```
- Reuses: `addressLabelService.ts` (Avery formats + generator + `LabelStyleOptions`), the
  `template#` store + `memberTemplateService` client + `MemberTemplateManager`, the pivot
  result-actions slot in `MemberPivotViews.tsx`, and the shared `valueFor` row accessor.
- Plane: entirely frontend; no SAM/worker change for download (email is deferred).

## Components and Interfaces

### THERE (reuse unchanged)
- `AVERY_LABEL_FORMATS`, `getLabelFormat`, `generateAddressLabelPdf`, `LabelStyleOptions`,
  `LabelFormat` in `addressLabelService.ts`.
- The template store CRUD (`memberTemplateService`) + `MemberTemplateManager`.

### ADD
- `composeLabelLines(rows, fieldConfig, template)` — pure; per row, per `template.lines[i]`,
  resolve each field key via `valueFor` and join non-empty values with a space → `{ lines }`.
  Takes NO `analytics`.
- Label-template editor (filtered `kind="label"` view in/beside `MemberTemplateManager`): ordered
  lines, each line selecting 1+ field keys from the result's available fields.
- `hasLabelTemplate` predicate (≥1 `kind="label"` template exists).

### CHANGE
- Labels action gate: FROM `canExport && hasAddressMapping` TO `canExport && hasLabelTemplate`.
- Labels modal composes via `composeLabelLines` (not `composeAddresses`/`resolveAddressMapping`).
- Add per-line truncation to the cell inner width (`doc.getTextWidth` + cut/ellipsis).
- Add an OPTIONAL per-sheet shrink-to-fit: pick the largest font (≤ the user's chosen size) at
  which every label fits width + height; one uniform size across the sheet. Wrap is DEFERRED.

### LEAVE
- Keep `composeAddresses`/`resolveAddressMapping` (R3 `to_fixed` labels may still use them); the
  ACTION simply stops depending on them. Do NOT touch `analytics.*`.

## Data Models

Label template record (same `template#` partition as mail templates):
```
template#<id>
{
  template_id, tenant_id, name,
  kind: "label",
  lines: [ ["display_name"], ["street"], ["postal_code","city"], ["country"] ],
  created_by, created_at, updated_at
}
```
- `kind` discriminates label vs mail. `lines` is the whole content model: N lines, each a list of
  field keys, no cap. Multi-key line → space-joined values.

## Correctness Properties

### Property 1: N lines yields N label lines
A label template with N lines yields a PDF whose each label has N text lines, in order.

**Validates: Requirements 3.1**

### Property 2: multi-field line join
A multi-field line joins its field values (space-separated) in the template's field order.

**Validates: Requirements 3.1**

### Property 3: gated action
The labels action is hidden unless `canExport && hasLabelTemplate`.

**Validates: Requirements 2.1, 2.2**

### Property 4: no analytics config
The label path never reads `analytics.*` (the composer takes only rows / fieldConfig / template).

**Validates: Requirements 6.1**

### Property 5: truncation (no overflow)
Over-long field text is truncated to the cell inner width — never drawn past the label box.

**Validates: Requirements 3.3**

### Property 6: shrink-to-fit (per-sheet)
When auto-fit is on, the chosen font is the LARGEST size at which EVERY label on the sheet fits
(all lines within the cell width and the line block within the cell height) — one uniform size
across the sheet; it only shrinks, never grows beyond the user's chosen size.

**Validates: Requirements 3.2, 3.3**

## Error Handling
- No label template / no export → action hidden with a bilingual degradation reason (not an error).
- A row with all-empty fields for every line → produces no usable label (dropped/counted), never a
  crash. A field key not present in the result resolves empty (dropped from its line).
- PDF generation errors surface a toast; the composed result is not lost.

## Testing Strategy
- vitest for `composeLabelLines` (P1/P2/P4), truncation (P5), the gate (P3), and the editor
  round-trip. No SAM/worker tests (frontend-only). Change-with-tests per steering 30/33.
