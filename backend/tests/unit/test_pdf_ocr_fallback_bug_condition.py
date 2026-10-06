"""
Fix-checking tests for the PDF OCR-fallback bugfix.

Feature: pdf-text-extraction-ocr-fallback (bugfix spec)
Property 1: Expected Behavior — vector-outline PDFs get OCR recovery or an honest
failure, never fabricated data.

HISTORY: these are the SAME four cases written at task 1, where they encoded the
UNFIXED defect (empty text handed to the AI, no OCR fallback, hardcoded Windows
tesseract path). At task 3.5 their assertions are flipped to the post-fix
expectation they were always meant to validate: OCR now recovers the real text,
that text flows into AI extraction, empty content never reaches the AI model, and
the tesseract binary is resolved from the environment. These tests PASS on the
FIXED code — confirming the bug is fixed and the expected behavior holds for every
bug-condition input.

The bug is deterministic, so the properties are scoped to concrete cases — the
committed real "Microsoft: Print To PDF" vector-outline fixture
(`netflix 202609.pdf`) and file-data with an empty `txt` — rather than generating
arbitrary PDFs.

`@pytest.mark.unit` is auto-applied by the `tests/unit/` directory. No real DB
connections, no `mysql.connector`, no `load_dotenv()` — all external boundaries
(storage/Drive, DatabaseManager, TransactionLogic, AIExtractor) are mocked. The AI
boundary is mocked to echo values parsed from the OCR'd text, keeping the test
deterministic while still proving the recovered text (not invented content) drives
the parse.
"""

import importlib
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The committed real vector-outline fixture. parents[3] of
# backend/tests/unit/<file>.py is the repo root.
FIXTURE = (
    Path(__file__).parents[3]
    / ".kiro/specs/FIN/pdf-text-extraction-ocr-fallback/netflix 202609.pdf"
)

# The hardcoded Windows path the UNFIXED code pointed tesseract at — it cannot
# resolve inside the Linux production container. The fix must never use it.
WINDOWS_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# The genuine values OCR recovers from the fixture (observed at task 3.2): the
# page rasterizes to "€20.99" total, "€3.64" VAT, date "17/09/2026". These are
# NOT the hallucinated 12.99 / 2023-11-15 the UNFIXED code produced on empty text.
OCR_TOTAL = 20.99
OCR_VAT = 3.64
OCR_DATE = "17/09/2026"

# The hallucinated shape the UNFIXED pipeline produced from empty content.
HALLUCINATED_TOTAL = 12.99
HALLUCINATED_DATE = "2023-11-15"


@pytest.fixture
def mock_config():
    """A Config stand-in so process_pdf touches no real storage folders."""
    config = MagicMock()
    config.get_storage_folder.return_value = "/test/netflix"
    config.ensure_folder_exists.return_value = None
    return config


@pytest.fixture
def mock_drive_result():
    """A Google Drive upload result stand-in (no real Drive call)."""
    return {
        "id": "mock_file_id",
        "url": "https://drive.google.com/file/d/mock_file_id/view",
    }


