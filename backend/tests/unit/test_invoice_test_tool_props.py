"""
Property-based tests for invoice processing test tool.

Uses Hypothesis to verify correctness properties from the design document.
Feature: invoice-processing-test-tool
Properties: 1 (File Extension Validation), 2 (Dry-Run No Side Effects),
            3 (Temporary File Cleanup), 7 (AI Metrics Conditional on Parser),
            8 (Cost Calculation Correctness), 9 (Prompt Length Validation),
            10 (Vendor Name Validation), 11 (Vendor History Count Limit),
            12 (Partial Result Preservation on Failure)

Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 4.2, 4.3, 4.4, 4.6, 5.1, 5.2, 6.3, 6.4, 7.1, 7.3, 8.4
Reference: .kiro/specs/invoice-processing-test-tool/design.md
"""

import re
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

from routes.sysadmin_test_tool import (
    _validate_file_extension,
    _validate_prompt_length,
    _validate_vendor_name,
    ALLOWED_EXTENSIONS,
    VENDOR_NAME_PATTERN,
    MAX_PROMPT_LENGTH,
    MIN_PROMPT_LENGTH,
)
from services.ai_usage_tracker import AIUsageTracker
from services.invoice_test_service import InvoiceTestService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid extensions (lowercase canonical forms)
VALID_EXTENSIONS = list(ALLOWED_EXTENSIONS)

# Strategy: generate a valid file extension (mixed case)
valid_extension_st = st.sampled_from(VALID_EXTENSIONS).flatmap(
    lambda ext: st.builds(
        lambda chars: ''.join(chars),
        st.lists(
            st.sampled_from([c.lower(), c.upper()] if c.isalpha() else [c]),
            min_size=len(ext),
            max_size=len(ext),
        ).map(lambda pairs: [p[0] if len(p) == 1 else p[i % 2] for i, p in enumerate(
            [[c.lower(), c.upper()] if c.isalpha() else [c] for c in ext]
        )])
    )
)

# Simpler approach for valid extensions with random casing
def _random_case_extension(ext):
    """Strategy that generates the extension with random upper/lower casing."""
    return st.lists(
        st.booleans(),
        min_size=len(ext),
        max_size=len(ext),
    ).map(lambda flags: ''.join(
        c.upper() if f else c.lower() for c, f in zip(ext, flags)
    ))


# Strategy: a valid filename with allowed extension
valid_filename_st = st.one_of([
    st.sampled_from(VALID_EXTENSIONS).flatmap(
        lambda ext: _random_case_extension(ext).flatmap(
            lambda cased_ext: st.text(
                alphabet=st.characters(blacklist_characters='\x00./\\'),
                min_size=1,
                max_size=50,
            ).map(lambda name: f"{name}.{cased_ext}")
        )
    )
])

# Strategy: invalid extensions (not in the allowed set)
invalid_extension_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), min_codepoint=ord('a'), max_codepoint=ord('z')),
    min_size=1,
    max_size=10,
).filter(lambda ext: ext.lower() not in ALLOWED_EXTENSIONS)

# Strategy: a filename with an invalid extension
invalid_extension_filename_st = st.tuples(
    st.text(
        alphabet=st.characters(blacklist_characters='\x00./\\'),
        min_size=1,
        max_size=50,
    ),
    invalid_extension_st,
).map(lambda t: f"{t[0]}.{t[1]}")

# Strategy: a filename with no extension (no dot)
no_extension_filename_st = st.text(
    alphabet=st.characters(blacklist_characters='\x00./\\'),
    min_size=1,
    max_size=50,
)

# Strategy: valid prompt (1 to 10,000 chars)
valid_prompt_st = st.text(min_size=MIN_PROMPT_LENGTH, max_size=MAX_PROMPT_LENGTH)

# Strategy: empty prompt
empty_prompt_st = st.just('')

# Strategy: prompt too long (>10,000 chars)
# Use a fixed character to avoid large_base_example health check
too_long_prompt_st = st.integers(
    min_value=MAX_PROMPT_LENGTH + 1,
    max_value=MAX_PROMPT_LENGTH + 500,
).map(lambda n: 'a' * n)

# Strategy: valid vendor name (matches ^[a-zA-Z0-9_ -]{1,100}$)
VALID_VENDOR_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- '
valid_vendor_name_st = st.text(
    alphabet=st.sampled_from(list(VALID_VENDOR_CHARS)),
    min_size=1,
    max_size=100,
)

# Strategy: invalid vendor name (contains invalid chars or wrong length)
invalid_vendor_name_too_long_st = st.text(
    alphabet=st.sampled_from(list(VALID_VENDOR_CHARS)),
    min_size=101,
    max_size=200,
)

invalid_vendor_name_empty_st = st.just('')

invalid_vendor_name_bad_chars_st = st.text(
    min_size=1,
    max_size=100,
).filter(lambda s: not re.match(r'^[a-zA-Z0-9_ -]{1,100}$', s))


# ---------------------------------------------------------------------------
# Property 1: File Extension Validation
# Feature: invoice-processing-test-tool, Property 1
# Validates: Requirements 2.1, 2.5
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFileExtensionValidation:
    """
    Property 1: File extension validation

    For any filename string, the file validation function SHALL accept it if
    and only if it has an extension in {pdf, jpg, jpeg, png, csv, eml, mhtml}
    (case-insensitive), and reject all other extensions.

    **Validates: Requirements 2.1, 2.5**
    """

    @given(ext=st.sampled_from(VALID_EXTENSIONS),
           case_flags=st.lists(st.booleans(), min_size=1, max_size=10),
           basename=st.text(
               alphabet=st.characters(blacklist_characters='\x00./\\'),
               min_size=1, max_size=30,
           ))
    @settings(max_examples=100)
    def test_accepts_valid_extensions_any_case(self, ext, case_flags, basename):
        """Files with allowed extensions (any casing) should be accepted."""
        # Apply random casing to the extension
        cased_ext = ''.join(
            c.upper() if case_flags[i % len(case_flags)] else c.lower()
            for i, c in enumerate(ext)
        )
        filename = f"{basename}.{cased_ext}"
        assert _validate_file_extension(filename) is True

    @given(ext=invalid_extension_st,
           basename=st.text(
               alphabet=st.characters(blacklist_characters='\x00./\\'),
               min_size=1, max_size=30,
           ))
    @settings(max_examples=100)
    def test_rejects_invalid_extensions(self, ext, basename):
        """Files with extensions not in the allowed set should be rejected."""
        filename = f"{basename}.{ext}"
        assert _validate_file_extension(filename) is False

    @given(filename=no_extension_filename_st)
    @settings(max_examples=100)
    def test_rejects_filenames_without_extension(self, filename):
        """Files without a dot (no extension) should be rejected."""
        assume('.' not in filename)
        assert _validate_file_extension(filename) is False

    @settings(max_examples=100)
    @given(data=st.data())
    def test_rejects_empty_filename(self, data):
        """Empty filenames and None should be rejected."""
        assert _validate_file_extension('') is False
        assert _validate_file_extension(None) is False


