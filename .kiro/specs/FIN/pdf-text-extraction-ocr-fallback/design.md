# PDF Text Extraction OCR Fallback Bugfix Design

## Overview

Some invoice PDFs saved with **"Microsoft: Print To PDF"** have no readable text layer.
Windows renders every glyph as a **vector path outline** (fill operators `m`/`l`/`h`/`f`),
not as a selectable text layer and not as a raster image. Verified against the real file
`netflix 202609.pdf`: 1 page, `/Producer = "Microsoft: Print To PDF"`, 0 fonts, 0
characters, 0 images, an empty page `/Resources`, and a ~352 KB content stream of pure
vector fill operators with **no text-showing operators** (`Tj`/`TJ`). `pypdf` and
`pdfplumber` therefore both correctly return `""` — there is genuinely no text layer to
read.

Two defects follow from that empty text, and both are fixed here:

1. **The AI hallucinates on empty input.** `process_pdf` returns `txt == ""`, and the
   pipeline (`pdf_processor.extract_transactions` → `pdf_ai_extraction.extract_with_ai`
   → `ai_extractor.AIExtractor.extract_invoice_data`) still hands that empty content to
   the AI model, which invents plausible placeholder values. Observed in production:
   Date `2023-11-15`, Total `€12.99`, Description `"Invoice 123456"` — none of which
   exist in the invoice or anywhere in our code.
2. **No OCR recovery exists for PDFs.** The real data is recoverable. Rasterizing each
   page with **PyMuPDF** at 300 dpi and running **tesseract** OCR recovered the genuine
   content: Netflix International B.V., Receipt No. `37C58-2972F-64916-D085A`, Date
   `17/09/2026`, Subtotal `€17.35`, VAT 21% `€3.64`, Total `€20.99` — completely
   different from the hallucinated values, which confirms both the hallucination and the
   recoverability.

The fix has three parts, all on the invoice-import code path and none touching the
MySQL/data plane:

1. **Shared tesseract binary resolution.** Both `pdf_parsing_strategies.py` (module-level
   `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`)
   and `image_ai_processor._try_tesseract` hardcode a Windows path that cannot resolve on
   Linux. A single helper `resolve_tesseract_cmd()` resolves the binary from `TESSERACT_CMD`
   → `shutil.which("tesseract")` → `None`, replacing both hardcoded paths. In dev the binary
   is confirmed at `/usr/bin/tesseract` and resolvable via `shutil.which("tesseract")`.
2. **OCR fallback on the PDF path.** When `pypdf` + `pdfplumber` produce no text,
   `process_pdf` renders each page with PyMuPDF `page.get_pixmap(dpi=300)` → PNG → PIL
   image and runs `pytesseract.image_to_string(image)` over it. PyMuPDF does its own
   rendering, so **no Ghostscript/poppler/ImageMagick system dependency is needed** — this
   is exactly why PyMuPDF is chosen over `pdfplumber.page.to_image()`, which needs
   Ghostscript (not installed). The recovered text flows into the existing AI extraction
   unchanged.
3. **Honest failure on empty content.** When text extraction *and* OCR both yield nothing,
   the system must not call the AI model on empty content and must not fabricate data. The
   empty-text path short-circuits before the AI call and routes through the existing
   `parser_used == "ai_failed"` channel, so the UI surfaces the explicit "No data found in
   the file" error. The fix prevents the hallucinating AI call from happening on empty
   input rather than trying to detect hallucination after the fact.

The strategy is deliberately minimal: OCR is additive and only runs when the text path
produces nothing, so every text-layer PDF (the 15+ working Netflix invoices) and every
non-PDF file takes exactly the path it does today.

## Glossary

- **Bug_Condition (C)**: A PDF import whose text-layer extraction (`pypdf` then
  `pdfplumber`) yields an empty string. The confirmed instance is the "Microsoft Print to
  PDF" vector-outline case, where page text is drawn as vector path outlines with no
  text-showing operators, so there is no text layer to read.