def test_process_pdf_vector_outline_fixture_recovers_text_via_ocr(
    mock_config, mock_drive_result
):
    """Test case 1 (fixed) — vector-outline PDF recovers text via OCR fallback.

    On the FIXED code, `process_pdf` runs pypdf + pdfplumber (both yield nothing
    for the "Microsoft: Print To PDF" fixture) and then falls back to the new OCR
    path, which rasterizes each page with PyMuPDF at 300 dpi and runs tesseract.
    With the binary resolvable (`/usr/bin/tesseract` in dev / CI), `txt` is now
    NON-EMPTY and carries the genuine invoice content.

    When the binary is unavailable, OCR degrades gracefully — `txt` is empty and
    no exception is raised — so the flow can fall through to the honest failure.

    Validates: Requirements 2.1, 2.2
    """
    if not FIXTURE.exists():
        pytest.skip(f"OCR fixture not present (optional): {FIXTURE}")

    import pdf_parsing_strategies
    from pdf_parsing_strategies import process_pdf

    # --- With tesseract resolvable: OCR runs and recovers real text. ---
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract binary not available in this environment")

    result = process_pdf(str(FIXTURE), mock_drive_result, mock_config, "netflix")

    # The fix: OCR fallback recovered a non-empty text layer.
    assert result["txt"] != "", (
        "OCR fallback should recover text from the vector-outline PDF"
    )
    # And it is the GENUINE content, not invented — the real total/date appear.
    assert "20.99" in result["txt"] or "20,99" in result["txt"]
    assert "17/09/2026" in result["txt"]
    # Dict shape is unchanged.
    assert result["url"] == mock_drive_result["url"]
    assert result["folder"] == "/test/netflix"

    # --- With tesseract unavailable: OCR degrades gracefully (empty, no raise). ---
    with patch.object(
        pdf_parsing_strategies, "resolve_tesseract_cmd", return_value=None
    ):
        degraded = process_pdf(
            str(FIXTURE), mock_drive_result, mock_config, "netflix"
        )
    assert degraded["txt"] == "", (
        "with no tesseract binary, OCR degrades gracefully to empty text"
    )


@patch("database.DatabaseManager")
@patch("ai_extractor.AIExtractor")
def test_ocr_recovered_text_flows_into_ai_and_parses_real_values(
    mock_ai_class, mock_db_class, mock_config, mock_drive_result
):
    """Fix-Checking — OCR'd text flows into AI extraction and real values are stored.

    On the FIXED code, the OCR-recovered text is fed into the existing AI
    extraction path. The AI boundary is mocked to echo values PARSED FROM the
    OCR'd text (Total 20.99, VAT 3.64, Date 17/09/2026) rather than inventing
    them, and we assert:
      * `AIExtractor.extract_invoice_data` was called with the NON-EMPTY OCR'd
        content (the recovered total appears in the text handed to the model), and
      * the stored transaction carries the REAL 20.99 / 17/09/2026 values, NOT the
        hallucinated 12.99 / 2023-11-15.

    This proves the recovered text (not invented content) drives the parse.

    Validates: Requirements 2.1, 2.2
    """
    if not FIXTURE.exists():
        pytest.skip(f"OCR fixture not present (optional): {FIXTURE}")
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract binary not available in this environment")

    from pdf_parsing_strategies import process_pdf
    from pdf_processor import PDFProcessor

    # Step 1: real OCR recovers the genuine text from the fixture.
    file_data = process_pdf(str(FIXTURE), mock_drive_result, mock_config, "netflix")
    file_data["folder"] = "netflix"
    file_data["name"] = "netflix 202609.pdf"
    assert file_data["txt"] != ""

    # Step 2: the AI boundary echoes values parsed FROM the OCR'd text (not
    # invented), so the test is deterministic but still proves the recovered text
    # drives the parse.
    def _parse_from_text(text, folder, previous):
        assert text.strip(), "AI must never be called on empty content"
        assert "20.99" in text or "20,99" in text, (
            "AI should receive the OCR'd text containing the real total"
        )
        return {
            "date": OCR_DATE,
            "total_amount": OCR_TOTAL,
            "vat_amount": OCR_VAT,
            "description": "Netflix Streaming Service",
            "vendor": "netflix",
            "_usage": {"total_tokens": 0, "model": "deepseek/deepseek-chat"},
        }

    mock_ai = MagicMock()
    mock_ai.extract_invoice_data.side_effect = _parse_from_text
    mock_ai_class.return_value = mock_ai

    mock_db = MagicMock()
    mock_db.get_previous_transactions.return_value = []
    mock_db_class.return_value = mock_db

    with patch("transaction_logic.TransactionLogic") as mock_tl_class:
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = [
            {"Debet": "4000", "Credit": "1300"},
            {"Debet": "2010", "Credit": "4000"},
        ]
        mock_tl_class.return_value = mock_tl

        processor = PDFProcessor()
        transactions = processor.extract_transactions(file_data)

    # The AI model WAS called, and with the non-empty OCR'd content.
    mock_ai.extract_invoice_data.assert_called_once()
    called_text = mock_ai.extract_invoice_data.call_args.args[0]
    assert called_text.strip(), "AI must receive non-empty OCR'd content"
    assert "20.99" in called_text or "20,99" in called_text

    # The stored transaction carries the REAL OCR-recovered values.
    assert len(transactions) >= 1
    main = transactions[0]
    assert main["amount"] == OCR_TOTAL
    assert main["date"] == OCR_DATE
    # And NOT the hallucinated placeholders.
    assert main["amount"] != HALLUCINATED_TOTAL
    assert main["date"] != HALLUCINATED_DATE
    # The positive VAT line is also built from the recovered VAT amount.
    vat = transactions[1]
    assert vat["amount"] == OCR_VAT