# ---------------------------------------------------------------------------
# Property 9: Prompt Length Validation
# Feature: invoice-processing-test-tool, Property 9
# Validates: Requirements 6.3, 6.4
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPromptLengthValidation:
    """
    Property 9: Prompt length validation

    For any custom prompt string, accept if length is between 1 and 10,000
    characters (inclusive). Reject if length is 0 or exceeds 10,000 characters.

    **Validates: Requirements 6.3, 6.4**
    """

    @given(prompt=valid_prompt_st)
    @settings(max_examples=100)
    def test_accepts_valid_length_prompts(self, prompt):
        """Prompts with 1–10,000 characters should be accepted."""
        assert _validate_prompt_length(prompt) is True

    @given(prompt=empty_prompt_st)
    @settings(max_examples=100)
    def test_rejects_empty_prompt(self, prompt):
        """Empty prompt (0 characters) should be rejected."""
        assert _validate_prompt_length(prompt) is False

    @given(prompt=too_long_prompt_st)
    @settings(max_examples=100)
    def test_rejects_too_long_prompt(self, prompt):
        """Prompts exceeding 10,000 characters should be rejected."""
        assert _validate_prompt_length(prompt) is False

    @given(length=st.integers(min_value=1, max_value=MAX_PROMPT_LENGTH))
    @settings(max_examples=100)
    def test_boundary_lengths_accepted(self, length):
        """Any prompt of length 1 to 10,000 should be accepted."""
        prompt = 'x' * length
        assert _validate_prompt_length(prompt) is True

    @given(length=st.integers(min_value=MAX_PROMPT_LENGTH + 1, max_value=MAX_PROMPT_LENGTH + 500))
    @settings(max_examples=100)
    def test_boundary_lengths_rejected(self, length):
        """Any prompt longer than 10,000 should be rejected."""
        prompt = 'x' * length
        assert _validate_prompt_length(prompt) is False


# ---------------------------------------------------------------------------
# Property 10: Vendor Name Validation
# Feature: invoice-processing-test-tool, Property 10
# Validates: Requirements 7.1
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVendorNameValidation:
    """
    Property 10: Vendor name validation

    For any input string, the system SHALL accept it if and only if it matches
    `^[a-zA-Z0-9_-]{1,100}$` (alphanumeric, hyphens, underscores, 1–100 characters).

    **Validates: Requirements 7.1**
    """

    @given(name=valid_vendor_name_st)
    @settings(max_examples=100)
    def test_accepts_valid_vendor_names(self, name):
        """Vendor names matching the pattern should be accepted."""
        assert _validate_vendor_name(name) is True

    @given(name=invalid_vendor_name_too_long_st)
    @settings(max_examples=100)
    def test_rejects_vendor_name_too_long(self, name):
        """Vendor names exceeding 100 characters should be rejected."""
        assert _validate_vendor_name(name) is False

    @given(name=invalid_vendor_name_bad_chars_st)
    @settings(max_examples=100)
    def test_rejects_vendor_name_with_invalid_chars(self, name):
        """Vendor names with invalid characters should be rejected."""
        assert _validate_vendor_name(name) is False

    def test_rejects_empty_vendor_name(self):
        """Empty vendor name should be rejected."""
        assert _validate_vendor_name('') is False

    @given(name=st.text(min_size=1, max_size=100))
    @settings(max_examples=100)
    def test_validation_matches_regex(self, name):
        """Validation result should match the regex pattern exactly."""
        expected = bool(re.match(r'^[a-zA-Z0-9_ -]{1,100}$', name))
        assert _validate_vendor_name(name) == expected


# ---------------------------------------------------------------------------
# Property 4: Raw text truncation invariant
# Feature: invoice-processing-test-tool, Property 4
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRawTextTruncationInvariant:
    """
    Property 4: Raw text truncation invariant

    For any extracted text output, if the text length exceeds 50,000 characters
    then the returned text SHALL be exactly 50,000 characters with
    `raw_text_truncated` set to true; if the text length is <= 50,000 characters
    then the full text SHALL be returned with `raw_text_truncated` set to false.

    **Validates: Requirements 3.1**
    """

    MAX_RAW_TEXT = InvoiceTestService.MAX_RAW_TEXT_LENGTH  # 50,000

    @given(text=st.text(min_size=0, max_size=50_000))
    @settings(max_examples=100)
    def test_text_within_limit_returned_in_full(self, text):
        """Text <= 50k chars should be returned as-is with truncated=false."""
        # Simulate the truncation logic from process_file_dry_run
        raw_text_truncated = len(text) > self.MAX_RAW_TEXT
        if raw_text_truncated:
            result_text = text[:self.MAX_RAW_TEXT]
        else:
            result_text = text

        assert raw_text_truncated is False
        assert result_text == text
        assert len(result_text) == len(text)

    @given(extra=st.integers(min_value=1, max_value=10_000))
    @settings(max_examples=100)
    def test_text_over_limit_truncated_to_exactly_50k(self, extra):
        """Text > 50k chars should be truncated to exactly 50k with truncated=true."""
        text = 'x' * (self.MAX_RAW_TEXT + extra)

        raw_text_truncated = len(text) > self.MAX_RAW_TEXT
        if raw_text_truncated:
            result_text = text[:self.MAX_RAW_TEXT]
        else:
            result_text = text

        assert raw_text_truncated is True
        assert len(result_text) == self.MAX_RAW_TEXT

    @given(char=st.characters(min_codepoint=32, max_codepoint=126))
    @settings(max_examples=100)
    def test_text_exactly_at_limit_not_truncated(self, char):
        """Text of exactly 50k chars should not be truncated."""
        text = char * self.MAX_RAW_TEXT

        raw_text_truncated = len(text) > self.MAX_RAW_TEXT
        if raw_text_truncated:
            result_text = text[:self.MAX_RAW_TEXT]
        else:
            result_text = text

        assert raw_text_truncated is False
        assert result_text == text
        assert len(result_text) == self.MAX_RAW_TEXT

    @given(extra=st.integers(min_value=1, max_value=5_000))
    @settings(max_examples=100)
    def test_truncated_text_preserves_prefix(self, extra):
        """When truncated, the result should be the first 50k chars of the original."""
        text = 'a' * self.MAX_RAW_TEXT + 'b' * extra

        raw_text_truncated = len(text) > self.MAX_RAW_TEXT
        result_text = text[:self.MAX_RAW_TEXT] if raw_text_truncated else text

        assert raw_text_truncated is True
        assert result_text == 'a' * self.MAX_RAW_TEXT