- **Property (P)**: The desired behavior for a bug-condition input — when OCR recovers
  usable text from a legible page, the real vendor data is parsed from *that recovered
  text*; when nothing is recoverable (OCR empty, or OCR unavailable), the system signals an
  explicit "No data found in the file" failure instead of calling the AI model on empty
  content and presenting fabricated data.
- **Preservation**: Existing behavior for text-layer PDFs and all non-PDF files (image,
  CSV, MHTML, EML) that must remain identical after the fix; OCR must never fire when `txt`
  is non-empty.
- **F (original)**: The current import path — sends empty content to the AI model, has no
  PDF OCR fallback, hardcodes the Windows tesseract path.
- **F' (fixed)**: The fixed path — environment-resolved tesseract, PyMuPDF+tesseract OCR
  fallback for empty-text PDFs, and an explicit "No data found in the file" failure instead
  of an AI call on empty content.
- **Vector-outline PDF**: A PDF whose page glyphs are drawn as vector fill operators
  (`m`/`l`/`h`/`f`) with no `Tj`/`TJ` text operators and no raster image — produced by
  "Microsoft: Print To PDF".
- **`process_pdf`**: The function in `backend/src/pdf_parsing_strategies.py` that extracts
  text from a PDF and returns the `{name, url, txt, folder}` file-data dict.
- **`extract_transactions`**: The method in `backend/src/pdf_processor.py` that turns
  file-data `txt` into transaction dicts via CSV rules or AI extraction, and currently
  fabricates `failure_data` when AI returns no positive amount.
- **`extract_with_ai`**: The function in `backend/src/pdf_ai_extraction.py` that calls
  `AIExtractor.extract_invoice_data` with the joined text lines.
- **`extract_invoice_data`**: The method in `backend/src/ai_extractor.py` that calls the
  AI model — currently invents values when handed empty content.
- **`resolve_tesseract_cmd()`**: New shared helper resolving the tesseract binary via
  `TESSERACT_CMD` env var → `shutil.which("tesseract")` → `None`.
- **`ocr_pdf_pages(file_path)`**: New helper that renders each PDF page with PyMuPDF at
  300 dpi and runs `pytesseract` over it to recover text.
- **`parser_used` / `ai_failed`**: The marker produced by
  `invoice_service._determine_parser_used` (and the test-service equivalent); `"ai_failed"`
  already means "no usable extraction" and already drives the UI's "No data found in the
  file" failure state when `transactions` is empty.

## Bug Details

### Bug Condition

The bug manifests when a PDF's text-layer extraction (`pypdf` then `pdfplumber`) yields an
empty string. The confirmed instance is a "Microsoft: Print To PDF" document whose page
text is drawn as vector path outlines with no text-showing operators — there is no text
layer to read, so `txt` is empty. The pipeline then hands that empty content to the AI
model, which fabricates placeholder values; and there is no OCR fallback on the PDF path to
recover the real text.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ImportedFile
  OUTPUT: boolean

  RETURN input.fileType = PDF
         AND textLayerExtract(input) = ""   // pypdf AND pdfplumber both produce nothing