def test_tesseract_cmd_resolved_from_environment_in_both_modules():
    """Test case 3 (fixed) — tesseract binary resolved from environment, not Windows.

    On the FIXED code, `pdf_parsing_strategies` resolves the binary via
    `resolve_tesseract_cmd()` (TESSERACT_CMD env var → `shutil.which("tesseract")`
    → None) and sets `pytesseract.tesseract_cmd` only when a path is found —
    never the hardcoded Windows path. `image_ai_processor._try_tesseract` uses the
    same shared resolver. Neither module source contains the Windows path.

    Validates: Requirements 2.5
    """
    import pdf_parsing_strategies

    importlib.reload(pdf_parsing_strategies)

    # The shared resolver prefers TESSERACT_CMD, then PATH, then None — never a
    # hardcoded OS-specific path.
    with patch.dict("os.environ", {"TESSERACT_CMD": "/custom/bin/tesseract"}):
        assert (
            pdf_parsing_strategies.resolve_tesseract_cmd() == "/custom/bin/tesseract"
        )
    with patch.dict("os.environ", {}, clear=True):
        with patch.object(
            pdf_parsing_strategies.shutil, "which", return_value="/usr/bin/tesseract"
        ):
            assert (
                pdf_parsing_strategies.resolve_tesseract_cmd()
                == "/usr/bin/tesseract"
            )
        with patch.object(pdf_parsing_strategies.shutil, "which", return_value=None):
            assert pdf_parsing_strategies.resolve_tesseract_cmd() is None

    # The module-level tesseract_cmd, when set, is whatever the environment
    # resolved to — and never the hardcoded Windows path.
    if pdf_parsing_strategies.pytesseract is not None:
        current_cmd = pdf_parsing_strategies.pytesseract.pytesseract.tesseract_cmd
        assert current_cmd != WINDOWS_TESSERACT_PATH

    # Neither source hardcodes the Windows path; both resolve from the
    # environment (pdf_parsing_strategies via shutil.which, image_ai_processor via
    # the shared resolve_tesseract_cmd).
    pps_source = Path(pdf_parsing_strategies.__file__).read_text(encoding="utf-8")
    assert WINDOWS_TESSERACT_PATH not in pps_source
    assert "shutil.which" in pps_source, (
        "fixed pdf_parsing_strategies resolves the binary from PATH"
    )

    import image_ai_processor

    iap_source = Path(image_ai_processor.__file__).read_text(encoding="utf-8")
    assert WINDOWS_TESSERACT_PATH not in iap_source
    assert "resolve_tesseract_cmd" in iap_source, (
        "fixed image_ai_processor._try_tesseract uses the shared resolver"
    )


