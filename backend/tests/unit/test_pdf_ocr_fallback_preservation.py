r"""
Preservation property tests for the PDF OCR-fallback bugfix.

Feature: pdf-text-extraction-ocr-fallback (bugfix spec)
Property 2: Preservation — text-layer PDFs and all non-PDF files behave
identically after the fix, and OCR never fires when text extraction already
yields text.

OBSERVATION-FIRST METHODOLOGY
-----------------------------
These tests observe behavior on the UNFIXED code first and encode it as
invariants that must STILL hold after task 3 applies the fix. The file is
designed to be GREEN-OR-XFAIL on the unfixed code:

  * BASELINE assertions (must already pass on the unfixed code) — these pin the
    existing behavior the fix must preserve:
      - 2a: `process_pdf` on a text-layer PDF returns the extracted `txt`
            (observed value recorded as the baseline to preserve).
      - 2b: `process_image` / `process_csv` / `process_mhtml` / `process_eml`
            produce their current results for representative non-PDF inputs.
      - 2c: `extract_transactions` builds the usual main (+ VAT) transactions
            when the AI returns a positive `total_amount`.

  * POST-FIX assertions — these reference `pdf_parsing_strategies.ocr_pdf_pages`
    and `pdf_parsing_strategies.resolve_tesseract_cmd`, introduced by task 3:
      - 2a (OCR-never-fires spy): the spy must observe ZERO calls for a
            text-layer PDF (OCR fires only when `txt` is empty).
      - 2d (resolver dev-path): `resolve_tesseract_cmd()` resolves
            TESSERACT_CMD -> PATH -> None, never a hardcoded Windows path.

These assertions were authored as `xfail` while the symbols did not yet exist on
the unfixed code; now that task 3 has introduced them and the behavior holds,
the obsolete xfail markers have been removed (task 3.6) so the tests assert
cleanly as plain passes.

Repo conventions: `@pytest.mark.unit` auto-applied by the `tests/unit/`
directory; `test_{function}_{scenario}_{expected}` naming; no real DB
connections, no `mysql.connector`, no `load_dotenv()`. External boundaries
(storage/Drive, DatabaseManager, TransactionLogic, AIExtractor, ImageAIProcessor)
are mocked. Hypothesis uses `@settings(max_examples=..., deadline=None)`.
"""

from unittest.mock import MagicMock, patch

