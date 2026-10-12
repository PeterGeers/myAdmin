# Bugfix Requirements Document

## Introduction

When importing certain invoice PDFs in production, text extraction returns an empty string, yet the system still presents what looks like a successfully parsed invoice. The values shown to the user are not real — they are fabricated by the AI model, which is being handed empty content and responds with plausible-looking placeholder data.

The confirmed trigger is the PDF save method, not the vendor and not a general regression. The example file (`netflix 202609.pdf`) was produced with `/Producer = "Microsoft: Print To PDF"`. When a document is saved this way, Windows renders all page text as **vector path outlines** (fill operators `m`/`l`/`h`/`f`), not as a real selectable text layer and not as a raster image. Verified against the actual file:

- `pypdf` and `pdfplumber` both report: 1 page, 0 characters, 0 images.
- The page `/Resources` is empty (no fonts, no XObjects).
- The content stream is ~352 KB of pure vector fill operators with no text-showing operators (`Tj`/`TJ`).

So text extraction legitimately returns `""` — there is no text layer to read. The same invoice re-saved as a normal PDF parses correctly, and this Netflix vendor has parsed successfully 15+ times before. This is a file-specific trigger caused solely by the "Microsoft Print to PDF" save method.

Two defects follow from that empty text:

- **Hallucinated data.** The pipeline (`backend/src/pdf_processor.py::extract_transactions` → `pdf_ai_extraction.extract_with_ai` → `ai_extractor.AIExtractor.extract_invoice_data`) still sends the empty content to the AI model. The model invents plausible placeholder values that are presented to the user as a real parse. Observed in production: Date `2023-11-15`, Total `€12.99`, Description `"Invoice 123456"` — none of which exist in our code or in the invoice.
- **No OCR recovery.** The real data is recoverable. Rasterizing the page (pymupdf at 300 dpi) and running tesseract OCR recovered the genuine content: Netflix International B.V., Receipt No. `37C58-2972F-64916-D085A`, Date `17/09/2026`, Subtotal `€17.35`, VAT 21% `€3.64`, Total `€20.99` — completely different from the hallucinated values, confirming the hallucination. tesseract is available in dev at `/usr/bin/tesseract` and resolvable via `shutil.which("tesseract")`, but the current code hardcodes a Windows path (`C:\Program Files\Tesseract-OCR\tesseract.exe`) in `backend/src/pdf_parsing_strategies.py`, which cannot resolve on Linux.

The impact: users importing a "Microsoft Print to PDF" invoice get fabricated transaction data that looks real, and the genuine invoice data (which OCR can recover) is never surfaced.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a PDF whose text-layer extraction (pypdf then pdfplumber) yields an empty string is imported THEN the system still passes the empty content to the AI model instead of stopping
1.2 WHEN the AI model is called with empty content THEN the system fabricates placeholder invoice values (e.g. Date `2023-11-15`, Total `€12.99`, Description `"Invoice 123456"`) and presents them to the user as a real parse
1.3 WHEN text-layer extraction yields an empty string THEN the system does not attempt any OCR fallback to recover the text, even though the real data is recoverable by rasterizing the page and running OCR
1.4 WHEN OCR is attempted THEN the system resolves the OCR binary from a hardcoded Windows path (`C:\Program Files\Tesseract-OCR\tesseract.exe`) in `backend/src/pdf_parsing_strategies.py`, which cannot resolve on Linux

### Expected Behavior (Correct)

2.1 WHEN a PDF's text-layer extraction (pypdf then pdfplumber) yields an empty string THEN the system SHALL attempt an OCR fallback: rasterize each page to an image, run OCR to recover the text, and feed the recovered text into the existing AI extraction path
2.2 WHEN the OCR fallback recovers usable text from a legible page THEN the system SHALL parse the real invoice data from that recovered text rather than from invented content
2.3 WHEN text-layer extraction yields an empty string AND OCR also recovers no usable text (or OCR is unavailable) THEN the system SHALL NOT call the AI model on empty content and SHALL NOT present fabricated or placeholder data
2.4 WHEN no usable text can be recovered by any means THEN the system SHALL return an explicit error to the user — "No data found in the file" — routed through the existing failure channel (`parser_used == "ai_failed"`) so the UI shows a genuine failure state
2.5 WHEN the system needs the OCR engine binary THEN it SHALL resolve the binary from the environment (e.g. `shutil.which("tesseract")` or an environment variable), never from a hardcoded OS-specific path
2.6 WHEN the OCR engine binary is absent from the runtime THEN the OCR fallback SHALL degrade gracefully without crashing, and the system SHALL fall through to the explicit "No data found in the file" failure

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a PDF with a real text layer is imported (the 15+ Netflix invoices that work today) THEN the system SHALL CONTINUE TO extract and parse it exactly as now
3.2 WHEN text-layer extraction already yields text THEN the system SHALL NOT fire OCR
3.3 WHEN a non-PDF file (image, CSV, MHTML, EML) is imported THEN the system SHALL CONTINUE TO use its existing processing path unchanged
3.4 WHEN AI extraction succeeds on real text with a positive amount THEN the system SHALL CONTINUE TO build the transaction from that extracted data exactly as it does today

## Bug Condition and Property

### Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type ImportedFile
  OUTPUT: boolean

  // The bug triggers for PDFs whose text-layer extraction (pypdf + pdfplumber)
  // yields an empty string. The confirmed instance is the "Microsoft Print to PDF"
  // vector-outline case, where page text is rendered as vector path outlines with
  // no text-showing operators, so there is no text layer to read.
  RETURN X.fileType = PDF
     AND textLayerExtract(X) = ""        // pypdf and pdfplumber both produce nothing
END FUNCTION
```

### Property — Fix Checking

```pascal
// Property: Fix Checking — empty-text PDFs get OCR recovery or an honest failure,
// never fabricated data.
FOR ALL X WHERE isBugCondition(X) DO
  result ← processImport'(X)

  // When OCR recovers usable text from a legible page, vendor data is parsed from
  // THAT recovered text, not invented by the AI model.
  ASSERT (ocrRecoversText(X)
            IMPLIES result.vendorData.parsedFromRecoveredText = true
                AND result.vendorData <> fabricated)

  // When nothing is recoverable (OCR finds no usable text, or OCR is unavailable),
  // the system signals an explicit failure instead of fabricating data.
  AND    (NOT ocrRecoversText(X)
            IMPLIES result.aiModelCalledOnEmptyContent = false
                AND result.error = "No data found in the file"
                AND result.parserUsed = "ai_failed")
END FOR
```

### Property — Preservation Checking

```pascal
// Property: Preservation Checking — text-layer PDFs and non-PDF files behave
// identically to today, and OCR never runs for them.
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT processImport(X) = processImport'(X)
  AND    ocrInvoked'(X) = false
END FOR
```

Where **F** = the current import code path (sends empty content to the AI model, no PDF OCR fallback, hardcoded Windows OCR path) and **F'** = the fixed path (adds an OCR fallback for text-empty PDFs with an environment-resolved OCR binary, and returns an explicit "No data found in the file" failure instead of calling the AI model on empty content).

> **Dependency flagged by this spec:** The OCR fallback requires the `tesseract` system binary to be present in the runtime. It is confirmed present in dev at `/usr/bin/tesseract`, but it MUST also be installed in the production container image. The Python dependencies `pymupdf` and `pytesseract` are added. If the binary is absent, OCR degrades gracefully (no crash) and the flow falls through to the explicit "No data found in the file" failure.
