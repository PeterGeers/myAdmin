# Labels sub-spec — analysis (findings + decided direction)

> A **SUBTASK of the parent spec** `.kiro/specs/Members/pivot-output-actions`, implementing
> **R6 — "Print address labels from a result"**. Mirrors the `mail/` sub-spec in shape. Not
> independently shippable; its prod promotion rides the parent spec's `test → main` promotion.

## What R6 asks (verbatim intent)
Generate/print Avery labels straight from a pivot result (not only as a mail attachment):
a "Generate address labels" action beside CSV / Mail; reuse the existing label generator; let
the user pick the Avery format; available when the user may export AND a label layout exists;
share one label-options model with R3's `to_fixed` + labels delivery.

## Findings (grounded in current code)
- **PDF generator EXISTS and works** — `frontend/src/components/members/analytics/addressLabelService.ts`:
  `generateAddressLabelPdf(rows, fieldConfig, format, options)` builds a real **jsPDF** A4 doc,
  lays composed lines onto an Avery grid, and returns the doc. Caller chooses `doc.save()`
  (download), `doc.output('bloburl')` (print/preview), or `doc.output('arraybuffer')` (attach to
  mail). **Download + print exist; mail-attach does not (deferred).**
- **Avery formats are PREDEFINED, not stored** — `AVERY_LABEL_FORMATS` (5 formats: L7160/L7163/
  L7162/L7161/CUSTOM_LARGE) is a hardcoded constant (mm geometry). The user PICKS one at
  generate time. This is the physical sheet; it is not per-tenant config.
- **Current line CONTENT source (to be REPLACED for R6):** `composeAddresses` builds fixed
  address lines (name / street / "postcode city" / country / region) from a fixed-slot mapping.
  That fixed-slot approach is NOT what R6 will use (see the decision below).
- **The labels action is GATED today** on a resolvable address mapping + `members:export`
  (`canGenerateLabels` in `MemberPivotViews.tsx`). h-dcn has no such mapping, so the action is
  hidden. R6's label template REPLACES that gating condition (a label template existing is what
  makes the action available).

## Decided direction (user, this session — explicit)
1. **A LABEL TEMPLATE is a normal template** — user-defined **lines**; each line = one or more
   pivot-result field keys (e.g. a "postcode + city" two-field line). **No hard line limit** —
   however many lines the user defines are the lines on the label.
2. **Stored in the EXISTING template store** (the `template#` records built for mail), with a
   `kind` discriminator so a LABEL template (lines-of-fields) and a MAIL template (HTML body)
   coexist in one store but the editor/picker tell them apart. It is a template built on a
   pivot result — same domain as the mail templates.
3. **Fields are the already-defined pivot/result fields.** There is NO use of the analytics
   config (`analytics.*`) at all — that area is PARKED (bugs-to-solve #6/#7/#8) and explicitly
   out of scope here.
4. **Putting the virtual label onto a physical Avery label = a RESIZE issue, not clever
   software.** Divide the cell HEIGHT by the number of template lines → row height. Truncate
   extreme field text per line. If the result is unreadable, that is the TEMPLATE DESIGNER's
   problem, not a software problem. (The existing PDF layout already divides by line count.)
5. **Output = DOWNLOAD now (and print — both already exist). Emailing the PDF**
   (`doc.output('arraybuffer')` → SAM send) **is DEFERRED / out of scope here.**

## Explicitly OUT OF SCOPE
- Any `analytics.config` / `address_mapping` authoring or reading (parked Track 3).
- Emailing the label PDF as an attachment (the SAM send path).
- Auto-shrink-to-fit / wrap heuristics beyond "divide height by lines + truncate".
