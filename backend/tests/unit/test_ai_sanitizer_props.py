"""
Property-based tests for AI Prompt Injection Prevention (AISanitizer).

Feature: security-hardening, Properties 7–10

Tests the AISanitizer class against universal correctness properties
using Hypothesis to generate varied inputs.
"""

import os
import sys
import re
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'services'))

from services.ai_sanitizer import AISanitizer, SanitizeResult


# --- Test Configuration ---

sanitizer = AISanitizer()

# The injection patterns as raw regex strings (matching AISanitizer.INJECTION_PATTERNS)
INJECTION_PATTERN_REGEXES = [
    re.compile(r'(?i)\b(you are now|act as|pretend to be|assume the role)\b'),
    re.compile(r'(?i)\b(ignore previous|disregard above|forget all|override instructions)\b'),
    re.compile(r'(?i)\[SYSTEM\]'),
    re.compile(r'(?i)###\s*(system|instruction|prompt)'),
    re.compile(r'(?i)\b(new instructions?|updated instructions?)\s*:'),
]

# Concrete injection pattern examples to embed in generated text
INJECTION_EXAMPLES = [
    "you are now",
    "act as",
    "pretend to be",
    "assume the role",
    "ignore previous",
    "disregard above",
    "forget all",
    "override instructions",
    "[SYSTEM]",
    "### system",
    "### instruction",
    "### prompt",
    "new instructions:",
    "new instruction:",
    "updated instructions:",
    "updated instruction:",
]


# --- Hypothesis Strategies ---

# Strategy for safe filler text that won't accidentally match injection patterns
safe_filler = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        blacklist_characters="\x00#[]",
    ),
    min_size=0,
    max_size=200,
).filter(
    lambda t: not any(p.search(t) for p in INJECTION_PATTERN_REGEXES)
)

# Strategy to pick one injection pattern example
injection_pattern_st = st.sampled_from(INJECTION_EXAMPLES)

# Strategy for number of injection patterns to embed (at least 1)
num_injections_st = st.integers(min_value=1, max_value=5)


# =============================================================================
# Property 7: AI Injection Pattern Removal
# Feature: security-hardening, Property 7: AI Injection Pattern Removal
# **Validates: Requirements 4.1**
# =============================================================================

class TestAIInjectionPatternRemoval:
    """
    Property 7: For any text string containing one or more known injection
    patterns, after sanitization the resulting text SHALL NOT match any of
    the injection pattern regexes.
    """

    @given(
        filler_parts=st.lists(safe_filler, min_size=2, max_size=6),
        injections=st.lists(injection_pattern_st, min_size=1, max_size=5),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_injection_patterns_removed_from_output(self, filler_parts, injections):
        """
        Generate text with embedded injection patterns at random positions,
        verify sanitized output matches none of the injection regexes.

        # Feature: security-hardening, Property 7: AI Injection Pattern Removal
        # **Validates: Requirements 4.1**
        """
        # Build text by interleaving filler with injection patterns
        parts = []
        for i, filler in enumerate(filler_parts):
            parts.append(filler)
            if i < len(injections):
                parts.append(injections[i])
        # Append any remaining injections
        for j in range(len(filler_parts) - 1, len(injections)):
            parts.append(injections[j])

        text = " ".join(parts)
        assume(len(text) > 0)

        result = sanitizer.sanitize(text)

        # If not rejected, the sanitized output must not contain any injection patterns
        if not result.rejected:
            for pattern in INJECTION_PATTERN_REGEXES:
                assert not pattern.search(result.text), (
                    f"Injection pattern still present in sanitized output: "
                    f"pattern={pattern.pattern}, output={result.text!r}"
                )

    @given(
        injection=injection_pattern_st,
        prefix=safe_filler,
        suffix=safe_filler,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_single_injection_always_removed(self, injection, prefix, suffix):
        """
        For any single injection pattern embedded between safe text,
        the sanitized output does not contain that pattern.

        # Feature: security-hardening, Property 7: AI Injection Pattern Removal
        # **Validates: Requirements 4.1**
        """
        text = f"{prefix} {injection} {suffix}"
        result = sanitizer.sanitize(text)

        if not result.rejected:
            for pattern in INJECTION_PATTERN_REGEXES:
                assert not pattern.search(result.text), (
                    f"Pattern still present: {pattern.pattern}"
                )


# =============================================================================
# Property 8: AI Text Truncation
# Feature: security-hardening, Property 8: AI Text Truncation
# **Validates: Requirements 4.4**
# =============================================================================

class TestAITextTruncation:
    """
    Property 8: For any text string with length greater than 10000 characters,
    the sanitized output length SHALL be less than or equal to 10000 characters.
    """

    @given(
        length=st.integers(min_value=10001, max_value=20000),
        char=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789 "),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example])
    def test_long_text_truncated_to_max_length(self, length, char):
        """
        Generate strings of length > 10000, verify sanitized output ≤ 10000 characters.

        # Feature: security-hardening, Property 8: AI Text Truncation
        # **Validates: Requirements 4.4**
        """
        text = char * length
        result = sanitizer.sanitize(text)

        # Text should not be rejected (no injection patterns present)
        assert not result.rejected
        assert len(result.text) <= AISanitizer.MAX_TEXT_LENGTH
        assert result.was_truncated is True

    @given(
        length=st.integers(min_value=10001, max_value=20000),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_repeated_char_truncation(self, length):
        """
        For any text of length > MAX_TEXT_LENGTH composed of a safe character,
        the output is truncated to exactly MAX_TEXT_LENGTH.

        # Feature: security-hardening, Property 8: AI Text Truncation
        # **Validates: Requirements 4.4**
        """
        text = "a" * length
        result = sanitizer.sanitize(text)

        assert not result.rejected
        assert len(result.text) == AISanitizer.MAX_TEXT_LENGTH
        assert result.was_truncated is True


# =============================================================================
# Property 9: AI Response Validation
# Feature: security-hardening, Property 9: AI Response Validation
# **Validates: Requirements 4.5**
# =============================================================================

# Strategy for valid response dicts
valid_response_st = st.fixed_dictionaries({
    'date': st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""),
    'total_amount': st.one_of(st.integers(min_value=0, max_value=100000), st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)),
    'vat_amount': st.one_of(st.integers(min_value=0, max_value=100000), st.floats(min_value=0, max_value=100000, allow_nan=False, allow_infinity=False)),
    'description': st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != ""),
    'vendor': st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != ""),
})

