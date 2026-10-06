"""
Focused example-based unit tests for the PDF OCR-fallback bugfix helpers and the
failure channel.

Feature: pdf-text-extraction-ocr-fallback (bugfix spec), task 4.

These are DISTINCT from:
  * test_pdf_ocr_fallback_bug_condition.py — Property 1 fix-checking against the
    real `netflix 202609.pdf` fixture (needs the tesseract binary), and
  * test_pdf_ocr_fallback_preservation.py — Property 2 Hypothesis preservation.

Here we drive each new helper in isolation with mocks — no real tesseract binary,
no real PDF rendering, no real DB — so they run deterministically everywhere:

  * resolve_tesseract_cmd()  — env var vs PATH vs None resolution; never a
    hardcoded Windows path.                                   (Req 2.5)
  * ocr_pdf_pages()          — graceful [] when the binary is absent or the
    optional deps import fails; happy-path line collection with mocked
    pymupdf + pytesseract.                                    (Req 2.1, 2.6)
  * extract_with_ai()        — honest short-circuit: empty/whitespace lines never
    reach AIExtractor; non-empty lines do.                    (Req 2.3)
  * _determine_parser_used() — on BOTH invoice_service and invoice_test_service,
    an empty transaction list maps to "ai_failed" (the channel that drives the UI
    "No data found in the file" error).                       (Req 2.4)

`@pytest.mark.unit` is auto-applied by the `tests/unit/` directory. No real DB
connections, no `mysql.connector`, no `load_dotenv()` — all external boundaries
are mocked.
"""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# The hardcoded Windows path the UNFIXED code used. The fix must NEVER return it.
WINDOWS_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ── resolve_tesseract_cmd ──────────────────────────────────────────────────


class TestResolveTesseractCmd:
    """resolve_tesseract_cmd() resolves TESSERACT_CMD -> PATH -> None, never a
    hardcoded Windows path. Validates: Requirements 2.5"""

    def test_resolve_tesseract_cmd_env_var_set_returns_env_value(self):
        import pdf_parsing_strategies as pps

        # which() must not even be consulted when the env var wins.
        with patch.dict("os.environ", {"TESSERACT_CMD": "/opt/bin/tesseract"}), patch.object(
            pps.shutil, "which", return_value="/usr/bin/tesseract"
        ):
            result = pps.resolve_tesseract_cmd()

        assert result == "/opt/bin/tesseract"
        assert result != WINDOWS_TESSERACT_PATH

    def test_resolve_tesseract_cmd_env_unset_binary_on_path_returns_which(self):
        import pdf_parsing_strategies as pps

        with patch.dict("os.environ", {}, clear=True), patch.object(
            pps.shutil, "which", return_value="/usr/bin/tesseract"
        ):
            result = pps.resolve_tesseract_cmd()

        assert result == "/usr/bin/tesseract"
        assert result != WINDOWS_TESSERACT_PATH

    def test_resolve_tesseract_cmd_env_unset_binary_absent_returns_none(self):
        import pdf_parsing_strategies as pps

        with patch.dict("os.environ", {}, clear=True), patch.object(
            pps.shutil, "which", return_value=None
        ):
            result = pps.resolve_tesseract_cmd()

        assert result is None

    def test_resolve_tesseract_cmd_empty_env_var_falls_through_to_path(self):
        """An empty TESSERACT_CMD is falsy -> fall through to PATH, not a crash."""
        import pdf_parsing_strategies as pps

        with patch.dict("os.environ", {"TESSERACT_CMD": ""}), patch.object(
            pps.shutil, "which", return_value="/usr/bin/tesseract"
        ):
            result = pps.resolve_tesseract_cmd()

        assert result == "/usr/bin/tesseract"

    def test_resolve_tesseract_cmd_never_returns_windows_path(self):
        """Across all resolution branches, the hardcoded Windows path never appears."""
        import pdf_parsing_strategies as pps

        for env, which_val in (
            ({"TESSERACT_CMD": "/a/tesseract"}, None),
            ({}, "/usr/bin/tesseract"),
            ({}, None),
        ):
            with patch.dict("os.environ", env, clear=True), patch.object(
                pps.shutil, "which", return_value=which_val
            ):
                assert pps.resolve_tesseract_cmd() != WINDOWS_TESSERACT_PATH