END FUNCTION
```

### Examples

Verified against the real `netflix 202609.pdf` (`/Producer = "Microsoft: Print To PDF"`,
0 fonts, 0 chars, 0 images, ~352 KB of vector fill operators):

- **Hallucinated (current, unfixed)** — text extraction returns `""`, the AI model is
  called on empty content and invents: Date `2023-11-15`, Total `€12.99`, Description
  `"Invoice 123456"`. These are presented to the user as a real parse.
- **OCR-recovered (fixed)** — PyMuPDF renders each page at 300 dpi and tesseract recovers
  the genuine content: Vendor `Netflix International B.V.`, Receipt No.
  `37C58-2972F-64916-D085A`, Date `17/09/2026`, Subtotal `€17.35`, VAT 21% `€3.64`, Total
  `€20.99`. The AI then parses *this real text* and the correct values are stored.
- **Side-by-side** — the recovered Total `€20.99` versus the hallucinated `€12.99`, and the
  recovered Date `17/09/2026` versus the hallucinated `2023-11-15`, show that the old output
  was pure fabrication, not a mis-parse.
- **Edge case — OCR unavailable or recovers nothing** (e.g. the `tesseract` system binary is
  absent from the production image, or the page is illegible): the system must *not* call
  the AI model on empty content and must *not* fabricate data; it returns the explicit
  "No data found in the file" failure through the `ai_failed` channel.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Text-layer PDFs (the 15+ Netflix invoices that work today) continue to extract via the
  existing `pypdf` → `pdfplumber` path, and OCR is never invoked for them (3.1, 3.2).
- Non-PDF files (image, CSV, MHTML, EML) continue to use their existing processing paths
  with no behavioral change (3.3).
- When AI extraction succeeds on real text with a positive amount, transactions continue to
  be built from the extracted vendor data exactly as today (3.4).

**Scope:**
All inputs that are NOT bug-condition inputs must be completely unaffected by this fix.
This includes:
- Any PDF whose text-layer extraction already produces usable text (OCR never fires because
  `txt` is non-empty).
- Images, CSV, MHTML, and EML files (routed through unchanged `process_*` functions).

**Note:** The expected correct behavior for bug-condition inputs is defined in the
Correctness Properties section (Property 1). This section focuses on what must NOT change.

## Hypothesized Root Cause

> This root cause has been **CONFIRMED** empirically against `netflix 202609.pdf`, not merely
> hypothesized. Each piece below was verified against the real file.

1. **CONFIRMED — "Microsoft: Print To PDF" produces a vector-outline PDF with no text layer.**
   The file reports `/Producer = "Microsoft: Print To PDF"`, 0 fonts, 0 characters, 0 images,
   an empty page `/Resources`, and a ~352 KB content stream of pure vector fill operators
   (`m`/`l`/`h`/`f`) with no `Tj`/`TJ`. `pypdf` and `pdfplumber` therefore correctly return
   `""`. This is a file-specific trigger from the save method, not a vendor regression — the
   same vendor parsed successfully 15+ times, and the same invoice re-saved as a normal PDF
   parses correctly.

2. **CONFIRMED — the pipeline calls the AI model on empty content, which hallucinates.**
   With `txt == ""`, `extract_transactions` → `extract_with_ai` → `extract_invoice_data`
   still invokes the AI model, which invents Date `2023-11-15`, Total `€12.99`, Description
   `"Invoice 123456"`. The hallucination origin is specifically
   `ai_extractor.extract_invoice_data` being handed empty content; the fix prevents that call
   on empty input rather than trying to detect hallucination afterward.

3. **CONFIRMED — no OCR fallback on the PDF path, and the OCR binary path is hardcoded for
   Windows.** `process_pdf` only runs text-layer extractors; OCR is wired only into the image
   path. And both `pdf_parsing_strategies.py` (module-level `tesseract_cmd`) and
   `image_ai_processor._try_tesseract` point at `C:\Program Files\Tesseract-OCR\tesseract.exe`,
   which cannot exist in the Linux container, so OCR could never run there even if reached. The
   real binary is at `/usr/bin/tesseract` and resolvable via `shutil.which("tesseract")`.

4. **CONFIRMED — the recovered data differs from the hallucinated data.** PyMuPDF+tesseract
   recovered Total `€20.99` / Date `17/09/2026`, versus the hallucinated `€12.99` /
   `2023-11-15`, proving the current output is fabricated and the real data is recoverable.

## Correctness Properties

Property 1: Bug Condition - Empty-text PDFs get OCR recovery or an honest failure, never fabricated data

_For any_ input where the bug condition holds (`isBugCondition` returns true — a PDF whose
`pypdf`+`pdfplumber` text extraction is empty), the fixed code SHALL attempt an OCR fallback
(PyMuPDF 300-dpi rasterization + tesseract) and: (a) when OCR recovers usable text from a
legible page, the real invoice data (vendor, date, totals, VAT) SHALL be parsed from that
recovered text, not invented by the AI model; and (b) when OCR recovers nothing or is
unavailable, the system SHALL NOT call the AI model on empty content, SHALL NOT present
fabricated data, and SHALL route through the `ai_failed` channel so the UI shows the explicit
"No data found in the file" error.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

Property 2: Preservation - Text-layer PDFs and non-PDF files behave identically

_For any_ input where the bug condition does NOT hold (`isBugCondition` returns false) —
text-layer PDFs with a usable text layer, and all non-PDF files (image, CSV, MHTML, EML) —
the fixed code SHALL produce exactly the same result as the original code, invoking no OCR
on the PDF path and preserving all existing extraction, AI-success, and transaction-building
behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Based on the confirmed root cause, four coordinated changes are needed, all on the
invoice-import path.

**File**: `backend/src/pdf_parsing_strategies.py`

**Functions**: new `resolve_tesseract_cmd()`, new `ocr_pdf_pages(file_path)`, and
`process_pdf`

**Specific Changes**:

1. **Shared tesseract binary resolution.** Add a module-level helper
   `resolve_tesseract_cmd()` that returns the binary path by checking, in order: the
   `TESSERACT_CMD` environment variable, then `shutil.which("tesseract")`; it returns
   `None` when no binary is found. Replace the current module-level assignment
   `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`
   with: resolve once, and set `pytesseract.pytesseract.tesseract_cmd` from the resolver only
   if a path is found — never assign the hardcoded Windows path. (Satisfies 2.5; contributes
   to 2.6.)

2. **`ocr_pdf_pages(file_path)` using PyMuPDF + pytesseract.** Add a new helper that:
   - imports `pymupdf` (`import pymupdf`, with a legacy `import fitz` fallback) and
     `pytesseract` / `PIL.Image` inside a `try`, so a missing dependency degrades gracefully;
   - returns `[]` immediately if `resolve_tesseract_cmd()` is `None` (binary absent) or the
     imports fail — logging the reason, never raising;
   - opens the PDF with PyMuPDF, renders each page with `page.get_pixmap(dpi=300)`, converts
     the pixmap to PNG bytes → `PIL.Image`, and runs `pytesseract.image_to_string(image)`;
   - collects non-empty recovered lines across all pages and returns them.
   PyMuPDF does its own rendering, so no Ghostscript/poppler/ImageMagick system dependency is
   introduced (the reason PyMuPDF is used instead of `pdfplumber.page.to_image()`, which needs
   Ghostscript that is not installed). (Satisfies 2.1, 2.2, 2.6.)

3. **Wire the OCR fallback into `process_pdf`.** After the existing `pypdf` block and the
   `pdfplumber` fallback block, add: `if not text_lines:` → call `ocr_pdf_pages(file_path)` and
   extend `text_lines` with its result. The existing `pypdf`/`pdfplumber` blocks are left
   unchanged, and the returned dict shape (`name`, `url`, `txt`, `folder`) is unchanged. Because
   the block is guarded by `if not text_lines:`, it runs only for bug-condition inputs and never
   for text-layer PDFs. (Satisfies 2.1; preserves 3.1, 3.2.)

**File**: `backend/src/image_ai_processor.py`

**Function**: `_try_tesseract`

**Specific Changes**:

4. **Use the shared resolver on the image path too.** Replace the hardcoded
   `subprocess.run([r"C:\Program Files\Tesseract-OCR\tesseract.exe", "--version"], ...)`
   availability check and the hardcoded
   `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\..."` assignment with
   `resolve_tesseract_cmd()`. If it returns `None`, keep the existing "Tesseract not installed"
   behavior (return `_fallback_data`). This removes the second hardcoded Windows path and keeps
   the image path working on Linux and WSL without changing its observable success behavior.
   (Satisfies 2.5.)