# PyMuPDF is the committed OCR-rendering dependency and is also the most
# convenient way to synthesize a *text-layer* PDF fixture in-memory (reportlab /
# fpdf are not installed). We only use it here to BUILD a text PDF so the
# text-layer extraction path (pypdf) has something to read.
import pymupdf
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_text_pdf_bytes(text: str) -> bytes:
    """Build a minimal single-page PDF with a real selectable text layer.

    Produces a PDF that `pypdf`/`pdfplumber` can read directly (unlike the
    vector-outline "Microsoft: Print To PDF" bug-condition fixture), so the
    text-layer path in `process_pdf` yields non-empty text and OCR must never
    be consulted.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    # Lay the text out over several lines so multi-line extraction is exercised.
    y = 72
    for line in text.split("\n"):
        page.insert_text((72, y), line)
        y += 18
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def text_pdf_path(tmp_path):
    """Path to a freshly written text-layer PDF fixture."""
    pdf_path = tmp_path / "text_layer_invoice.pdf"
    pdf_path.write_bytes(
        _make_text_pdf_bytes("Invoice from ACME\nTotal 42.00\nVAT 7.00")
    )
    return str(pdf_path)


@pytest.fixture
def mock_config():
    """A Config stand-in so process_* functions touch no real storage folders."""
    config = MagicMock()
    config.get_storage_folder.return_value = "/test/acme"
    config.ensure_folder_exists.return_value = None
    return config


@pytest.fixture
def mock_drive_result():
    """A Google Drive upload result stand-in (no real Drive call)."""
    return {
        "id": "mock_file_id",
        "url": "https://drive.google.com/file/d/mock_file_id/view",
    }


# ---------------------------------------------------------------------------
# Strategies (reused shape from tests/unit/test_pdf_processor_properties.py)
# ---------------------------------------------------------------------------

# Folder names that do NOT match a CSV rule (no "airbnb" substring) so the AI
# path is exercised.
folder_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
).filter(lambda s: "airbnb" not in s.lower())

# Non-empty text content (the preservation invariant for 2a: OCR never fires
# when text is non-empty).
nonempty_text_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=120,
).filter(lambda s: s.strip() != "")

valid_amount_st = st.floats(
    min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False
)
valid_vat_st = st.floats(
    min_value=0.0, max_value=50000.0, allow_nan=False, allow_infinity=False
)
valid_date_st = st.dates().map(lambda d: d.strftime("%Y-%m-%d"))
valid_description_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=100,
)
valid_vendor_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
)


def _extract_tx_with_positive_ai(file_data, ai_result):
    """Run extract_transactions with a positive-amount AI result mocked in.

    Mirrors the mock wiring in tests/unit/test_pdf_processor_properties.py so
    the preservation assertions compare against the exact transaction shape the
    current code builds.
    """
    from pdf_processor import PDFProcessor

    with (
        patch("ai_extractor.AIExtractor") as mock_ai_class,
        patch("database.DatabaseManager") as mock_db_class,
        patch("transaction_logic.TransactionLogic") as mock_tl_class,
    ):
        mock_ai = MagicMock()
        mock_ai.extract_invoice_data.return_value = ai_result
        mock_ai_class.return_value = mock_ai

        mock_db = MagicMock()
        mock_db.get_previous_transactions.return_value = []
        mock_db_class.return_value = mock_db

        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = {
            "error": True,
            "message": "no history",
        }
        mock_tl_class.return_value = mock_tl

        processor = PDFProcessor()
        return processor.extract_transactions(file_data)


# ===========================================================================
# Property test 2a — text PDF preservation + OCR never fires
# Validates: Requirements 3.1, 3.2
# ===========================================================================


class TestTextPdfPreservation:
    """2a — a text-layer PDF extracts via pypdf/pdfplumber; OCR must not fire."""

    def test_process_pdf_text_layer_returns_extracted_text_baseline(
        self, text_pdf_path, mock_config, mock_drive_result
    ):
        """BASELINE (passes on UNFIXED code).

        A text-layer PDF yields non-empty `txt` from the existing
        pypdf -> pdfplumber path. This is the observed behavior the fix must
        preserve byte-for-byte; OCR is additive and must never alter it.

        Validates: Requirements 3.1, 3.2
        """
        from pdf_parsing_strategies import process_pdf

        result = process_pdf(text_pdf_path, mock_drive_result, mock_config, "acme")

        # Observed baseline: the text layer is recovered (non-empty, carrying the
        # content we wrote). The exact text must be identical after the fix.
        assert result["txt"] != ""
        assert "Invoice from ACME" in result["txt"]
        assert "Total 42.00" in result["txt"]
        # Dict shape preserved.
        assert result["name"] == mock_drive_result["id"]
        assert result["url"] == mock_drive_result["url"]
        assert result["folder"] == "/test/acme"

    def test_process_pdf_text_layer_never_invokes_ocr(
        self, text_pdf_path, mock_config, mock_drive_result
    ):
        """With a text-layer PDF, text extraction already yields text, so the new
        OCR fallback helper must NEVER be called (preservation invariant: OCR
        fires only for bug-condition inputs where `txt` is empty).

        Validates: Requirements 3.1, 3.2
        """
        import pdf_parsing_strategies

        with patch.object(pdf_parsing_strategies, "ocr_pdf_pages") as spy_ocr:
            result = pdf_parsing_strategies.process_pdf(
                text_pdf_path, mock_drive_result, mock_config, "acme"
            )

        assert result["txt"] != ""
        spy_ocr.assert_not_called()

    @settings(max_examples=25, deadline=None)
    @given(content=nonempty_text_st)
    def test_process_pdf_nonempty_text_never_invokes_ocr_property(self, content):
        """For ANY non-empty text content, `process_pdf` must never invoke
        `ocr_pdf_pages` — OCR is guarded behind an empty-text condition. This is
        the universal preservation invariant Hypothesis is best suited to.

        Validates: Requirements 3.1, 3.2
        """
        import pdf_parsing_strategies

        config = MagicMock()
        config.get_storage_folder.return_value = "/test/acme"
        config.ensure_folder_exists.return_value = None
        drive_result = {"id": "fid", "url": "https://drive.example/fid"}

        # Patch pypdf's reader so extraction deterministically yields the content
        # (independent of glyph rendering), then assert OCR is never consulted.
        fake_page = MagicMock()
        fake_page.extract_text.return_value = content
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page]

        with (
            patch.object(pdf_parsing_strategies, "ocr_pdf_pages") as spy_ocr,
            patch("pdf_parsing_strategies.PdfReader", return_value=fake_reader),
            patch("builtins.open", MagicMock()),
        ):
            result = pdf_parsing_strategies.process_pdf(
                "ignored.pdf", drive_result, config, "acme"
            )

        assert result["txt"] != ""
        spy_ocr.assert_not_called()


# ===========================================================================
# Property test 2b — non-PDF preservation
# Validates: Requirements 3.3
# ===========================================================================


class TestNonPdfPreservation:
    """2b — image / csv / mhtml / eml paths are unchanged by the PDF OCR fix."""

    def test_process_image_result_unchanged_baseline(
        self, tmp_path, mock_config, mock_drive_result
    ):
        """BASELINE (passes on UNFIXED code).

        `process_image` routes through ImageAIProcessor and formats the AI/OCR
        result into the standard dict. Mocking ImageAIProcessor (as in
        test_image_ai_processor.py) pins the exact observable output the fix
        must preserve.

        Validates: Requirements 3.3
        """
        import pdf_parsing_strategies

        img_path = tmp_path / "receipt.png"
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        ai_data = {
            "date": "2024-06-15",
            "total_amount": 99.50,
            "vat_amount": 17.31,
            "description": "INV-001",
            "vendor": "TestVendor",
        }

        with (
            patch.object(
                pdf_parsing_strategies, "ImageAIProcessor", create=True
            ) as mock_proc_class,
            patch("database.DatabaseManager") as mock_db_class,
        ):
            # process_image imports ImageAIProcessor and DatabaseManager inside
            # the function body; patch where they are looked up.
            mock_proc = MagicMock()
            mock_proc.process_image.return_value = ai_data
            mock_proc_class.return_value = mock_proc

            mock_db = MagicMock()
            mock_db.get_previous_transactions.return_value = []
            mock_db_class.return_value = mock_db

            with patch("image_ai_processor.ImageAIProcessor", return_value=mock_proc):
                result = pdf_parsing_strategies.process_image(
                    str(img_path), mock_drive_result, mock_config, "TestVendor"
                )

        # Observed baseline shape: formatted text lines + ai_data passthrough.
        assert result["name"] == mock_drive_result["id"]
        assert result["url"] == mock_drive_result["url"]
        assert result["folder"] == "/test/acme"
        assert result["ai_data"] == ai_data
        assert "[AI/OCR Extracted Data]" in result["txt"]
        assert "Total Amount: €99.50" in result["txt"]
        assert "Vendor: TestVendor" in result["txt"]

    def test_process_csv_result_unchanged_baseline(
        self, tmp_path, mock_config, mock_drive_result
    ):
        """BASELINE (passes on UNFIXED code).

        `process_csv` summarizes a CSV into text lines + an embedded JSON block.
        The PDF OCR fix must not touch this path.

        Validates: Requirements 3.3
        """
        from pdf_parsing_strategies import process_csv

        csv_path = tmp_path / "airbnb_tax.csv"
        csv_path.write_text("date,amount\n2024-01-01,10.00\n2024-02-01,20.00\n")

        result = process_csv(str(csv_path), mock_drive_result, mock_config, "airbnb")

        assert result["name"] == mock_drive_result["id"]
        assert result["url"] == mock_drive_result["url"]
        assert result["folder"] == "/test/acme"
        assert "[CSV File: airbnb_tax.csv]" in result["txt"]
        assert "[CSV_DATA_START]" in result["txt"]
        assert "[CSV_DATA_END]" in result["txt"]

    def test_process_mhtml_result_unchanged_baseline(
        self, tmp_path, mock_config, mock_drive_result
    ):
        """BASELINE (passes on UNFIXED code).

        `process_mhtml` strips HTML tags and summarizes. Unchanged by the fix.

        Validates: Requirements 3.3
        """
        from pdf_parsing_strategies import process_mhtml

        mhtml_path = tmp_path / "order.mhtml"
        mhtml_path.write_text(
            "<html><body><p>Order confirmation</p>"
            "<strong>12</strong> some text <strong>99</strong>"
            "</body></html>",
            encoding="utf-8",
        )

        result = process_mhtml(
            str(mhtml_path), mock_drive_result, mock_config, "picnic"
        )

        assert result["name"] == mock_drive_result["id"]
        assert result["url"] == mock_drive_result["url"]
        assert result["folder"] == "/test/acme"
        assert "[MHTML Email: order.mhtml]" in result["txt"]
        assert "Order confirmation" in result["txt"]

    def test_process_eml_result_unchanged_baseline(
        self, tmp_path, mock_config, mock_drive_result
    ):
        """BASELINE (passes on UNFIXED code).

        `process_eml` extracts the plain-text part and summarizes. Unchanged by
        the fix.

        Validates: Requirements 3.3
        """
        from pdf_parsing_strategies import process_eml

        eml_path = tmp_path / "order.eml"
        eml_path.write_text(
            "Content-Type: text/plain\n\n"
            "Order 12345-6789\n"
            "Totaal ---- 25.00\n"
            "Thank you for your order\n",
            encoding="utf-8",
        )

        result = process_eml(str(eml_path), mock_drive_result, mock_config, "picnic")

        assert result["name"] == mock_drive_result["id"]
        assert result["url"] == mock_drive_result["url"]
        assert result["folder"] == "/test/acme"
        assert "[EML Email: order.eml]" in result["txt"]
        assert "Thank you for your order" in result["txt"]


# ===========================================================================
# Property test 2c — positive-amount success preservation
# Validates: Requirements 3.4
# ===========================================================================


class TestPositiveAmountSuccessPreservation:
    """2c — positive AI total builds the same main (+ VAT) transactions."""

    @settings(max_examples=30, deadline=None)
    @given(
        folder_name=folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=valid_vat_st,
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_extract_transactions_positive_amount_builds_main_tx_baseline(
        self, folder_name, total_amount, vat_amount, date, description, vendor
    ):
        """BASELINE (passes on UNFIXED code).

        For any AI result with total_amount > 0, `extract_transactions` builds a
        main transaction carrying the AI date / amount / description and the
        folder as `ref`. This success path must remain untouched by the fix.

        Validates: Requirements 3.4
        """
        rounded_total = round(total_amount, 2)
        ai_result = {
            "date": date,
            "total_amount": rounded_total,
            "vat_amount": round(vat_amount, 2),
            "description": description,
            "vendor": vendor,
            "_usage": {"total_tokens": 0, "model": "test"},
        }
        file_data = {
            "txt": "Some invoice text content",
            "folder": folder_name,
            "url": "https://drive.google.com/test",
            "name": "test-file-id",
        }

        result = _extract_tx_with_positive_ai(file_data, ai_result)

        assert isinstance(result, list)
        assert len(result) >= 1
        main = result[0]
        assert main["date"] == date
        assert float(main["amount"]) == rounded_total
        assert main["description"] == description
        assert main["ref"] == folder_name

    @settings(max_examples=30, deadline=None)
    @given(
        folder_name=folder_name_st,
        total_amount=valid_amount_st,
        vat_amount=st.floats(
            min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False
        ),
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_extract_transactions_positive_vat_builds_vat_tx_baseline(
        self, folder_name, total_amount, vat_amount, date, description, vendor
    ):
        """BASELINE (passes on UNFIXED code).

        When vat_amount > 0, a second (VAT) transaction is appended carrying the
        VAT amount. Preserved by the fix.

        Validates: Requirements 3.4
        """
        rounded_vat = round(vat_amount, 2)
        ai_result = {
            "date": date,
            "total_amount": round(total_amount, 2),
            "vat_amount": rounded_vat,
            "description": description,
            "vendor": vendor,
            "_usage": {"total_tokens": 0, "model": "test"},
        }
        file_data = {
            "txt": "Some invoice text content",
            "folder": folder_name,
            "url": "https://drive.google.com/test",
            "name": "test-file-id",
        }

        result = _extract_tx_with_positive_ai(file_data, ai_result)

        assert isinstance(result, list)
        assert len(result) >= 2, "main + VAT expected when vat_amount > 0"
        vat_tx = result[1]
        assert float(vat_tx["amount"]) == rounded_vat
        assert vat_tx["description"] == f"VAT - {description}"

    @settings(max_examples=30, deadline=None)
    @given(
        folder_name=folder_name_st,
        total_amount=valid_amount_st,
        date=valid_date_st,
        description=valid_description_st,
        vendor=valid_vendor_st,
    )
    def test_extract_transactions_zero_vat_builds_single_tx_baseline(
        self, folder_name, total_amount, date, description, vendor
    ):
        """BASELINE (passes on UNFIXED code).

        When vat_amount == 0, NO VAT transaction is appended (only the main tx).
        Preserved by the fix.

        Validates: Requirements 3.4
        """
        ai_result = {
            "date": date,
            "total_amount": round(total_amount, 2),
            "vat_amount": 0.0,
            "description": description,
            "vendor": vendor,
            "_usage": {"total_tokens": 0, "model": "test"},
        }
        file_data = {
            "txt": "Some invoice text content",
            "folder": folder_name,
            "url": "https://drive.google.com/test",
            "name": "test-file-id",
        }

        result = _extract_tx_with_positive_ai(file_data, ai_result)

        assert isinstance(result, list)
        assert len(result) == 1, "no VAT tx when vat_amount == 0"


# ===========================================================================
# Property test 2d — resolver dev-path preservation
# Validates: Requirements 3.1, 3.2
#
# resolve_tesseract_cmd() was introduced at task 3.1; these assertions now
# verify its env-var -> PATH -> None resolution directly.
# ===========================================================================


class TestResolverDevPathPreservation:
    """2d — resolve_tesseract_cmd(): env var -> PATH -> None (never Windows)."""

    def test_resolve_tesseract_cmd_env_unset_path_present_returns_path_binary(
        self,
    ):
        """With TESSERACT_CMD unset and `tesseract` on PATH, the resolver returns
        the PATH binary (dev behavior: /usr/bin/tesseract).

        Validates: Requirements 3.1, 3.2
        """
        import pdf_parsing_strategies

        resolve = pdf_parsing_strategies.resolve_tesseract_cmd

        with patch.dict("os.environ", {}, clear=False) as _env:
            # Ensure the env var is absent for this check.
            import os

            os.environ.pop("TESSERACT_CMD", None)
            with patch(
                "pdf_parsing_strategies.shutil.which",
                return_value="/usr/bin/tesseract",
            ):
                assert resolve() == "/usr/bin/tesseract"

    def test_resolve_tesseract_cmd_env_set_returns_env_value(self):
        """TESSERACT_CMD takes precedence over PATH. Never a hardcoded Windows path.

        Validates: Requirements 3.1, 3.2
        """
        import pdf_parsing_strategies

        resolve = pdf_parsing_strategies.resolve_tesseract_cmd

        with (
            patch.dict(
                "os.environ", {"TESSERACT_CMD": "/opt/tess/tesseract"}, clear=False
            ),
            patch(
                "pdf_parsing_strategies.shutil.which",
                return_value="/usr/bin/tesseract",
            ),
        ):
            resolved = resolve()
        assert resolved == "/opt/tess/tesseract"
        assert "Program Files" not in resolved

    def test_resolve_tesseract_cmd_neither_present_returns_none_no_raise(self):
        """With neither TESSERACT_CMD nor a PATH binary, the resolver returns None
        WITHOUT raising, so non-OCR paths are unaffected.

        Validates: Requirements 3.1, 3.2
        """
        import pdf_parsing_strategies

        resolve = pdf_parsing_strategies.resolve_tesseract_cmd

        import os

        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("TESSERACT_CMD", None)
            with patch("pdf_parsing_strategies.shutil.which", return_value=None):
                assert resolve() is None
