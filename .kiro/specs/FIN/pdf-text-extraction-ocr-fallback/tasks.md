# Implementation Plan

This plan follows the exploratory bugfix workflow from the design's Testing Strategy:
first reproduce the defect on the UNFIXED code, then apply the coordinated changes, then
confirm the fix (Property 1) and preservation (Property 2). Tests live under
`backend/tests/unit/` and `backend/tests/integration/` and follow repo conventions:
`@pytest.mark.unit` / `@pytest.mark.integration` are auto-applied by directory,
`test_{function}_{scenario}_{expected}` naming, Hypothesis for property-based tests, and
the `mock_db` / `mock_env` isolation fixtures. No real DB connections (the unit
`conftest.py` connection guard enforces this), no `mysql.connector`, no `load_dotenv()` in
test files. All test runs use `cd backend && source .venv/bin/activate && pytest ...`.

The confirmed trigger is a **"Microsoft: Print To PDF" vector-outline PDF** — page glyphs
are drawn as vector fill operators (`m`/`l`/`h`/`f`) with no `Tj`/`TJ` text operators and no
raster image, so `pypdf` + `pdfplumber` both correctly return `""`. Use the committed real
fixture `.kiro/specs/FIN/pdf-text-extraction-ocr-fallback/netflix 202609.pdf` where helpful.