**File**: `backend/src/pdf_ai_extraction.py` (and `backend/src/pdf_processor.py`)

**Functions**: `extract_with_ai`, `PDFProcessor.extract_transactions`

**Specific Changes**:

5. **Honest failure in the empty-text path — do not call the AI model on empty content.**
   `extract_with_ai` SHALL short-circuit when the joined text is empty/whitespace: return a
   sentinel that does not invoke `AIExtractor.extract_invoice_data` (so the model is never
   handed empty content and cannot hallucinate). `extract_transactions` SHALL, when text is
   empty and AI/OCR produced nothing usable, stop fabricating `failure_data`
   (`datetime.now()`, `0.0` amounts, `"<folder> invoice"`) and instead return no transaction
   (empty list) so that `invoice_service._determine_parser_used` /
   `invoice_test_service._determine_parser_used` return `"ai_failed"` for the empty
   `transactions` list — the existing channel that drives the UI's explicit "No data found in
   the file" error. The positive-amount AI success path is left untouched. (Satisfies 2.3,
   2.4; preserves 3.4.)

### Dependencies

Add to `backend/requirements.txt`:
- `pymupdf` — PDF rendering for OCR (self-contained renderer; no Ghostscript/poppler needed).
- `pytesseract` — Python binding to the tesseract engine (currently imported but not pinned).

