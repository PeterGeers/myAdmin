"""
Property-based (Hypothesis) tests for the PDF OCR-fallback bugfix *invariants*.

Feature: pdf-text-extraction-ocr-fallback (bugfix spec), task 5.

These encode the UNIVERSAL fix invariants — "for all inputs in a domain" — and are
deliberately DISTINCT from:
  * test_pdf_ocr_fallback_helpers.py       — concrete example-based unit tests (task 4),
  * test_pdf_ocr_fallback_bug_condition.py — Property 1 fix-checking against the real
    `netflix 202609.pdf` fixture (task 1 / 3.5),
  * test_pdf_ocr_fallback_preservation.py  — Property 2 preservation (task 2 / 3.6).

Every boundary is mocked (no real tesseract binary, no PDF rendering, no DB, no
network), so these run deterministically everywhere. `@pytest.mark.unit` is
auto-applied by the `tests/unit/` directory. No real DB connections, no
`mysql.connector`, no `load_dotenv()`.

Invariants (one test class each):

  * INVARIANT A — no-empty-AI: for ANY lines whose joined text is empty/whitespace,
    extract_with_ai returns None WITHOUT calling AIExtractor.extract_invoice_data.
    Validates: Requirements 2.3
  * INVARIANT B — non-empty-reaches-AI: for ANY lines whose joined text has
    non-whitespace content, extract_with_ai calls the AI exactly once with text
    whose .strip() is truthy.                              Validates: Requirements 2.3
  * INVARIANT C — honest-failure: for ANY AI result that is None or has
    total_amount <= 0, extract_transactions returns [] (never a fabricated
    placeholder).                                          Validates: Requirements 2.4
  * INVARIANT D — positive-amount-builds-tx: for ANY AI result with total_amount > 0,
    extract_transactions returns a non-empty list whose first tx amount ==
    total_amount, and a VAT line is appended iff vat_amount > 0.
    Validates: Requirements 3.4
  * INVARIANT E — resolver-never-windows: for ANY TESSERACT_CMD env value and ANY
    shutil.which return, resolve_tesseract_cmd() never returns the hardcoded Windows
    path, and returns the env value when non-empty else which() else None.
    Validates: Requirements 2.5
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# The hardcoded Windows path the UNFIXED code used. The fix must NEVER return it.
WINDOWS_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# Whitespace-only "words": any mix of the usual blanks (space, tab, CR, LF,
# form-feed, vertical-tab) plus the empty string. A list of these always joins
# (via "\n") to text whose .strip() is empty.
_whitespace_atoms = st.sampled_from(["", " ", "  ", "\t", "\t\t", "\n", "\r", "\f", "\v", " \t "])
whitespace_lines_st = st.lists(_whitespace_atoms, min_size=0, max_size=8)

# Lines that join to text with at least one non-whitespace character. We build a
# list with at least one line containing a visible character, interleaved with
# arbitrary whitespace noise so the generator explores mixed content too.
_visible_text_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip() != "")

nonempty_lines_st = st.lists(_whitespace_atoms, max_size=4).flatmap(
    lambda noise: st.lists(_visible_text_st, min_size=1, max_size=4).map(
        lambda visible: noise + visible
    )
)

# Folder names that do NOT match a CSV rule (no "airbnb" substring), mirroring
# test_pdf_processor_properties.py so the AI path is exercised.
folder_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
).filter(lambda s: "airbnb" not in s.lower())

# Arbitrary url / name strings for file_data.
arbitrary_str_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=0,
    max_size=40,
)

valid_date_st = st.dates().map(lambda d: d.strftime("%Y-%m-%d"))

description_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=60,
)

vendor_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
)

# Positive totals (> 0) and non-negative VAT (>= 0, including 0 so the "no VAT
# line" branch is exercised).
positive_amount_st = st.floats(
    min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False
).map(lambda f: round(f, 2))

vat_amount_st = st.floats(
    min_value=0.0, max_value=50000.0, allow_nan=False, allow_infinity=False
).map(lambda f: round(f, 2))

# Non-positive totals: 0, exact negatives, and tiny negatives near zero.
non_positive_amount_st = st.one_of(
    st.just(0.0),
    st.just(-0.0),
    st.floats(min_value=-100000.0, max_value=-0.01, allow_nan=False, allow_infinity=False),
    st.sampled_from([-0.001, -0.0001, -1e-9]),
)


def _file_data(txt, folder, url, name):
    return {"txt": txt, "folder": folder, "url": url, "name": name}


# ---------------------------------------------------------------------------
# INVARIANT A — no-empty-AI
# Validates: Requirements 2.3
# ---------------------------------------------------------------------------


class TestInvariantNoEmptyAI:
    """INVARIANT A: for ANY generated `lines` whose joined text is empty-or-whitespace,
    extract_with_ai(lines, folder) returns None WITHOUT ever calling
    AIExtractor.extract_invoice_data.

    **Validates: Requirements 2.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(lines=whitespace_lines_st, folder=folder_name_st)
    def test_extract_with_ai_whitespace_or_empty_never_calls_ai_returns_none(
        self, lines, folder
    ):
        from pdf_ai_extraction import extract_with_ai

        # Precondition the strategy guarantees: the joined text is all whitespace.
        assert "\n".join(lines).strip() == ""

        with patch("ai_extractor.AIExtractor") as mock_ai_class, patch(
            "database.DatabaseManager"
        ) as mock_db_class:
            mock_ai = MagicMock()
            mock_ai_class.return_value = mock_ai

            result = extract_with_ai(lines, folder)

            # Honest short-circuit: no AI model call, no extractor construction.
            assert result is None
            mock_ai.extract_invoice_data.assert_not_called()
            mock_ai_class.assert_not_called()
            # The empty-content path must never touch the DB for history either.
            mock_db_class.assert_not_called()