# Required fields for the response
REQUIRED_FIELDS = ['date', 'total_amount', 'vat_amount', 'description', 'vendor']

# Strategy for wrong-typed values (not matching expected types)
wrong_type_for_string = st.one_of(
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.lists(st.integers(), max_size=3),
    st.just(None),
    st.booleans(),
)

wrong_type_for_number = st.one_of(
    st.text(min_size=1, max_size=10),
    st.lists(st.integers(), max_size=3),
    st.just(None),
    st.booleans(),
)


class TestAIResponseValidation:
    """
    Property 9: For any response dictionary, validate_response SHALL return
    False if any required field is missing or has the wrong type, and True
    for valid responses.
    """

    @given(response=valid_response_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_response_accepted(self, response):
        """
        For any dict with all required fields and correct types,
        validate_response returns True.

        # Feature: security-hardening, Property 9: AI Response Validation
        # **Validates: Requirements 4.5**
        """
        result = sanitizer.validate_response(response)
        assert result is True, f"Valid response rejected: {response}"

    @given(
        response=valid_response_st,
        field_to_remove=st.sampled_from(REQUIRED_FIELDS),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_field_rejected(self, response, field_to_remove):
        """
        For any valid response with one required field removed,
        validate_response returns False.

        # Feature: security-hardening, Property 9: AI Response Validation
        # **Validates: Requirements 4.5**
        """
        incomplete_response = dict(response)
        del incomplete_response[field_to_remove]

        result = sanitizer.validate_response(incomplete_response)
        assert result is False, (
            f"Response with missing '{field_to_remove}' was accepted: {incomplete_response}"
        )

    @given(
        response=valid_response_st,
        wrong_value=wrong_type_for_number,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_wrong_type_for_amount_fields_rejected(self, response, wrong_value):
        """
        For any valid response where total_amount or vat_amount has wrong type,
        validate_response returns False.

        # Feature: security-hardening, Property 9: AI Response Validation
        # **Validates: Requirements 4.5**
        """
        # Mutate one of the number fields with a wrong type
        bad_response = dict(response)
        bad_response['total_amount'] = wrong_value

        result = sanitizer.validate_response(bad_response)
        assert result is False, (
            f"Response with wrong type total_amount={wrong_value!r} was accepted"
        )

    @given(
        response=valid_response_st,
        wrong_value=wrong_type_for_string,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_wrong_type_for_string_fields_rejected(self, response, wrong_value):
        """
        For any valid response where a string field has wrong type,
        validate_response returns False.

        # Feature: security-hardening, Property 9: AI Response Validation
        # **Validates: Requirements 4.5**
        """
        bad_response = dict(response)
        bad_response['vendor'] = wrong_value

        result = sanitizer.validate_response(bad_response)
        assert result is False, (
            f"Response with wrong type vendor={wrong_value!r} was accepted"
        )

    @given(
        data=st.one_of(
            st.just(None),
            st.just("string"),
            st.just(42),
            st.just([]),
            st.just(True),
        )
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_dict_input_rejected(self, data):
        """
        For any non-dict input, validate_response returns False.

        # Feature: security-hardening, Property 9: AI Response Validation
        # **Validates: Requirements 4.5**
        """
        result = sanitizer.validate_response(data)
        assert result is False

    @given(response=valid_response_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_boolean_in_numeric_field_rejected(self, response):
        """
        Booleans should be rejected even though bool is subclass of int.

        # Feature: security-hardening, Property 9: AI Response Validation
        # **Validates: Requirements 4.5**
        """
        bad_response = dict(response)
        bad_response['total_amount'] = True

        result = sanitizer.validate_response(bad_response)
        assert result is False, "Boolean should be rejected in numeric field"


# =============================================================================
# Property 10: AI Rejection Threshold
# Feature: security-hardening, Property 10: AI Rejection Threshold
# **Validates: Requirements 4.6**
# =============================================================================

class TestAIRejectionThreshold:
    """
    Property 10: For any text string where the sanitization process removes
    more than 50% of the original character count, the sanitizer SHALL reject
    the text and return a rejection result.
    """

    @given(
        injections=st.lists(
            injection_pattern_st,
            min_size=10,
            max_size=30,
        ),
        filler=st.text(
            alphabet=st.characters(
                whitelist_categories=("L",),
                blacklist_characters="\x00",
            ),
            min_size=0,
            max_size=20,
        ).filter(lambda t: not any(p.search(t) for p in INJECTION_PATTERN_REGEXES)),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
    def test_majority_injection_text_rejected(self, injections, filler):
        """
        Generate text where >50% is injection patterns, verify sanitizer
        returns rejection result.

        # Feature: security-hardening, Property 10: AI Rejection Threshold
        # **Validates: Requirements 4.6**
        """
        # Build text that is majority injection patterns
        # Use many injection patterns with minimal filler
        injection_text = " ".join(injections)
        text = f"{filler} {injection_text}"

        assume(len(text) > 0)

        # Calculate expected removal ratio
        result = sanitizer.sanitize(text)

        # Calculate actual removal ratio
        original_length = len(text)
        sanitized_length = len(result.text) if not result.rejected else 0

        if original_length > 0:
            removed_ratio = 1 - (sanitized_length / original_length)

            if removed_ratio > AISanitizer.REJECTION_THRESHOLD:
                assert result.rejected is True, (
                    f"Text with {removed_ratio:.1%} removed should be rejected. "
                    f"Original: {original_length}, Sanitized: {sanitized_length}"
                )

    @given(
        repeat_count=st.integers(min_value=5, max_value=20),
        injection=injection_pattern_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_repeated_injection_pattern_triggers_rejection(self, repeat_count, injection):
        """
        Text composed primarily of repeated injection patterns should be rejected.

        # Feature: security-hardening, Property 10: AI Rejection Threshold
        # **Validates: Requirements 4.6**
        """
        # Create text that's overwhelmingly injection patterns
        text = (injection + " ") * repeat_count

        result = sanitizer.sanitize(text)

        # The injection portion after removal should exceed 50% threshold
        # Since text is nearly all injection patterns, it should be rejected
        assert result.rejected is True, (
            f"Text of {repeat_count} repeated '{injection}' should be rejected. "
            f"Result: rejected={result.rejected}, patterns_removed={result.patterns_removed}"
        )

    @given(
        safe_text=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Zs"),
                blacklist_characters="\x00#[]",
            ),
            min_size=100,
            max_size=500,
        ).filter(lambda t: not any(p.search(t) for p in INJECTION_PATTERN_REGEXES)),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
    def test_clean_text_not_rejected(self, safe_text):
        """
        Text without injection patterns should never be rejected.

        # Feature: security-hardening, Property 10: AI Rejection Threshold
        # **Validates: Requirements 4.6**
        """
        result = sanitizer.sanitize(safe_text)

        assert result.rejected is False, (
            f"Clean text was incorrectly rejected: {safe_text!r}"
        )
        assert result.patterns_removed == 0