> **System-package prerequisite (flagged):** The OCR fallback requires the `tesseract-ocr`
> **system package** at runtime. It is confirmed present in dev at `/usr/bin/tesseract`, but it
> **MUST** also be installed in the production container image. If the binary is absent,
> `resolve_tesseract_cmd()` returns `None`, `ocr_pdf_pages` returns `[]` without raising, and the
> flow degrades gracefully to the explicit "No data found in the file" failure (never a crash,
> never fabricated data).

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples that demonstrate the bug on the unfixed code (empty
text → AI hallucination; no OCR; hardcoded Windows path), then verify the fix produces real
OCR-recovered data (or an honest "No data found" failure) for bug-condition inputs while
leaving all non-bug inputs byte-for-byte unchanged.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix, and
confirm the (already empirically-confirmed) root cause. If a test does not fail as predicted,
re-hypothesize.

**Test Plan**: Drive `process_pdf` and the extraction pipeline with the real
`netflix 202609.pdf` vector-outline fixture and assert the observed defect on the UNFIXED
code. Also assert the hardcoded-path defect directly.

**Test Cases**:
1. **Vector-outline PDF yields empty text**: `process_pdf("netflix 202609.pdf").txt == ""`
   (holds on unfixed code — confirms no text layer and no OCR fallback).
2. **Empty text triggers an AI call that hallucinates**: with empty `txt`, the pipeline calls
   `AIExtractor.extract_invoice_data` on empty content and returns non-real values (e.g. a
   total of `€12.99`, date `2023-11-15`) presented as parsed data (holds on unfixed code —
   confirms the masquerade).
3. **Hardcoded Windows OCR path**: the module-level `tesseract_cmd` in
   `pdf_parsing_strategies.py` and the one in `image_ai_processor._try_tesseract` equal the
   Windows path and ignore `shutil.which("tesseract")` (holds on unfixed code — confirms the
   Linux-container failure).