# ---------------------------------------------------------------------------
# INVARIANT B — non-empty-reaches-AI
# Validates: Requirements 2.3
# ---------------------------------------------------------------------------


class TestInvariantNonEmptyReachesAI:
    """INVARIANT B: for ANY generated `lines` whose joined text has non-whitespace
    content, extract_with_ai calls the AI exactly once with text whose `.strip()`
    is truthy.

    **Validates: Requirements 2.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(lines=nonempty_lines_st, folder=folder_name_st)
    def test_extract_with_ai_nonempty_calls_ai_once_with_nonempty_text(
        self, lines, folder
    ):
        from pdf_ai_extraction import extract_with_ai

        # Precondition the strategy guarantees: the joined text has real content.
        assert "\n".join(lines).strip() != ""

        canned = {
            "date": "2026-09-17",
            "total_amount": 20.99,
            "vat_amount": 3.64,
            "description": "canned",
            "vendor": folder.lower(),
            "_usage": {"total_tokens": 10, "model": "test"},
        }

        with patch("ai_extractor.AIExtractor") as mock_ai_class, patch(
            "database.DatabaseManager"
        ) as mock_db_class:
            mock_ai = MagicMock()
            mock_ai.extract_invoice_data.return_value = canned
            mock_ai_class.return_value = mock_ai
            mock_db_class.return_value.get_previous_transactions.return_value = []

            result = extract_with_ai(lines, folder)

            # The AI model was handed real (non-whitespace) content exactly once.
            mock_ai.extract_invoice_data.assert_called_once()
            text_arg = mock_ai.extract_invoice_data.call_args.args[0]
            assert text_arg.strip(), "AI must receive text with non-whitespace content"
            # Canned positive-amount result flows straight back.
            assert result == canned


# ---------------------------------------------------------------------------
# INVARIANT C — honest-failure
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------


class TestInvariantHonestFailure:
    """INVARIANT C: for ANY AI result that is None OR has total_amount <= 0,
    extract_transactions returns [] — never a fabricated placeholder transaction.

    **Validates: Requirements 2.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        folder=folder_name_st,
        url=arbitrary_str_st,
        name=arbitrary_str_st,
        total_amount=non_positive_amount_st,
        date=valid_date_st,
        description=description_st,
        vendor=vendor_st,
    )
    def test_extract_transactions_non_positive_amount_returns_empty_list(
        self, folder, url, name, total_amount, date, description, vendor
    ):
        from pdf_processor import PDFProcessor

        ai_result = {
            "date": date,
            "total_amount": total_amount,
            "vat_amount": 0.0,
            "description": description,
            "vendor": vendor,
            "_usage": {"total_tokens": 0, "model": "test"},
        }
        # Non-empty txt so the empty-text short-circuit is NOT what drives this;
        # the honest failure comes purely from the non-positive total.
        file_data = _file_data("some invoice text", folder, url, name)

        with patch("ai_extractor.AIExtractor") as mock_ai_class, patch(
            "database.DatabaseManager"
        ) as mock_db_class, patch("transaction_logic.TransactionLogic") as mock_tl_class:
            mock_ai = MagicMock()
            mock_ai.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai

            mock_db_class.return_value.get_previous_transactions.return_value = []

            mock_tl = MagicMock()
            mock_tl.get_last_transactions.return_value = {"error": True, "message": "none"}
            mock_tl_class.return_value = mock_tl

            processor = PDFProcessor()
            result = processor.extract_transactions(file_data)

        assert result == [], (
            f"Non-positive total {total_amount} must yield no transaction (honest "
            f"failure -> ai_failed), got {result!r}"
        )

    @settings(max_examples=50, deadline=None)
    @given(folder=folder_name_st, url=arbitrary_str_st, name=arbitrary_str_st)
    def test_extract_transactions_none_ai_result_returns_empty_list(
        self, folder, url, name
    ):
        """A None AI result (extraction error) also yields [] — no placeholder."""
        from pdf_processor import PDFProcessor

        file_data = _file_data("some invoice text", folder, url, name)

        with patch("ai_extractor.AIExtractor") as mock_ai_class, patch(
            "database.DatabaseManager"
        ) as mock_db_class, patch("transaction_logic.TransactionLogic") as mock_tl_class:
            mock_ai = MagicMock()
            mock_ai.extract_invoice_data.return_value = None
            mock_ai_class.return_value = mock_ai

            mock_db_class.return_value.get_previous_transactions.return_value = []
            mock_tl_class.return_value.get_last_transactions.return_value = {
                "error": True,
                "message": "none",
            }

            processor = PDFProcessor()
            result = processor.extract_transactions(file_data)

        assert result == []