# ── ocr_pdf_pages ───────────────────────────────────────────────────────────


class TestOcrPdfPages:
    """ocr_pdf_pages() recovers lines on the happy path and degrades to [] (never
    raising) when the binary or optional deps are unavailable.
    Validates: Requirements 2.1, 2.6"""

    def test_ocr_pdf_pages_no_binary_returns_empty_without_raising(self):
        """resolve_tesseract_cmd() -> None short-circuits to [] (graceful degrade)."""
        import pdf_parsing_strategies as pps

        with patch.object(pps, "resolve_tesseract_cmd", return_value=None):
            result = pps.ocr_pdf_pages("/some/vector-outline.pdf")

        assert result == []

    def test_ocr_pdf_pages_import_failure_returns_empty_without_raising(self):
        """A missing optional dep (pymupdf/pytesseract/PIL) degrades to [], no raise.

        The helper imports pymupdf (falling back to `import fitz`) and then
        pytesseract/PIL inside a try. Forcing every candidate import to raise
        ImportError exercises the degrade-gracefully branch deterministically,
        regardless of which deps happen to be installed.
        """
        import builtins

        import pdf_parsing_strategies as pps

        real_import = builtins.__import__

        def _fail_optional(name, *args, **kwargs):
            if name in ("pymupdf", "fitz", "pytesseract") or name.startswith("PIL"):
                raise ImportError(f"simulated missing dependency: {name}")
            return real_import(name, *args, **kwargs)

        with patch.object(
            pps, "resolve_tesseract_cmd", return_value="/usr/bin/tesseract"
        ), patch.object(builtins, "__import__", side_effect=_fail_optional):
            result = pps.ocr_pdf_pages("/some/vector-outline.pdf")

        assert result == []

    def test_ocr_pdf_pages_happy_path_returns_collected_nonempty_lines(self):
        """With mocked pymupdf + pytesseract, non-empty OCR lines are collected.

        We inject fake `pymupdf` and `pytesseract` modules into sys.modules so the
        helper's in-function imports pick them up. Two pages return canned text
        with blank lines interleaved; only the non-empty lines survive.
        """
        import pdf_parsing_strategies as pps

        # --- fake pytesseract: one canned string per page call ---
        fake_pytesseract = MagicMock()
        fake_pytesseract.image_to_string.side_effect = [
            "Netflix International B.V.\n\nTotal: 20.99",  # page 1 (blank line dropped)
            "VAT 21%: 3.64\n   \nReceipt No. 37C58",       # page 2 (whitespace line dropped)
        ]

        # --- fake pymupdf: context-manager doc yielding two pages ---
        def _make_page():
            page = MagicMock()
            pixmap = MagicMock()
            pixmap.tobytes.return_value = b"\x89PNG-fake-bytes"
            page.get_pixmap.return_value = pixmap
            return page

        fake_doc = MagicMock()
        fake_doc.__iter__.return_value = iter([_make_page(), _make_page()])
        fake_doc.__enter__.return_value = fake_doc
        fake_doc.__exit__.return_value = False

        fake_pymupdf = MagicMock()
        fake_pymupdf.open.return_value = fake_doc

        # --- fake PIL.Image.open so we never touch real image bytes ---
        fake_pil = MagicMock()
        fake_pil.Image.open.return_value = MagicMock()

        modules = {
            "pymupdf": fake_pymupdf,
            "pytesseract": fake_pytesseract,
            "PIL": fake_pil,
            "PIL.Image": fake_pil.Image,
        }

        with patch.object(
            pps, "resolve_tesseract_cmd", return_value="/usr/bin/tesseract"
        ), patch.dict(sys.modules, modules):
            result = pps.ocr_pdf_pages("/some/vector-outline.pdf")

        # Only the non-empty lines across both pages are returned, in order.
        assert result == [
            "Netflix International B.V.",
            "Total: 20.99",
            "VAT 21%: 3.64",
            "Receipt No. 37C58",
        ]
        # pymupdf.open was given the file path; the pixmap was rendered at 300 dpi.
        fake_pymupdf.open.assert_called_once_with("/some/vector-outline.pdf")

    def test_ocr_pdf_pages_pixmap_uses_300_dpi(self):
        """Each page is rasterized with get_pixmap(dpi=300) per the design."""
        import pdf_parsing_strategies as pps

        fake_pytesseract = MagicMock()
        fake_pytesseract.image_to_string.return_value = "line"

        page = MagicMock()
        pixmap = MagicMock()
        pixmap.tobytes.return_value = b"png"
        page.get_pixmap.return_value = pixmap

        fake_doc = MagicMock()
        fake_doc.__iter__.return_value = iter([page])
        fake_doc.__enter__.return_value = fake_doc
        fake_doc.__exit__.return_value = False

        fake_pymupdf = MagicMock()
        fake_pymupdf.open.return_value = fake_doc

        fake_pil = MagicMock()
        fake_pil.Image.open.return_value = MagicMock()

        modules = {
            "pymupdf": fake_pymupdf,
            "pytesseract": fake_pytesseract,
            "PIL": fake_pil,
            "PIL.Image": fake_pil.Image,
        }

        with patch.object(
            pps, "resolve_tesseract_cmd", return_value="/usr/bin/tesseract"
        ), patch.dict(sys.modules, modules):
            pps.ocr_pdf_pages("/some.pdf")

        page.get_pixmap.assert_called_once_with(dpi=300)
        pixmap.tobytes.assert_called_once_with("png")

    def test_ocr_pdf_pages_per_page_error_is_isolated_other_pages_survive(self):
        """A single page that fails to render is logged and skipped — the
        remaining pages still contribute their recovered lines (no raise)."""
        import pdf_parsing_strategies as pps

        # Page 1 raises on get_pixmap; page 2 renders fine.
        bad_page = MagicMock()
        bad_page.get_pixmap.side_effect = RuntimeError("render failed")

        good_pixmap = MagicMock()
        good_pixmap.tobytes.return_value = b"png"
        good_page = MagicMock()
        good_page.get_pixmap.return_value = good_pixmap

        fake_pytesseract = MagicMock()
        fake_pytesseract.image_to_string.return_value = "Recovered line"

        fake_doc = MagicMock()
        fake_doc.__iter__.return_value = iter([bad_page, good_page])
        fake_doc.__enter__.return_value = fake_doc
        fake_doc.__exit__.return_value = False

        fake_pymupdf = MagicMock()
        fake_pymupdf.open.return_value = fake_doc

        fake_pil = MagicMock()
        fake_pil.Image.open.return_value = MagicMock()

        modules = {
            "pymupdf": fake_pymupdf,
            "pytesseract": fake_pytesseract,
            "PIL": fake_pil,
            "PIL.Image": fake_pil.Image,
        }

        with patch.object(
            pps, "resolve_tesseract_cmd", return_value="/usr/bin/tesseract"
        ), patch.dict(sys.modules, modules):
            result = pps.ocr_pdf_pages("/mixed.pdf")

        # The bad page is skipped; the good page's line is still returned.
        assert result == ["Recovered line"]

    def test_ocr_pdf_pages_open_error_returns_empty_without_raising(self):
        """If pymupdf.open raises, the helper returns [] instead of propagating."""
        import pdf_parsing_strategies as pps

        fake_pymupdf = MagicMock()
        fake_pymupdf.open.side_effect = RuntimeError("corrupt pdf")

        fake_pil = MagicMock()
        modules = {
            "pymupdf": fake_pymupdf,
            "pytesseract": MagicMock(),
            "PIL": fake_pil,
            "PIL.Image": fake_pil.Image,
        }

        with patch.object(
            pps, "resolve_tesseract_cmd", return_value="/usr/bin/tesseract"
        ), patch.dict(sys.modules, modules):
            result = pps.ocr_pdf_pages("/broken.pdf")

        assert result == []

    def test_ocr_pdf_pages_bytesio_available(self):
        """Sanity: the module uses io.BytesIO for the PNG round-trip (import present)."""
        import pdf_parsing_strategies as pps

        # io is imported at module level and used to wrap the pixmap PNG bytes.
        assert pps.io is io