@patch("database.DatabaseManager")
@patch("ai_extractor.AIExtractor")
def test_extract_transactions_empty_txt_returns_empty_list_without_calling_ai(
    mock_ai_class, mock_db_class
):
    """Test case 2/4 (fixed) — empty text never reaches the AI and yields no data.

    On the FIXED code, when `txt` is empty, `extract_with_ai` short-circuits
    BEFORE calling `AIExtractor.extract_invoice_data` (honest failure), and
    `extract_transactions` returns an EMPTY list instead of fabricating a
    placeholder transaction. The empty list is what
    `invoice_service._determine_parser_used` maps to `"ai_failed"`, driving the
    UI's explicit "No data found in the file" error.

    This covers both former task-1 cases (2 and 4): the AI is not called on empty
    content, and no placeholder (today's date / 0.0 / "<folder> invoice") is
    produced.

    Validates: Requirements 2.3, 2.4
    """
    from pdf_processor import PDFProcessor

    mock_ai = MagicMock()
    mock_ai_class.return_value = mock_ai

    mock_db = MagicMock()
    mock_db.get_previous_transactions.return_value = []
    mock_db_class.return_value = mock_db

    file_data = {
        "txt": "",  # vector-outline PDF with OCR unavailable -> empty text
        "folder": "netflix",
        "url": "https://drive.google.com/file/d/mock_file_id/view",
        "name": "netflix 202609.pdf",
    }

    with patch("transaction_logic.TransactionLogic") as mock_tl_class:
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = [
            {"Debet": "4000", "Credit": "1300"},
            {"Debet": "2010", "Credit": "4000"},
        ]
        mock_tl_class.return_value = mock_tl

        processor = PDFProcessor()
        transactions = processor.extract_transactions(file_data)

    # The fix: the AI model is NEVER called with empty content.
    mock_ai.extract_invoice_data.assert_not_called()

    # The fix: an empty list is returned (routed to "ai_failed"), not a fabricated
    # placeholder transaction.
    assert transactions == [], (
        "fixed code returns an empty list (-> ai_failed), never a placeholder"
    )


@patch("database.DatabaseManager")
@patch("ai_extractor.AIExtractor")
def test_extract_transactions_ai_error_returns_empty_list_not_placeholder(
    mock_ai_class, mock_db_class
):
    """Test case 4 (fixed) — AI error on recovered-but-unusable text yields no data.

    When OCR recovers some text but the AI extraction fails outright (raises),
    `extract_with_ai` returns None, and `extract_transactions` returns an EMPTY
    list rather than fabricating `failure_data` (today's date / 0.0 /
    "<folder> invoice"). The empty list routes to `"ai_failed"`.

    Validates: Requirements 2.3, 2.4
    """
    from pdf_processor import PDFProcessor

    # AI raises -> extract_with_ai returns None -> no positive amount -> [].
    mock_ai = MagicMock()
    mock_ai.extract_invoice_data.side_effect = RuntimeError("API error")
    mock_ai_class.return_value = mock_ai

    mock_db = MagicMock()
    mock_db.get_previous_transactions.return_value = []
    mock_db_class.return_value = mock_db

    file_data = {
        "txt": "Some OCR'd text the AI could not turn into an invoice",
        "folder": "netflix",
        "url": "https://drive.google.com/file/d/mock_file_id/view",
        "name": "netflix 202609.pdf",
    }

    with patch("transaction_logic.TransactionLogic") as mock_tl_class:
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = [
            {"Debet": "4000", "Credit": "1300"},
            {"Debet": "2010", "Credit": "4000"},
        ]
        mock_tl_class.return_value = mock_tl

        processor = PDFProcessor()
        transactions = processor.extract_transactions(file_data)

    # Non-empty text was handed to the AI (it is allowed to try) ...
    mock_ai.extract_invoice_data.assert_called_once()
    # ... but on failure the fix returns an empty list, not a placeholder.
    assert transactions == [], (
        "AI error must route to ai_failed (empty list), not fabricated data"
    )