# ---------------------------------------------------------------------------
# INVARIANT D — positive-amount-builds-tx
# Validates: Requirements 3.4
# ---------------------------------------------------------------------------


class TestInvariantPositiveAmountBuildsTx:
    """INVARIANT D: for ANY AI result with total_amount > 0, extract_transactions
    returns a non-empty list whose first tx amount == total_amount, and a VAT line
    is appended iff vat_amount > 0.

    **Validates: Requirements 3.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        folder=folder_name_st,
        url=arbitrary_str_st,
        name=arbitrary_str_st,
        total_amount=positive_amount_st,
        vat_amount=vat_amount_st,
        date=valid_date_st,
        description=description_st,
        vendor=vendor_st,
    )
    def test_extract_transactions_positive_amount_builds_main_and_optional_vat(
        self, folder, url, name, total_amount, vat_amount, date, description, vendor
    ):
        from pdf_processor import PDFProcessor

        ai_result = {
            "date": date,
            "total_amount": total_amount,
            "vat_amount": vat_amount,
            "description": description,
            "vendor": vendor,
            "_usage": {"total_tokens": 0, "model": "test"},
        }
        file_data = _file_data("some invoice text", folder, url, name)

        with patch("ai_extractor.AIExtractor") as mock_ai_class, patch(
            "database.DatabaseManager"
        ) as mock_db_class, patch("transaction_logic.TransactionLogic") as mock_tl_class:
            mock_ai = MagicMock()
            mock_ai.extract_invoice_data.return_value = ai_result
            mock_ai_class.return_value = mock_ai

            mock_db_class.return_value.get_previous_transactions.return_value = []
            mock_tl_class.return_value.get_last_transactions.return_value = {
                "error": True,
                "message": "none",
            }

            processor = PDFProcessor()
            result = processor.extract_transactions(file_data)

        assert isinstance(result, list)
        assert len(result) >= 1, "A positive total must build at least the main tx"

        main_tx = result[0]
        assert float(main_tx["amount"]) == total_amount
        assert main_tx["date"] == date
        assert main_tx["description"] == description

        # VAT line present iff vat_amount > 0.
        if vat_amount > 0:
            assert len(result) >= 2, "vat_amount > 0 must append a VAT line"
            vat_tx = result[1]
            assert float(vat_tx["amount"]) == vat_amount
            assert vat_tx["description"] == f"VAT - {description}"
        else:
            # No VAT line: the only transaction is the main one.
            assert len(result) == 1, "vat_amount == 0 must NOT append a VAT line"


# ---------------------------------------------------------------------------
# INVARIANT E — resolver-never-windows
# Validates: Requirements 2.5
# ---------------------------------------------------------------------------


class TestInvariantResolverNeverWindows:
    """INVARIANT E: for ANY TESSERACT_CMD env value and ANY shutil.which return
    (string or None), resolve_tesseract_cmd() never returns the hardcoded Windows
    path, and returns the env value when the env var is non-empty, else the which()
    value, else None.

    **Validates: Requirements 2.5**
    """

    @settings(max_examples=150, deadline=None)
    @given(
        env_value=st.one_of(
            st.none(),
            st.just(""),
            st.text(min_size=1, max_size=60).filter(lambda s: "\x00" not in s),
        ),
        which_value=st.one_of(
            st.none(),
            st.text(min_size=1, max_size=60).filter(lambda s: "\x00" not in s),
        ),
    )
    def test_resolve_tesseract_cmd_env_then_which_then_none_never_windows(
        self, env_value, which_value
    ):
        import pdf_parsing_strategies as pps

        # Build the environment: when env_value is None, TESSERACT_CMD is absent.
        env = {} if env_value is None else {"TESSERACT_CMD": env_value}

        with patch.dict("os.environ", env, clear=True), patch.object(
            pps.shutil, "which", return_value=which_value
        ):
            result = pps.resolve_tesseract_cmd()

        # Expected resolution: non-empty env var wins, else which(), else None.
        if env_value:
            expected = env_value
        else:
            expected = which_value

        assert result == expected
        # Universal safety invariant: the hardcoded Windows path never surfaces.
        assert result != WINDOWS_TESSERACT_PATH