# ── extract_with_ai honest short-circuit ───────────────────────────────────


class TestExtractWithAiHonestShortCircuit:
    """extract_with_ai() must never hand empty/whitespace content to the AI model.
    Validates: Requirements 2.3"""

    @patch("database.DatabaseManager")
    @patch("ai_extractor.AIExtractor")
    def test_extract_with_ai_empty_lines_does_not_call_ai_returns_none(
        self, mock_ai_class, mock_db_class
    ):
        from pdf_ai_extraction import extract_with_ai

        mock_ai = MagicMock()
        mock_ai_class.return_value = mock_ai

        result = extract_with_ai([], "netflix")

        assert result is None
        mock_ai.extract_invoice_data.assert_not_called()
        # The extractor should not even be constructed on the short-circuit path.
        mock_ai_class.assert_not_called()

    @patch("database.DatabaseManager")
    @patch("ai_extractor.AIExtractor")
    def test_extract_with_ai_whitespace_only_lines_does_not_call_ai_returns_none(
        self, mock_ai_class, mock_db_class
    ):
        from pdf_ai_extraction import extract_with_ai

        mock_ai = MagicMock()
        mock_ai_class.return_value = mock_ai

        # Lines that join to pure whitespace must be treated as empty.
        result = extract_with_ai(["", "   ", "\t", "\n"], "netflix")

        assert result is None
        mock_ai.extract_invoice_data.assert_not_called()

    @patch("database.DatabaseManager")
    @patch("ai_extractor.AIExtractor")
    def test_extract_with_ai_nonempty_lines_calls_ai(self, mock_ai_class, mock_db_class):
        """Sanity: non-empty content IS handed to the AI model."""
        from pdf_ai_extraction import extract_with_ai

        mock_ai = MagicMock()
        mock_ai.extract_invoice_data.return_value = {
            "total_amount": 20.99,
            "vendor": "netflix",
            "_usage": {"total_tokens": 10, "model": "test"},
        }
        mock_ai_class.return_value = mock_ai
        mock_db_class.return_value.get_previous_transactions.return_value = []

        result = extract_with_ai(["Netflix", "Total: 20.99"], "netflix")

        assert result is not None
        assert result["total_amount"] == 20.99
        mock_ai.extract_invoice_data.assert_called_once()
        # The content handed to the model is the non-empty joined text.
        called_text = mock_ai.extract_invoice_data.call_args.args[0]
        assert called_text.strip()
        assert "20.99" in called_text