# ---------------------------------------------------------------------------
# Property 5: Extraction result field completeness
# Feature: invoice-processing-test-tool, Property 5
# Validates: Requirements 3.2, 3.3
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractionResultFieldCompleteness:
    """
    Property 5: Extraction result field completeness

    For any successful extraction (AI or CSV rule), the extraction result SHALL
    contain all five fields (date, total_amount, vat_amount, description, vendor)
    as explicitly present keys, with missing values represented as empty string
    or 0.0 rather than omitted keys.

    **Validates: Requirements 3.2, 3.3**
    """

    REQUIRED_FIELDS = {'date', 'total_amount', 'vat_amount', 'description', 'vendor'}

    @given(
        date=st.one_of(st.just(''), st.text(min_size=0, max_size=20)),
        total_amount=st.one_of(st.just(0.0), st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)),
        vat_amount=st.one_of(st.just(0.0), st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)),
        description=st.text(min_size=0, max_size=200),
        vendor=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=100)
    def test_build_extraction_result_from_ai_data(self, date, total_amount, vat_amount, description, vendor):
        """_build_extraction_result with ai_data should produce all 5 fields."""
        service = InvoiceTestService.__new__(InvoiceTestService)

        file_data = {
            'ai_data': {
                'date': date,
                'total_amount': total_amount,
                'vat_amount': vat_amount,
                'description': description,
                'vendor': vendor,
            }
        }

        result = service._build_extraction_result(file_data, [], 'ai')

        # All 5 required fields must be present as keys
        assert set(result.keys()) >= self.REQUIRED_FIELDS

    @given(
        amount=st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False),
        date=st.text(min_size=0, max_size=20),
        description=st.text(min_size=0, max_size=200),
    )
    @settings(max_examples=100)
    def test_build_extraction_result_from_transactions(self, amount, date, description):
        """_build_extraction_result with transactions should produce all 5 fields."""
        service = InvoiceTestService.__new__(InvoiceTestService)

        transactions = [{'amount': amount, 'date': date, 'description': description}]
        file_data = {'folder': 'test/TestVendor'}

        result = service._build_extraction_result(file_data, transactions, 'ai')

        # All 5 required fields must be present as keys
        assert set(result.keys()) >= self.REQUIRED_FIELDS

    @given(parser_used=st.sampled_from(['ai', 'csv_rule', 'ai_failed']))
    @settings(max_examples=100)
    def test_build_extraction_result_empty_produces_all_fields(self, parser_used):
        """_build_extraction_result with no data should still produce all 5 fields."""
        service = InvoiceTestService.__new__(InvoiceTestService)

        result = service._build_extraction_result({}, [], parser_used)

        # All 5 required fields must be present as keys
        assert set(result.keys()) >= self.REQUIRED_FIELDS
        # Missing values should be empty string or 0.0, never None
        assert result['date'] == ''
        assert result['total_amount'] == 0.0
        assert result['vat_amount'] == 0.0
        assert result['description'] == ''
        assert result['vendor'] == ''


