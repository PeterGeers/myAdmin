# Requirements Document

## Introduction

Implements parent-spec **R6 — "Print address labels from a result"** as a `labels/` sub-spec of
`.kiro/specs/Members/pivot-output-actions` (mirrors the `mail/` sub-spec). A member-admin defines a
reusable LABEL TEMPLATE (ordered lines of pivot-result fields), then generates Avery labels from a
pivot result and downloads/prints the PDF. The label template is stored like the mail templates
(the `template#` store) and IS the label content definition — there is NO use of `analytics.config`
(that area is parked, bugs-to-solve #6/#7/#8). Avery placement is a resize concern (cell height ÷
lines + truncation), not an auto-fit guarantee. Emailing the PDF is deferred. Grounding:
`analysis.md`.

## Glossary

- **Label template** — a stored template of `kind="label"`: an ordered list of lines, each line a
  list of pivot-result field keys. No hard line limit.
- **Avery format** — a predefined physical sheet geometry (`AVERY_LABEL_FORMATS`); user picks one.
- **Compose** — turning a result row + a label template into the per-label text lines.
- **Pivot result** — the current (post-filter) result rows the action operates on.

## Requirements

### Requirement 1: Label template (lines of pivot fields), stored like a mail template
**User Story:** As a member-admin, I want to define a reusable label template so a pivot result can
be printed as Avery labels with my chosen content.
#### Acceptance Criteria
1. WHEN I define a label template THEN it SHALL be an ordered list of lines, each line one or more
   field keys from the pivot result (e.g. `[postal_code, city]`), with NO hard limit on lines.
2. WHEN a label template is saved THEN it SHALL persist in the existing `template#` store with a
   `kind="label"` discriminator (distinct from the mail HTML-body kind), tenant-pinned.
3. WHEN label and mail templates coexist THEN the picker/editor SHALL distinguish them by `kind`.

### Requirement 2: "Generate address labels" action on a pivot result
**User Story:** As a member-admin, I want a labels action beside CSV / Mail on a pivot result.
#### Acceptance Criteria
1. WHEN I may export (`members:export`) AND at least one label template exists THEN the "Generate
   address labels" action SHALL be available in the result-actions slot.
2. WHEN either condition is false THEN the action SHALL be hidden with a bilingual reason.
3. WHEN I generate labels THEN it SHALL operate on the CURRENT (post-filter) result rows.

### Requirement 3: Compose + Avery placement (resize, not magic)
**User Story:** As a member-admin, I want my template's lines placed onto the chosen Avery sheet.
#### Acceptance Criteria
1. WHEN I pick a label template + an Avery format THEN each template line SHALL render as one label
   line, multi-field lines joining their values with a space in field order.
2. WHEN laying out THEN the Avery cell height SHALL be divided by the number of template lines for
   the row height (reusing `generateAddressLabelPdf`), NOT reimplemented.
3. WHEN a field's text is extreme THEN it SHALL be truncated to the cell inner width (no overflow
   past the label box); readability of a badly-designed template is the designer's responsibility.

### Requirement 4: Output: download / print now; email deferred
**User Story:** As a member-admin, I want to download/print the generated label PDF.
#### Acceptance Criteria
1. WHEN I generate labels THEN the jsPDF SHALL be downloadable and/or printable (both already exist).
2. Emailing the label PDF (`doc.output('arraybuffer')` → SAM send) SHALL be OUT OF SCOPE here.

### Requirement 5: Shared label-options model
**User Story:** As a developer, I want one shared label-options model so interactive labels and the R3 delivery do not diverge.
#### Acceptance Criteria
1. WHEN label options are used THEN there SHALL be ONE `LabelStyleOptions` model (Avery format,
   font size, alignment, border, sort, start position, country toggle) shared with R3's
   `to_fixed` + labels delivery — not a forked second shape.

### Requirement 6: No analytics config
**User Story:** As a maintainer, I want the label path to never touch analytics.config so the parked redesign is not entangled.
#### Acceptance Criteria
1. The label path SHALL NOT read or write any `analytics.*` config; label content comes only from
   the stored label template + the already-defined pivot/result fields.