**Expected Counterexamples**:
- `process_pdf("netflix 202609.pdf").txt == ""` with no OCR attempted.
- Hallucinated transaction (`€12.99` / `2023-11-15` / `"Invoice 123456"`) returned as if parsed.
- `tesseract_cmd` resolving to the non-existent Windows path on Linux.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces
the expected behavior — OCR-recovered real data when the page is legible, and a distinct
"No data found" failure (no AI call on empty content) when nothing is recoverable.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := process_import_fixed(input)
  IF ocrRecoversText(input) THEN
    ASSERT result.txt <> "" AND vendorDataParsedFrom(result.txt)
    ASSERT result.total == 20.99 AND result.date == "17/09/2026"   // real, not fabricated
  ELSE
    ASSERT result.aiModelCalledOnEmptyContent == false
    ASSERT result.parser_used == "ai_failed"
    ASSERT result.error == "No data found in the file"
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function
produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT process_import_original(input) = process_import_fixed(input)
  AND    ocrInvoked_fixed(input) = false
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation because:
- It generates many inputs automatically across the file-type and text-content domain.
- It catches edge cases (odd text content, empty pages mixed with text pages) that
  hand-written unit tests miss.
- It gives a strong guarantee that non-bug inputs are untouched — in particular that OCR is
  never invoked when `txt` is non-empty.

**Test Plan**: Observe behavior on the UNFIXED code for text-layer PDFs and non-PDF files, then
write property-based tests asserting the fixed code produces identical results and never calls
`ocr_pdf_pages` for those inputs.

**Test Cases**:
1. **Text PDF preservation**: a PDF with a real text layer produces the same `txt` before and
   after the fix, and `ocr_pdf_pages` is never called (assert via a spy/mock).
2. **Non-PDF preservation**: `process_image`, `process_csv`, `process_mhtml`, `process_eml`
   produce identical results before and after the fix.
3. **Positive-amount success preservation**: when AI extraction returns a positive total,
   `extract_transactions` builds the same transactions as today (3.4).
4. **Resolver dev-path preservation**: with no `TESSERACT_CMD` set and `tesseract` on `PATH`,
   `resolve_tesseract_cmd()` returns the `PATH` binary (`/usr/bin/tesseract`); with neither
   present it returns `None` and OCR degrades gracefully.

### Unit Tests

- `resolve_tesseract_cmd()` returns the `TESSERACT_CMD` value when set, else
  `shutil.which("tesseract")`, else `None` — and never the hardcoded Windows path.
- `process_pdf` invokes `ocr_pdf_pages` only when `pypdf`+`pdfplumber` text is empty.
- `ocr_pdf_pages` returns collected lines for a legible rendered page, and returns `[]`
  (no raise) when `pymupdf`/`pytesseract` import fails or `resolve_tesseract_cmd()` is `None`.
- `extract_with_ai` short-circuits on empty/whitespace text and does NOT call
  `AIExtractor.extract_invoice_data`.
- `extract_transactions` returns an empty transaction list (→ `ai_failed`) when text and OCR
  both yield nothing, and builds transactions normally for a positive AI total.

### Property-Based Tests

- For randomly generated non-empty text content, `process_pdf` never calls `ocr_pdf_pages`
  (preservation invariant).
- For randomly generated file-data where AI returns a positive amount, `extract_transactions`
  always builds matching transactions (success invariant).
- Across generated extraction states (empty-text / OCR-empty / OCR-recovered / positive AI),
  the AI model is called on empty content in exactly zero cases, and `ai_failed` appears
  exactly when no usable text is recovered (honest-failure invariant).

### Integration Tests

- Full invoice-upload flow with the real `netflix 202609.pdf` fixture: OCR runs, text is
  recovered, and the stored transaction reflects the real values (Total `€20.99`, VAT `€3.64`,
  Date `17/09/2026`) — not the hallucinated `€12.99` / `2023-11-15`.
- Full flow with OCR unavailable (binary absent): the response is routed to
  `parser_used == "ai_failed"`, the UI shows "No data found in the file", and the AI model is
  never called on empty content — no placeholder data.
- Full flow with a text-layer PDF and with a non-PDF file: responses are unchanged from current
  behavior, and `ocr_pdf_pages` is never invoked.