Source files under change (per the design's Fix Implementation):
- `backend/src/pdf_parsing_strategies.py` — new `resolve_tesseract_cmd()` helper, new
  `ocr_pdf_pages(file_path)` helper (PyMuPDF `get_pixmap(dpi=300)` → PNG → PIL →
  `pytesseract.image_to_string`), OCR fallback wired into `process_pdf`, and removal of the
  hardcoded Windows `tesseract_cmd`.
- `backend/src/image_ai_processor.py` — `_try_tesseract` uses the shared resolver instead of
  its own hardcoded Windows path.
- `backend/src/pdf_ai_extraction.py` + `backend/src/pdf_processor.py` — `extract_with_ai`
  short-circuits on empty text (never calls the AI model on empty content) and
  `extract_transactions` stops fabricating `failure_data`, routing genuine failure through the
  empty-list → `"ai_failed"` channel.
- `backend/requirements.txt` — add `pymupdf` and `pytesseract`; the `tesseract-ocr` **system
  package** is flagged as a production container image prerequisite.

---

- [x] 1. Write bug condition exploration test (BEFORE implementing the fix)
  - **Property 1: Bug Condition** - Vector-outline PDFs yield empty text, the AI is called on empty content and fabricates data, and the OCR path is hardcoded for Windows
  - **CRITICAL**: These tests MUST reproduce / assert the current defect on the UNFIXED code — that is what confirms the bug exists.
  - **DO NOT attempt to fix the test or the code when it reproduces the defect** — document the counterexamples instead.
  - **NOTE**: These tests encode the expected post-fix behavior; they will validate the fix once it is implemented (re-run at task 3.2).
  - **GOAL**: Surface counterexamples that demonstrate the three cooperating root causes confirmed in the design.
  - **Scoped PBT Approach**: The bug is deterministic, so scope the properties to concrete failing cases — the committed real `netflix 202609.pdf` vector-outline fixture and file-data with empty `txt` — rather than generating arbitrary PDFs.
  - Create `backend/tests/unit/test_pdf_ocr_fallback_bug_condition.py` (`@pytest.mark.unit`, auto-applied by directory).
  - Resolve the real fixture path (e.g. a module-level `FIXTURE = Path(__file__).parents[3] / ".kiro/specs/FIN/pdf-text-extraction-ocr-fallback/netflix 202609.pdf"`). Mock `config.get_storage_folder` / `ensure_folder_exists` and `drive_result` so no real storage/Drive is touched.
  - **Test case 1 — vector-outline PDF yields empty text (Bug Condition C(X))**: assert `process_pdf("netflix 202609.pdf", drive_result, config, folder_name)["txt"] == ""`. Holds on UNFIXED code — confirms there is no text layer and no OCR fallback on the PDF path. _Requirements: 1.1, 1.3_
  - **Test case 2 — empty text triggers an AI call that hallucinates**: call the extraction pipeline (`PDFProcessor.extract_transactions` → `extract_with_ai` → `AIExtractor.extract_invoice_data`) with `file_data = {"txt": "", "folder": "netflix", "url": ..., "name": ...}`, mocking `ai_extractor.AIExtractor.extract_invoice_data` to assert it IS invoked with empty content on the unfixed path (and returns the observed hallucinated shape, e.g. Total `12.99`, Date `2023-11-15`, Description `"Invoice 123456"`). Mock `database.DatabaseManager` and `transaction_logic.TransactionLogic` per `mock_db` conventions. Assert the returned transaction list is non-empty and carries those fabricated values presented as a real parse. Holds on UNFIXED code — confirms the masquerade. _Requirements: 1.1, 1.2_
  - **Test case 3 — hardcoded Windows OCR path**: assert that on import of `pdf_parsing_strategies`, `pytesseract.pytesseract.tesseract_cmd` equals `r"C:\Program Files\Tesseract-OCR\tesseract.exe"`, and that the same hardcoded path exists in `image_ai_processor._try_tesseract`, with `shutil.which("tesseract")` never consulted. Holds on UNFIXED code — confirms the Linux-container failure. _Requirements: 1.4_
  - **Test case 4 — edge: empty extraction is not signalled as a distinct failure**: assert `extract_transactions` on empty `txt` returns a formatted transaction list (today's date / `0.0` / `"netflix invoice"`) rather than an empty list / explicit failure marker, so the caller's `_determine_parser_used` would classify it as a successful `"ai"` parse rather than `"ai_failed"`. Holds on UNFIXED code — confirms 2.3/2.4 are unmet today. _Requirements: 1.2_
  - Run on UNFIXED code: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_ocr_fallback_bug_condition.py -v`.
  - **EXPECTED OUTCOME**: Tests pass by asserting the defect (bug reproduced). Document each counterexample (e.g. `process_pdf("netflix 202609.pdf").txt == ""` with no OCR attempted; the AI called on empty content returning `12.99` / `2023-11-15` / `"Invoice 123456"`; `tesseract_cmd == C:\Program Files\...` in both modules).
  - Mark complete when the tests are written, run, and the counterexamples are documented.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing the fix)
  - **Property 2: Preservation** - Text-layer PDFs and non-PDF files behave identically
  - **IMPORTANT**: Follow the observation-first methodology — observe behavior on the UNFIXED code first, then encode it as tests that must still pass after the fix.
  - **Testing Approach**: Property-based (Hypothesis) is recommended here because preservation is a universal property ("for all non-bug-condition inputs") and PBT catches edge cases (empty pages mixed with text pages, odd text content) hand-written cases miss. In particular it guarantees OCR is never invoked when `txt` is non-empty.
  - Create `backend/tests/unit/test_pdf_ocr_fallback_preservation.py` (`@pytest.mark.unit`).
  - **Observe (UNFIXED)**: record `process_pdf` output for a text-layer PDF, and `process_csv` / `process_mhtml` / `process_eml` / `process_image` outputs for representative non-PDF inputs; record that `extract_transactions` builds the usual main (+ VAT) transactions when the AI returns a positive `total_amount`.
  - **Property test 2a — text PDF preservation + OCR never fires**: with a text-layer PDF fixture, assert `process_pdf` returns the same `txt` before and after the fix, and spy/patch `pdf_parsing_strategies.ocr_pdf_pages` to assert it is NEVER called when text-layer extraction already yields text. Use Hypothesis to generate non-empty text content and assert the OCR helper is never invoked (preservation invariant). _Requirements: 3.1, 3.2_
  - **Property test 2b — non-PDF preservation**: assert `process_image`, `process_csv`, `process_mhtml`, `process_eml` produce byte-identical results to the UNFIXED code (mock `config`, `drive_result`, and `ImageAIProcessor` as in existing `test_image_ai_processor.py`). _Requirements: 3.3_
  - **Property test 2c — positive-amount success preservation**: Hypothesis-generate AI results with `total_amount > 0` (reuse the strategies/mocks from `tests/unit/test_pdf_processor_properties.py`) and assert `extract_transactions` builds the same main (+ VAT when `vat_amount > 0`) transactions as today. _Requirements: 3.4_
  - **Property test 2d — resolver dev-path preservation**: assert that with `TESSERACT_CMD` unset and `tesseract` present on `PATH`, `resolve_tesseract_cmd()` returns the `PATH` binary (patch `shutil.which` → `/usr/bin/tesseract`); with neither present it returns `None` and non-OCR paths are unaffected (no raise). Use `mock_env` / `patch.dict` for env; never a real Windows path. _Requirements: 3.1, 3.2_
  - Run on UNFIXED code: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_ocr_fallback_preservation.py -v`.
  - **EXPECTED OUTCOME**: Tests that reference existing behavior (2a `txt`, 2b, 2c) PASS on the UNFIXED code, establishing the baseline to preserve. Tests that reference the not-yet-existing `ocr_pdf_pages` / `resolve_tesseract_cmd` symbols (the "OCR never fires" spy in 2a and all of 2d) are expected to error/fail until task 3 introduces those symbols — note which assertions are baseline (must already pass) vs. post-fix (become green after task 3).
  - Mark complete when the baseline-behavior assertions are written, run, and passing on the unfixed code.
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for vector-outline PDF extraction (OCR fallback + environment-resolved binary + honest failure)

  - [x] 3.1 Implement the shared tesseract resolver and remove both hardcoded Windows paths
    - **`backend/src/pdf_parsing_strategies.py`**: add module-level `resolve_tesseract_cmd()` returning, in order, the `TESSERACT_CMD` env var value, then `shutil.which("tesseract")`, else `None`. On import, set `pytesseract.pytesseract.tesseract_cmd` from this helper ONLY when a path is found; never assign the hardcoded Windows path. Remove the `r"C:\Program Files\Tesseract-OCR\tesseract.exe"` assignment.
    - **`backend/src/image_ai_processor.py::_try_tesseract`**: replace the hardcoded Windows `subprocess` version check and the hardcoded `tesseract_cmd` assignment with `resolve_tesseract_cmd()`. If it returns `None`, keep the existing "Tesseract not installed" behavior (fall back to `_fallback_data`); do not change the image path's observable success behavior.
    - _Bug_Condition: isBugCondition(input) = input.fileType == PDF AND textLayerExtract(input) == ""_
    - _Expected_Behavior: OCR binary resolved from TESSERACT_CMD → shutil.which("tesseract") → None, never a hardcoded OS-specific path_
    - _Preservation: image path keeps its "Tesseract not installed" → _fallback_data behavior unchanged_
    - _Requirements: 2.5, 2.6_

  - [x] 3.2 Implement `ocr_pdf_pages` with PyMuPDF + pytesseract and wire it into `process_pdf`
    - **`backend/src/pdf_parsing_strategies.py`**: add `ocr_pdf_pages(file_path)` that imports `pymupdf` (with a legacy `import fitz` fallback) and `pytesseract` / `PIL.Image` inside a `try` so a missing dependency degrades gracefully; returns `[]` immediately (logging the reason, never raising) if `resolve_tesseract_cmd()` is `None` or the imports fail; opens the PDF with PyMuPDF, renders each page via `page.get_pixmap(dpi=300)`, converts the pixmap to PNG bytes → `PIL.Image`, runs `pytesseract.image_to_string(image)` per page, and returns the collected non-empty lines. **No Ghostscript/poppler/ImageMagick** — PyMuPDF does its own rendering (the reason it is chosen over `pdfplumber.page.to_image()`).
    - In `process_pdf`, after the existing `pypdf` block and `pdfplumber` fallback block, add `if not text_lines:` → `text_lines.extend(ocr_pdf_pages(file_path))`. Leave the `pypdf`/`pdfplumber` blocks and the returned dict shape (`name`, `url`, `txt`, `folder`) unchanged, so OCR fires only for bug-condition inputs.
    - _Bug_Condition: textLayerExtract(X) == "" (empty pypdf + pdfplumber text)_
    - _Expected_Behavior: ocrRecoversText(X) ⇒ result.txt != "" and the recovered text flows into AI extraction; binary/dep absent ⇒ returns [] without raising_
    - _Preservation: OCR never fires when text_lines is non-empty; dict shape unchanged (3.1, 3.2)_
    - _Requirements: 2.1, 2.2, 2.6_

  - [x] 3.3 Implement honest failure — never call the AI model on empty content
    - **`backend/src/pdf_ai_extraction.py::extract_with_ai`**: short-circuit when the joined text is empty/whitespace — return a sentinel that does NOT invoke `AIExtractor.extract_invoice_data`, so the model is never handed empty content and cannot hallucinate.
    - **`backend/src/pdf_processor.py::PDFProcessor.extract_transactions`**: when text is empty and AI/OCR produced nothing usable (AI error or no positive `total_amount`), stop building `failure_data` (`datetime.now()`, `0.0`, `"<folder> invoice"`) and return an empty transaction list so that `invoice_service._determine_parser_used` / `invoice_test_service._determine_parser_used` return `"ai_failed"` for the empty list — the existing channel that drives the UI's explicit "No data found in the file" error. Leave the positive-amount AI success path untouched.
    - _Bug_Condition: textLayerExtract(X) == "" AND NOT ocrRecoversText(X)_
    - _Expected_Behavior: aiModelCalledOnEmptyContent == false; parser_used == "ai_failed"; error == "No data found in the file"; no fabricated data_
    - _Preservation: positive-amount AI success builds the same transactions as today (3.4)_
    - _Requirements: 2.3, 2.4_

  - [x] 3.4 Add Python dependencies and install the `tesseract-ocr` system package in the production image
    - Add `pymupdf` and `pytesseract` to `backend/requirements.txt` (pin per repo convention — `pytesseract` is currently imported but not pinned, so give it an explicit version alongside the new `pymupdf` pin). No rasterizer package (poppler/ghostscript) is required because PyMuPDF does its own rendering.
    - **`backend/Dockerfile`** is the production image builder (confirmed: both `backend/railway.json` and `backend/railway.toml` set `builder = "DOCKERFILE"` / `dockerfilePath = "Dockerfile"`, and `backend/nixpacks.toml` is a disabled stub reading "Use Dockerfile instead"). Add `tesseract-ocr` to the existing `apt-get install` block, which currently installs `curl libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2 gcc g++ cmake` — append `tesseract-ocr` to that same package list. Do NOT add any poppler/ghostscript package (PyMuPDF renders on its own). Keep the trailing `rm -rf /var/lib/apt/lists/*` cleanup line intact in the same `RUN` layer.
    - **Graceful-degradation guarantee (why the code fix is safe to ship before the image is rebuilt)**: until the image includes `tesseract-ocr`, `resolve_tesseract_cmd()` returns `None`, `ocr_pdf_pages()` returns `[]`, and the flow surfaces the "No data found in the file" error — never a crash, never fabricated data. So the code change can deploy ahead of the image rebuild; it simply won't auto-recover vector-outline PDFs until `tesseract-ocr` is actually deployed in the production image.
    - _Requirements: 2.6_

  - [x] 3.5 Verify the bug condition exploration test now reflects the fixed behavior
    - **Property 1: Expected Behavior** - Vector-outline PDFs get OCR recovery or an honest failure, never fabricated data
    - **IMPORTANT**: Re-run / update the SAME tests from task 1 — the task 1 cases encoded the UNFIXED defect, so update their assertions to the post-fix expectation they were always meant to validate; do NOT write a brand-new file.
    - Test case 1 → with the real `netflix 202609.pdf` fixture and `tesseract` resolvable, `process_pdf(...)["txt"] != ""` (OCR ran and recovered text); when the binary is unavailable, OCR degrades gracefully (empty `txt`, no raise). _Requirements: 2.1, 2.2_
    - **Fix-Checking**: assert that when OCR yields text, that text flows into AI extraction and the resulting vendor data is parsed from it — e.g. the stored Total is `20.99` and Date `17/09/2026` (the real OCR-recovered values), NOT the hallucinated `12.99` / `2023-11-15`. _Requirements: 2.1, 2.2_
    - Test case 2/4 → `extract_with_ai` is NOT called with empty content, and `extract_transactions` on empty `txt` / AI error returns an empty list (routed to `"ai_failed"`), NOT placeholder transactions. _Requirements: 2.3, 2.4_
    - Test case 3 → `tesseract_cmd` is resolved from `TESSERACT_CMD` / `PATH` in both modules and is never the hardcoded Windows path. _Requirements: 2.5_
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_ocr_fallback_bug_condition.py -v`.
    - **EXPECTED OUTCOME**: Tests PASS (confirms the bug is fixed and the expected behavior holds for all bug-condition inputs).
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Text-layer PDFs and non-PDF files behave identically
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new ones. The "OCR never fires" spy (2a) and resolver tests (2d) that referenced not-yet-existing symbols should now be green.
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_ocr_fallback_preservation.py -v`.
    - **EXPECTED OUTCOME**: All preservation tests PASS (no regressions): text PDFs produce identical `txt` with OCR never invoked, non-PDF paths unchanged, positive-amount success unchanged, dev-path resolution correct.
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 4. Unit tests for the new helpers and the failure channel
  - Add focused unit tests (`backend/tests/unit/test_pdf_ocr_fallback.py`, `@pytest.mark.unit`) alongside the property tests, covering the design's Unit Tests list:
  - `resolve_tesseract_cmd()` returns the `TESSERACT_CMD` value when set; else `shutil.which("tesseract")`; else `None` — and never a Windows path (patch `os.environ` via `mock_env`/`patch.dict` and `shutil.which`). _Requirements: 2.5_
  - `process_pdf` invokes `ocr_pdf_pages` only when `pypdf`+`pdfplumber` text is empty (spy on the helper for both the text-PDF and vector-outline fixtures). _Requirements: 2.1, 3.1, 3.2_
  - `ocr_pdf_pages` returns collected lines for a legible rendered page (mock `pymupdf`/`page.get_pixmap` and `pytesseract.image_to_string`) and returns `[]` WITHOUT raising when `pymupdf`/`pytesseract` import fails or `resolve_tesseract_cmd()` → `None`. _Requirements: 2.1, 2.6_
  - `extract_with_ai` short-circuits on empty/whitespace text and does NOT call `AIExtractor.extract_invoice_data`. _Requirements: 2.3_
  - `extract_transactions` returns an empty transaction list (→ `"ai_failed"`) when text and OCR both yield nothing, and builds transactions normally for a positive AI total (reuse `mock_db` / `TransactionLogic` mocks). _Requirements: 2.4, 3.4_
  - `_try_tesseract` uses `resolve_tesseract_cmd()` and preserves "Tesseract not installed" → `_fallback_data` when it returns `None` (extend/mirror `tests/unit/test_image_ai_processor.py`). _Requirements: 2.5_
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_ocr_fallback.py -v`.
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.4_

- [x] 5. Property-based tests for the fix invariants
  - Add Hypothesis property tests (co-locate in `backend/tests/unit/test_pdf_ocr_fallback_preservation.py` or a dedicated `test_pdf_ocr_fallback_props.py`), per the design's Property-Based Tests list:
  - For randomly generated non-empty text content, `process_pdf` NEVER calls `ocr_pdf_pages` (preservation invariant). _Requirements: 3.1, 3.2_
  - For randomly generated file-data where the AI returns a positive amount, `extract_transactions` ALWAYS builds matching transactions (success invariant). _Requirements: 3.4_
  - Across generated extraction states (empty-text / OCR-empty / OCR-recovered / positive AI), the AI model is called on empty content in EXACTLY zero cases, and `"ai_failed"` appears EXACTLY when no usable text is recovered (honest-failure invariant). _Requirements: 2.3, 2.4_
  - Follow existing PBT conventions (`@settings(max_examples=..., deadline=None)`, strategies modeled on `test_pdf_processor_properties.py`).
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_ocr_fallback_props.py -v` (or the co-located file).
  - _Requirements: 2.3, 2.4, 3.1, 3.2, 3.4_

- [x] 6. Integration tests for the full invoice-upload flow
  - Add integration tests under `backend/tests/integration/` (`@pytest.mark.integration`, auto-applied by directory), per the design's Integration Tests list:
  - **Microsoft-PDF success**: drive the full invoice-upload flow with the real `netflix 202609.pdf` fixture (tesseract available or mocked at the boundary); assert OCR runs, text is recovered, and the stored transaction reflects the real parsed values (Total `20.99`, VAT `3.64`, Date `17/09/2026`) rather than the hallucinated `12.99` / `2023-11-15`. _Requirements: 2.1, 2.2_
  - **Genuinely unreadable PDF**: drive the flow with OCR unavailable (binary absent) or empty-OCR; assert the response routes through `parser_used == "ai_failed"`, the UI shows "No data found in the file", the AI model is never called on empty content, and NO placeholder vendor data (today's date / €0.00 / `"<folder> invoice"`) is presented. _Requirements: 2.3, 2.4, 2.6_
  - **Text PDF and non-PDF unchanged**: drive the flow with a text-layer PDF and with a non-PDF file (image / CSV); assert responses are unchanged from current behavior and `ocr_pdf_pages` is never invoked. _Requirements: 3.1, 3.2, 3.3, 3.4_
  - Mock external boundaries (Google Drive, DB) using the integration fixtures; keep the invoice service / route wiring real so `_determine_parser_used` is exercised end to end.
  - Run: `cd backend && source .venv/bin/activate && pytest tests/integration/ -k ocr_fallback -v`.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 3.1, 3.2, 3.3, 3.4_

- [x] 7. Checkpoint - Ensure all tests pass
  - Run the full affected suite: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_ocr_fallback_bug_condition.py tests/unit/test_pdf_ocr_fallback_preservation.py tests/unit/test_pdf_ocr_fallback.py tests/integration/ -k "ocr_fallback or pdf" -v`.
  - Run the broader PDF regression set to confirm no collateral damage: `cd backend && source .venv/bin/activate && pytest tests/unit/test_pdf_processor.py tests/unit/test_pdf_processor_properties.py tests/unit/test_image_ai_processor.py tests/unit/test_pdf_ai_extraction.py -v`.
  - Lint the changed source: `cd backend && source .venv/bin/activate && ruff check src/pdf_parsing_strategies.py src/pdf_processor.py src/pdf_ai_extraction.py src/image_ai_processor.py`.
  - Confirm Property 1 (fix checking) and Property 2 (preservation) both pass; the bug-condition tests that reproduced the defect now validate the fix.
  - Clean up any scratch fixtures/output. Ask the user if any question arises (in particular whether the production container image already installs the `tesseract-ocr` system package — the infrastructure prerequisite flagged in task 3.4 and the design's Dependency note).