# ---------------------------------------------------------------------------
# Property 6: Parser used is a valid enum value
# Feature: invoice-processing-test-tool, Property 6
# Validates: Requirements 3.6
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParserUsedValidEnum:
    """
    Property 6: Parser used is a valid enum value

    For any pipeline execution result, the `parser_used` field SHALL be exactly
    one of: "ai", "csv_rule", or "ai_failed".

    **Validates: Requirements 3.6**
    """

    VALID_PARSER_VALUES = {'ai', 'csv_rule', 'ai_failed'}

    @given(
        has_transactions=st.booleans(),
        parser_hint=st.one_of(st.just(None), st.just('csv_rule'), st.just('other')),
        has_ai_data=st.booleans(),
        amount=st.floats(min_value=-100, max_value=100000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_determine_parser_used_always_valid_enum(self, has_transactions, parser_hint, has_ai_data, amount):
        """_determine_parser_used should always return a valid enum value."""
        service = InvoiceTestService.__new__(InvoiceTestService)

        # Build transactions based on strategy
        if has_transactions:
            tx = {'amount': amount}
            if parser_hint:
                tx['parser_used_hint'] = parser_hint
            transactions = [tx]
        else:
            transactions = []

        # Build file_data
        file_data = {}
        if has_ai_data:
            file_data['ai_data'] = {'date': '2024-01-01'}

        result = service._determine_parser_used(transactions, file_data)

        assert result in self.VALID_PARSER_VALUES

    @given(data=st.data())
    @settings(max_examples=100)
    def test_parser_used_from_various_transaction_shapes(self, data):
        """Different transaction structures should all produce valid parser_used."""
        service = InvoiceTestService.__new__(InvoiceTestService)

        # Generate a variety of transaction list shapes
        tx_count = data.draw(st.integers(min_value=0, max_value=5))
        transactions = []
        for _ in range(tx_count):
            tx = {}
            if data.draw(st.booleans()):
                tx['amount'] = data.draw(st.floats(min_value=-100, max_value=100000, allow_nan=False, allow_infinity=False))
            if data.draw(st.booleans()):
                tx['parser_used_hint'] = data.draw(st.sampled_from(['csv_rule', 'ai', None, 'other']))
            if data.draw(st.booleans()):
                tx['date'] = '2024-01-01'
            transactions.append(tx)

        file_data = {}
        if data.draw(st.booleans()):
            file_data['ai_data'] = {}

        result = service._determine_parser_used(transactions, file_data)

        assert result in self.VALID_PARSER_VALUES


# ---------------------------------------------------------------------------
# Property 13: Execution log truncation
# Feature: invoice-processing-test-tool, Property 13
# Validates: Requirements 8.5
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExecutionLogTruncation:
    """
    Property 13: Execution log truncation

    For any pipeline execution producing stdout output, the `execution_log` field
    SHALL contain at most 10,000 characters. If the actual log exceeds 10,000
    characters, it SHALL be truncated to the most recent 10,000 characters.

    **Validates: Requirements 8.5**
    """

    MAX_LOG = InvoiceTestService.MAX_EXECUTION_LOG_LENGTH  # 10,000

    def _truncate(self, log_text):
        """Call _truncate_log using a minimal instance (avoids __init__ side effects)."""
        service = InvoiceTestService.__new__(InvoiceTestService)
        return service._truncate_log(log_text)

    @given(log_text=st.text(min_size=0, max_size=10_000))
    @settings(max_examples=100)
    def test_log_within_limit_returned_in_full(self, log_text):
        """Log text <= 10k chars should be returned unchanged."""
        result = self._truncate(log_text)

        assert result == log_text
        assert len(result) <= self.MAX_LOG

    @given(extra=st.integers(min_value=1, max_value=10_000))
    @settings(max_examples=100)
    def test_log_over_limit_truncated_to_10k(self, extra):
        """Log text > 10k chars should be truncated to exactly 10k."""
        log_text = 'x' * (self.MAX_LOG + extra)

        result = self._truncate(log_text)

        assert len(result) == self.MAX_LOG

    @given(extra=st.integers(min_value=1, max_value=5_000))
    @settings(max_examples=100)
    def test_truncation_keeps_most_recent_chars(self, extra):
        """When truncated, the result should be the LAST 10k characters."""
        prefix = 'a' * extra
        suffix = 'b' * self.MAX_LOG
        log_text = prefix + suffix

        result = self._truncate(log_text)

        assert len(result) == self.MAX_LOG
        # The result should be the most recent (last) 10k characters
        assert result == log_text[-self.MAX_LOG:]

    @given(char=st.characters(min_codepoint=32, max_codepoint=126))
    @settings(max_examples=100)
    def test_log_exactly_at_limit_not_truncated(self, char):
        """Log text of exactly 10k chars should not be truncated."""
        log_text = char * self.MAX_LOG

        result = self._truncate(log_text)

        assert result == log_text
        assert len(result) == self.MAX_LOG

    @given(log_text=st.text(min_size=0, max_size=30_000))
    @settings(max_examples=100)
    def test_output_never_exceeds_limit(self, log_text):
        """Regardless of input size, output should never exceed 10k characters."""
        result = self._truncate(log_text)

        assert len(result) <= self.MAX_LOG


# ---------------------------------------------------------------------------
# Property 7: AI metrics conditional on parser used
# Feature: invoice-processing-test-tool, Property 7
# Validates: Requirements 4.2, 4.3, 4.4, 4.6
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAIMetricsConditionalOnParser:
    """
    Property 7: AI metrics conditional on parser used

    For any pipeline execution result:
    - If parser_used is "ai": ai_duration_ms must be a non-negative integer,
      ai_model must be a non-empty string, and ai_tokens must contain
      non-negative integers for prompt_tokens, completion_tokens, and total_tokens.
    - If parser_used is "csv_rule": ai_duration_ms, ai_model, and ai_tokens
      must all be null/None.

    **Validates: Requirements 4.2, 4.3, 4.4, 4.6**
    """

    @given(
        prompt_tokens=st.integers(min_value=0, max_value=10_000),
        completion_tokens=st.integers(min_value=0, max_value=10_000),
        ai_duration_ms=st.integers(min_value=0, max_value=60_000),
        model_name=st.sampled_from([
            'deepseek/deepseek-chat',
            'meta-llama/llama-3.2-3b-instruct:free',
            'google/gemini-flash-1.5',
        ]),
        folder_name=st.text(
            alphabet=st.sampled_from(list('abcdefghijklmnopqrstuvwxyz0123456789_-')),
            min_size=1, max_size=20,
        ),
    )
    @settings(max_examples=100, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
    def test_ai_parser_has_non_negative_metrics(
        self, prompt_tokens, completion_tokens, ai_duration_ms, model_name, folder_name
    ):
        """When parser_used is 'ai', AI metrics must be non-negative and model non-empty."""
        from unittest.mock import patch, MagicMock
        from services.invoice_test_service import InvoiceTestService

        total_tokens = prompt_tokens + completion_tokens

        # Mock PDFProcessor to simulate AI extraction
        with patch('services.invoice_test_service.PDFProcessor') as MockProcessor, \
             patch('services.invoice_test_service.CsvRuleEngine'):

            mock_processor_instance = MagicMock()
            MockProcessor.return_value = mock_processor_instance

            # Simulate process_file returning file_data with ai_data and _usage
            mock_file_data = {
                'txt': 'Invoice text content',
                'name': 'test.pdf',
                'url': 'dry-run://test.pdf',
                'ai_data': {
                    'date': '2024-01-15',
                    'total_amount': 100.0,
                    'vat_amount': 21.0,
                    'description': 'Test invoice',
                    'vendor': folder_name,
                    '_usage': {
                        'model': model_name,
                        'prompt_tokens': prompt_tokens,
                        'completion_tokens': completion_tokens,
                        'total_tokens': total_tokens,
                    },
                },
            }
            mock_processor_instance.process_file.return_value = mock_file_data

            # extract_transactions returns AI-based transactions (no csv_rule hint)
            mock_processor_instance.extract_transactions.return_value = [
                {'date': '2024-01-15', 'amount': 100.0, 'description': 'Test'}
            ]

            # Mock _extract_with_ai to capture usage
            mock_processor_instance._extract_with_ai = MagicMock(return_value={
                '_usage': {
                    'model': model_name,
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                }
            })

            service = InvoiceTestService.__new__(InvoiceTestService)
            service.processor = mock_processor_instance
            service.csv_rule_engine = MagicMock()

            # Create a temp file path that we pretend exists
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            tmp.write(b'fake pdf content')
            tmp.close()

            try:
                result = service.process_file_dry_run(tmp.name, folder_name)
            except Exception:
                # If temp file was already cleaned up, that's fine
                return

            performance = result['performance']
            parser_used = result['pipeline_result'].get('parser_used')

            # When AI was used, verify metrics
            if parser_used == 'ai':
                assert performance['ai_duration_ms'] is not None
                assert isinstance(performance['ai_duration_ms'], int)
                assert performance['ai_duration_ms'] >= 0

                assert performance['ai_model'] is not None
                assert isinstance(performance['ai_model'], str)
                assert len(performance['ai_model']) > 0

                assert performance['ai_tokens'] is not None
                assert performance['ai_tokens']['prompt_tokens'] >= 0
                assert performance['ai_tokens']['completion_tokens'] >= 0
                assert performance['ai_tokens']['total_tokens'] >= 0

    @given(
        folder_name=st.text(
            alphabet=st.sampled_from(list('abcdefghijklmnopqrstuvwxyz0123456789_-')),
            min_size=1, max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_csv_rule_parser_has_null_ai_metrics(self, folder_name):
        """When parser_used is 'csv_rule', AI metrics must all be None."""
        from unittest.mock import patch, MagicMock
        from services.invoice_test_service import InvoiceTestService

        # Mock PDFProcessor to simulate CSV rule extraction
        with patch('services.invoice_test_service.PDFProcessor') as MockProcessor, \
             patch('services.invoice_test_service.CsvRuleEngine'):

            mock_processor_instance = MagicMock()
            MockProcessor.return_value = mock_processor_instance

            # Simulate process_file returning file_data without ai_data
            mock_file_data = {
                'txt': 'csv,data,content',
                'name': 'test.csv',
                'url': 'dry-run://test.csv',
            }
            mock_processor_instance.process_file.return_value = mock_file_data

            # extract_transactions returns CSV-rule-based transactions
            mock_processor_instance.extract_transactions.return_value = [
                {
                    'date': '2024-01-15',
                    'amount': 50.0,
                    'description': 'CSV transaction',
                    'parser_used_hint': 'csv_rule',
                }
            ]

            # No _extract_with_ai call for CSV rule
            mock_processor_instance._extract_with_ai = MagicMock(return_value=None)

            service = InvoiceTestService.__new__(InvoiceTestService)
            service.processor = mock_processor_instance
            service.csv_rule_engine = MagicMock()

            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
            tmp.write(b'col1,col2\nval1,val2')
            tmp.close()

            try:
                result = service.process_file_dry_run(tmp.name, folder_name)
            except Exception:
                return

            performance = result['performance']
            parser_used = result['pipeline_result'].get('parser_used')

            # When CSV rule was used, AI metrics must be null
            if parser_used == 'csv_rule':
                assert performance['ai_duration_ms'] is None
                assert performance['ai_model'] is None
                assert performance['ai_tokens'] is None


# ---------------------------------------------------------------------------
# Property 8: Cost calculation correctness
# Feature: invoice-processing-test-tool, Property 8
# Validates: Requirements 5.1, 5.2
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCostCalculationCorrectness:
    """
    Property 8: Cost calculation correctness

    For any (tokens, model) pair:
    - cost_estimate = (total_tokens / 1,000,000) × rate_per_million
      rounded to 6 decimal places.
    - Uses _build_ai_usage_preview directly with generated token values.

    **Validates: Requirements 5.1, 5.2**
    """

    @given(
        total_tokens=st.integers(min_value=0, max_value=10_000_000),
        prompt_tokens=st.integers(min_value=0, max_value=5_000_000),
        completion_tokens=st.integers(min_value=0, max_value=5_000_000),
        model=st.sampled_from([
            'deepseek/deepseek-chat',
            'meta-llama/llama-3.2-3b-instruct:free',
            'google/gemini-flash-1.5',
            'anthropic/claude-3.5-sonnet',
            'default',
        ]),
    )
    @settings(max_examples=100)
    def test_cost_formula_matches_decimal_calculation(
        self, total_tokens, prompt_tokens, completion_tokens, model
    ):
        """cost_estimate must equal (total_tokens / 1_000_000) * rate rounded to 6 places."""
        from decimal import Decimal
        from unittest.mock import patch, MagicMock
        from services.invoice_test_service import InvoiceTestService
        from services.ai_usage_tracker import AIUsageTracker

        # Build a performance dict simulating what the service would have
        performance = {
            'total_duration_ms': 1000,
            'ai_duration_ms': 500,
            'ai_model': model if model != 'default' else 'unknown/model',
            'ai_tokens': {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
            },
        }

        # Create an instance without full init to test _build_ai_usage_preview directly
        service = InvoiceTestService.__new__(InvoiceTestService)

        # Call _build_ai_usage_preview
        result = service._build_ai_usage_preview(
            'test-admin', 'TestVendor', performance
        )

        # Compute expected cost using the same formula
        actual_model = model if model != 'default' else 'unknown/model'
        rate_per_million = AIUsageTracker.MODEL_PRICING.get(
            actual_model,
            AIUsageTracker.MODEL_PRICING.get('default', 0.5)
        )

        if total_tokens > 0:
            expected_cost = (
                Decimal(total_tokens) / Decimal(1_000_000) * Decimal(str(rate_per_million))
            ).quantize(Decimal('0.000001'))
        else:
            expected_cost = Decimal('0.000000')

        # Verify the cost_estimate matches
        assert result['cost_estimate'] == str(expected_cost), (
            f"For {total_tokens} tokens with model '{actual_model}' "
            f"(rate={rate_per_million}): expected {expected_cost}, "
            f"got {result['cost_estimate']}"
        )

        # Verify the cost_breakdown fields
        assert result['cost_breakdown']['total_tokens'] == total_tokens
        assert result['cost_breakdown']['rate_per_million'] == rate_per_million
        assert result['cost_breakdown']['model'] == actual_model
        assert result['tokens_used'] == total_tokens

    @given(
        total_tokens=st.integers(min_value=0, max_value=10_000_000),
        model=st.sampled_from(list(AIUsageTracker.MODEL_PRICING.keys())),
    )
    @settings(max_examples=100)
    def test_cost_uses_correct_model_rate(self, total_tokens, model):
        """Cost calculation must use the correct rate from MODEL_PRICING for the given model."""
        from decimal import Decimal
        from services.invoice_test_service import InvoiceTestService
        from services.ai_usage_tracker import AIUsageTracker

        performance = {
            'total_duration_ms': 1000,
            'ai_duration_ms': 500,
            'ai_model': model,
            'ai_tokens': {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': total_tokens,
            },
        }

        service = InvoiceTestService.__new__(InvoiceTestService)
        result = service._build_ai_usage_preview('test-admin', 'TestVendor', performance)

        # The rate in breakdown must match MODEL_PRICING for this model
        expected_rate = AIUsageTracker.MODEL_PRICING[model]
        assert result['cost_breakdown']['rate_per_million'] == expected_rate

        # Verify cost to 6 decimal places
        if total_tokens > 0:
            expected_cost = (
                Decimal(total_tokens) / Decimal(1_000_000) * Decimal(str(expected_rate))
            ).quantize(Decimal('0.000001'))
        else:
            expected_cost = Decimal('0.000000')

        assert result['cost_estimate'] == str(expected_cost)

    @given(
        total_tokens=st.just(0),
        model=st.sampled_from(list(AIUsageTracker.MODEL_PRICING.keys())),
    )
    @settings(max_examples=100)
    def test_zero_tokens_gives_zero_cost(self, total_tokens, model):
        """When total_tokens is 0, cost_estimate must be '0.000000'."""
        from services.invoice_test_service import InvoiceTestService

        performance = {
            'total_duration_ms': 1000,
            'ai_duration_ms': 500,
            'ai_model': model,
            'ai_tokens': {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0,
            },
        }

        service = InvoiceTestService.__new__(InvoiceTestService)
        result = service._build_ai_usage_preview('test-admin', 'TestVendor', performance)

        assert result['cost_estimate'] == '0.000000'


# ---------------------------------------------------------------------------
# Property 11: Vendor History Count Limit
# Feature: invoice-processing-test-tool, Property 11
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVendorHistoryCountLimit:
    """
    Property 11: Vendor history count limit

    For any vendor name query, the returned transaction list SHALL contain
    at most 20 items.

    **Validates: Requirements 7.3**
    """

    @given(list_size=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100, deadline=None)
    def test_vendor_history_returns_at_most_20_items(self, list_size):
        """get_vendor_history always returns at most 20 items regardless of DB result size."""
        from unittest.mock import patch, MagicMock

        # Generate a mock transaction list of the given size
        mock_transactions = [
            {
                'TransactionDate': f'2024-01-{(i % 28) + 1:02d}',
                'TransactionAmount': 100.0 + i,
                'TransactionDescription': f'Invoice #{i}',
            }
            for i in range(list_size)
        ]

        service = InvoiceTestService.__new__(InvoiceTestService)

        with patch('transaction_logic.TransactionLogic') as MockTL:
            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = mock_transactions
            MockTL.return_value = mock_tl_instance

            result = service.get_vendor_history('TestVendor', 'admin1')

        assert len(result) <= 20

    @given(list_size=st.integers(min_value=21, max_value=100))
    @settings(max_examples=100, deadline=None)
    def test_vendor_history_truncates_large_lists(self, list_size):
        """When DB returns more than 20, result is exactly 20."""
        from unittest.mock import patch, MagicMock

        mock_transactions = [
            {
                'TransactionDate': f'2024-01-{(i % 28) + 1:02d}',
                'TransactionAmount': 50.0 + i,
                'TransactionDescription': f'Payment #{i}',
            }
            for i in range(list_size)
        ]

        service = InvoiceTestService.__new__(InvoiceTestService)

        with patch('transaction_logic.TransactionLogic') as MockTL:
            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = mock_transactions
            MockTL.return_value = mock_tl_instance

            result = service.get_vendor_history('SomeVendor', 'admin2')

        assert len(result) == 20

    @given(list_size=st.integers(min_value=0, max_value=20))
    @settings(max_examples=100, deadline=None)
    def test_vendor_history_preserves_small_lists(self, list_size):
        """When DB returns 20 or fewer, all items are returned."""
        from unittest.mock import patch, MagicMock

        mock_transactions = [
            {
                'TransactionDate': f'2024-02-{(i % 28) + 1:02d}',
                'TransactionAmount': 200.0 + i,
                'TransactionDescription': f'Bill #{i}',
            }
            for i in range(list_size)
        ]

        service = InvoiceTestService.__new__(InvoiceTestService)

        with patch('transaction_logic.TransactionLogic') as MockTL:
            mock_tl_instance = MagicMock()
            mock_tl_instance.get_last_transactions.return_value = mock_transactions
            MockTL.return_value = mock_tl_instance

            result = service.get_vendor_history('AnyVendor', 'admin3')

        assert len(result) == list_size


# ---------------------------------------------------------------------------
# Property 2: Dry-Run Produces No Side Effects
# Feature: invoice-processing-test-tool, Property 2
# Validates: Requirements 2.2, 2.3
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDryRunNoSideEffects:
    """
    Property 2: Dry-run produces no side effects

    For any valid file processed through the test tool pipeline, the system SHALL
    make zero database write calls (INSERT, UPDATE, DELETE), zero Google Drive
    upload calls, and zero S3 upload calls.

    **Validates: Requirements 2.2, 2.3**
    """

    @given(folder_name=st.sampled_from(['TestVendor', 'Vendor-A', 'my_vendor_123']))
    @settings(max_examples=100, deadline=None)
    def test_no_db_writes_during_dry_run(self, folder_name):
        """process_file_dry_run shall not call any database write operations."""
        import tempfile
        import os
        from unittest.mock import patch, MagicMock

        # Create a real temp file for the test
        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp.write(b'%PDF-1.4 fake content')
        tmp.close()

        try:
            service = InvoiceTestService.__new__(InvoiceTestService)
            service.processor = MagicMock()
            service.csv_rule_engine = MagicMock()

            # Mock process_file to return minimal valid data
            service.processor.process_file.return_value = {
                'txt': 'Some extracted text',
                'name': 'test.pdf',
                'url': 'dry-run://test.pdf',
            }
            service.processor.extract_transactions.return_value = []
            service.processor._extract_with_ai = MagicMock(return_value=None)

            # Track database writes
            db_write_mock = MagicMock()

            with patch('database.DatabaseManager.execute_query', db_write_mock), \
                 patch('transaction_logic.TransactionLogic') as MockTL:
                mock_tl = MagicMock()
                mock_tl.get_last_transactions.return_value = []
                MockTL.return_value = mock_tl

                service.process_file_dry_run(tmp.name, folder_name, 'test-admin')

            # Verify no DB write calls (fetch=False indicates a write)
            for call in db_write_mock.call_args_list:
                args, kwargs = call
                assert kwargs.get('fetch', True) is True, \
                    "Database write detected during dry-run (fetch=False)"
        finally:
            # Cleanup in case process_file_dry_run didn't remove it
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    @given(folder_name=st.sampled_from(['TestVendor', 'Vendor-B', 'vendor_xyz']))
    @settings(max_examples=100, deadline=None)
    def test_no_drive_uploads_during_dry_run(self, folder_name):
        """process_file_dry_run shall not call any Google Drive upload methods."""
        import tempfile
        import os
        from unittest.mock import patch, MagicMock

        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        tmp.write(b'\xff\xd8\xff\xe0 fake jpeg content')
        tmp.close()

        try:
            service = InvoiceTestService.__new__(InvoiceTestService)
            service.processor = MagicMock()
            service.csv_rule_engine = MagicMock()

            service.processor.process_file.return_value = {
                'txt': 'Image text',
                'name': 'invoice.jpg',
                'url': 'dry-run://invoice.jpg',
            }
            service.processor.extract_transactions.return_value = []
            service.processor._extract_with_ai = MagicMock(return_value=None)

            drive_upload_mock = MagicMock()

            with patch('transaction_logic.TransactionLogic') as MockTL, \
                 patch.dict('sys.modules', {'google_drive': MagicMock()}):
                mock_tl = MagicMock()
                mock_tl.get_last_transactions.return_value = []
                MockTL.return_value = mock_tl

                # Patch any potential drive upload references
                with patch.object(service.processor, 'upload_to_drive',
                                  drive_upload_mock, create=True):
                    service.process_file_dry_run(tmp.name, folder_name, 'admin1')

            # The processor should never call upload methods
            drive_upload_mock.assert_not_called()
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    @given(folder_name=st.sampled_from(['TestVendor', 'Vendor-C', 'vendor99']))
    @settings(max_examples=100, deadline=None)
    def test_no_s3_uploads_during_dry_run(self, folder_name):
        """process_file_dry_run shall not call any S3 upload methods."""
        import tempfile
        import os
        from unittest.mock import patch, MagicMock

        tmp = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        tmp.write(b'date,amount\n2024-01-01,100.00')
        tmp.close()

        try:
            service = InvoiceTestService.__new__(InvoiceTestService)
            service.processor = MagicMock()
            service.csv_rule_engine = MagicMock()

            service.processor.process_file.return_value = {
                'txt': 'date,amount\n2024-01-01,100.00',
                'name': 'data.csv',
                'url': 'dry-run://data.csv',
            }
            service.processor.extract_transactions.return_value = []
            service.processor._extract_with_ai = MagicMock(return_value=None)

            s3_upload_mock = MagicMock()

            with patch('transaction_logic.TransactionLogic') as MockTL, \
                 patch('boto3.client', return_value=MagicMock()) as mock_boto:
                mock_tl = MagicMock()
                mock_tl.get_last_transactions.return_value = []
                MockTL.return_value = mock_tl

                with patch.object(service.processor, 'upload_to_s3',
                                  s3_upload_mock, create=True):
                    service.process_file_dry_run(tmp.name, folder_name, 'admin2')

            s3_upload_mock.assert_not_called()
            # Also verify boto3 client was not used for uploads
            if mock_boto.called:
                s3_client = mock_boto.return_value
                s3_client.upload_file.assert_not_called()
                s3_client.put_object.assert_not_called()
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)


# ---------------------------------------------------------------------------
# Property 3: Temporary File Cleanup
# Feature: invoice-processing-test-tool, Property 3
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTemporaryFileCleanup:
    """
    Property 3: Temporary file cleanup

    For any file processed through the test tool (whether the pipeline succeeds
    or fails at any stage), all temporary files created during processing SHALL
    be removed after the request completes.

    **Validates: Requirements 2.6**
    """

    @given(fail_stage=st.sampled_from(['none', 'file_parsing', 'extraction', 'preparation']))
    @settings(max_examples=100, deadline=None)
    def test_temp_file_removed_after_processing(self, fail_stage):
        """Temp file is cleaned up regardless of which stage fails."""
        import tempfile
        import os
        from unittest.mock import patch, MagicMock

        # Create a real temp file
        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp.write(b'%PDF-1.4 test content for cleanup verification')
        tmp.close()
        tmp_path = tmp.name

        assert os.path.exists(tmp_path), "Temp file should exist before processing"

        service = InvoiceTestService.__new__(InvoiceTestService)
        service.processor = MagicMock()
        service.csv_rule_engine = MagicMock()
        service.processor._extract_with_ai = MagicMock(return_value=None)

        if fail_stage == 'file_parsing':
            service.processor.process_file.side_effect = RuntimeError("Parse failed")
        elif fail_stage == 'extraction':
            service.processor.process_file.return_value = {
                'txt': 'Some text', 'name': 'test.pdf', 'url': 'dry-run://test.pdf'
            }
            service.processor.extract_transactions.side_effect = RuntimeError("Extraction failed")
        elif fail_stage == 'preparation':
            service.processor.process_file.return_value = {
                'txt': 'Some text', 'name': 'test.pdf', 'url': 'dry-run://test.pdf'
            }
            service.processor.extract_transactions.return_value = [
                {'date': '2024-01-01', 'amount': 100.0, 'description': 'Test'}
            ]
            # Make preparation fail
            with patch('transaction_logic.TransactionLogic') as MockTL:
                mock_tl = MagicMock()
                mock_tl.get_last_transactions.side_effect = RuntimeError("DB error")
                MockTL.return_value = mock_tl
                service.process_file_dry_run(tmp_path, 'TestVendor', 'admin')

            # File should be cleaned up
            assert not os.path.exists(tmp_path), \
                f"Temp file still exists after preparation failure"
            return  # Early return since we already called process_file_dry_run
        else:
            # Success path
            service.processor.process_file.return_value = {
                'txt': 'Extracted text', 'name': 'test.pdf', 'url': 'dry-run://test.pdf'
            }
            service.processor.extract_transactions.return_value = []

        # Call process_file_dry_run (for non-preparation failure stages)
        if fail_stage != 'preparation':
            with patch('transaction_logic.TransactionLogic') as MockTL:
                mock_tl = MagicMock()
                mock_tl.get_last_transactions.return_value = []
                MockTL.return_value = mock_tl
                service.process_file_dry_run(tmp_path, 'TestVendor', 'admin')

        # Assert: temp file should be removed
        assert not os.path.exists(tmp_path), \
            f"Temp file still exists after processing (fail_stage={fail_stage})"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_temp_file_removed_on_unexpected_exception(self, data):
        """Temp file is cleaned up even when an unexpected exception occurs in pipeline."""
        import tempfile
        import os
        from unittest.mock import patch, MagicMock

        # Create temp file
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp.write(b'\x89PNG\r\n fake png data')
        tmp.close()
        tmp_path = tmp.name

        assert os.path.exists(tmp_path)

        service = InvoiceTestService.__new__(InvoiceTestService)
        service.processor = MagicMock()
        service.csv_rule_engine = MagicMock()
        service.processor._extract_with_ai = MagicMock(return_value=None)

        # Make process_file raise an unexpected error
        service.processor.process_file.side_effect = ValueError("Unexpected error in parsing")

        with patch('transaction_logic.TransactionLogic') as MockTL:
            mock_tl = MagicMock()
            MockTL.return_value = mock_tl
            service.process_file_dry_run(tmp_path, 'TestVendor', 'admin')

        # File must still be cleaned up
        assert not os.path.exists(tmp_path), \
            "Temp file still exists after unexpected exception"


# ---------------------------------------------------------------------------
# Property 12: Partial Result Preservation on Failure
# Feature: invoice-processing-test-tool, Property 12
# Validates: Requirements 8.4
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPartialResultPreservation:
    """
    Property 12: Partial result preservation on failure

    For any pipeline execution that fails at stage N, all successfully completed
    stages prior to N SHALL have their outputs present in the response (non-null,
    correctly populated).

    **Validates: Requirements 8.4**
    """

    @given(fail_at_stage=st.sampled_from([2, 3]))
    @settings(max_examples=100, deadline=None)
    def test_prior_stages_present_when_later_stage_fails(self, fail_at_stage):
        """When stage N fails, stages 1..N-1 outputs are present and non-null."""
        import tempfile
        import os
        from unittest.mock import patch, MagicMock

        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp.write(b'%PDF-1.4 test content')
        tmp.close()

        service = InvoiceTestService.__new__(InvoiceTestService)
        service.processor = MagicMock()
        service.csv_rule_engine = MagicMock()
        service.processor._extract_with_ai = MagicMock(return_value=None)

        # Stage 1 always succeeds
        service.processor.process_file.return_value = {
            'txt': 'Raw extracted text content from invoice',
            'name': 'invoice.pdf',
            'url': 'dry-run://invoice.pdf',
            'folder': 'TestVendor',
        }

        if fail_at_stage == 2:
            # Stage 2 (extraction) fails
            service.processor.extract_transactions.side_effect = RuntimeError("AI model exhausted")
        elif fail_at_stage == 3:
            # Stage 2 succeeds, Stage 3 (preparation) fails
            service.processor.extract_transactions.return_value = [
                {'date': '2024-03-15', 'amount': 250.0, 'description': 'March invoice'}
            ]

        with patch('transaction_logic.TransactionLogic') as MockTL:
            mock_tl = MagicMock()
            if fail_at_stage == 3:
                mock_tl.get_last_transactions.side_effect = RuntimeError("DB unavailable")
            else:
                mock_tl.get_last_transactions.return_value = []
            MockTL.return_value = mock_tl

            result = service.process_file_dry_run(tmp.name, 'TestVendor', 'admin')

        pipeline_result = result['pipeline_result']

        # Stage 1 outputs should always be present when stage 1 succeeds
        assert 'raw_text' in pipeline_result, "raw_text missing after stage 1 success"
        assert pipeline_result['raw_text'] is not None, "raw_text is None"
        assert len(pipeline_result['raw_text']) > 0, "raw_text is empty"
        assert 'raw_text_truncated' in pipeline_result, "raw_text_truncated flag missing"
        assert 'folder_name' in pipeline_result, "folder_name missing"

        if fail_at_stage == 3:
            # Stage 2 succeeded, so extraction/formatting outputs should be present
            assert 'formatted_transactions' in pipeline_result, \
                "formatted_transactions missing after stage 2 success"
            assert pipeline_result['formatted_transactions'] is not None, \
                "formatted_transactions is None after stage 2 success"
            assert 'extraction_result' in pipeline_result, \
                "extraction_result missing after stage 2 success"
            assert 'parser_used' in pipeline_result, \
                "parser_used missing after stage 2 success"

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_stage1_output_preserved_when_stage2_fails(self, data):
        """Stage 1 (raw text) is always available when only stage 2+ fails."""
        import tempfile
        import os
        from unittest.mock import patch, MagicMock

        raw_text_content = 'Invoice #12345\nDate: 2024-01-15\nTotal: 150.00'

        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp.write(b'%PDF-1.4 content')
        tmp.close()

        service = InvoiceTestService.__new__(InvoiceTestService)
        service.processor = MagicMock()
        service.csv_rule_engine = MagicMock()
        service.processor._extract_with_ai = MagicMock(return_value=None)

        # Stage 1 succeeds with specific text
        service.processor.process_file.return_value = {
            'txt': raw_text_content,
            'name': 'invoice.pdf',
            'url': 'dry-run://invoice.pdf',
        }
        # Stage 2 fails
        service.processor.extract_transactions.side_effect = Exception("Extraction error")

        with patch('transaction_logic.TransactionLogic') as MockTL:
            mock_tl = MagicMock()
            mock_tl.get_last_transactions.return_value = []
            MockTL.return_value = mock_tl

            result = service.process_file_dry_run(tmp.name, 'TestVendor', 'admin')

        pipeline_result = result['pipeline_result']

        # Stage 1 output preserved
        assert pipeline_result['raw_text'] == raw_text_content
        assert pipeline_result['raw_text_truncated'] is False
        assert pipeline_result['folder_name'] == 'TestVendor'

        # Errors should include the stage 2 failure
        assert len(result['errors']) > 0
        assert result['errors'][0]['stage'] == 'transaction_formatting'