# ── failure channel: _determine_parser_used -> "ai_failed" ──────────────────


@pytest.fixture
def invoice_service():
    """InvoiceService with all DB-touching collaborators mocked at import."""
    with patch("services.invoice_service.DatabaseManager"), patch(
        "services.invoice_service.PDFProcessor"
    ), patch("services.invoice_service.TransactionLogic"):
        from services.invoice_service import InvoiceService

        return InvoiceService()


@pytest.fixture
def invoice_test_service():
    """InvoiceTestService with its PDFProcessor collaborator mocked at import."""
    with patch("services.invoice_test_service.PDFProcessor"), patch(
        "services.invoice_test_service.CsvRuleEngine"
    ):
        from services.invoice_test_service import InvoiceTestService

        return InvoiceTestService()


class TestFailureChannelAiFailed:
    """Both services route an empty transaction list to "ai_failed" — the channel
    that drives the UI "No data found in the file" error.
    Validates: Requirements 2.4"""

    def test_invoice_service_determine_parser_used_empty_list_returns_ai_failed(
        self, invoice_service
    ):
        result = {"folder": "netflix", "txt": ""}

        parser_used = invoice_service._determine_parser_used([], result)

        assert parser_used == "ai_failed"

    def test_invoice_test_service_determine_parser_used_empty_list_returns_ai_failed(
        self, invoice_test_service
    ):
        file_data = {"folder": "netflix", "txt": ""}

        parser_used = invoice_test_service._determine_parser_used([], file_data)

        assert parser_used == "ai_failed"

    def test_both_services_agree_on_ai_failed_for_empty_list(
        self, invoice_service, invoice_test_service
    ):
        """The two parallel implementations must classify the empty list the same
        way, so production and the dry-run test tool surface the same failure."""
        result = {"folder": "netflix", "txt": ""}

        assert (
            invoice_service._determine_parser_used([], result)
            == invoice_test_service._determine_parser_used([], result)
            == "ai_failed"
        )
