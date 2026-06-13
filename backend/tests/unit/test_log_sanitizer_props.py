"""
Property-based tests for Sensitive Data Logging Prevention (log_sanitizer).

Feature: security-hardening, Property 15: Sensitive Value Masking

Tests the mask_sensitive_value function against universal correctness properties
using Hypothesis to generate varied inputs.
"""

import os
import sys
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils.log_sanitizer import mask_sensitive_value, is_sensitive_key, REDACTED


# --- Test Configuration ---

# Known sensitive key base patterns that trigger masking
SENSITIVE_BASE_PATTERNS = [
    "api_key",
    "password",
    "encryption_key",
    "oauth_secret",
    "oauth_client_secret",
    "jwt_key",
    "jwt_signing_key",
    "secret_key",
    "access_token",
    "refresh_token",
    "private_key",
    "client_secret",
]

# Prefixes and suffixes to create realistic key variations
KEY_PREFIXES = ["", "my_", "db_", "app_", "OPENROUTER_", "AWS_", "GOOGLE_", ""]
KEY_SUFFIXES = ["", "_value", "_v2", "_prod", ""]


# --- Hypothesis Strategies ---

# Strategy for generating sensitive key names by combining patterns with prefixes/suffixes
sensitive_key_st = st.builds(
    lambda prefix, base, suffix: f"{prefix}{base}{suffix}",
    prefix=st.sampled_from(KEY_PREFIXES),
    base=st.sampled_from(SENSITIVE_BASE_PATTERNS),
    suffix=st.sampled_from(KEY_SUFFIXES),
)

# Strategy for generating case variations of sensitive keys
sensitive_key_case_st = st.builds(
    lambda key, case: key.upper() if case == "upper" else (key.lower() if case == "lower" else key.title()),
    key=sensitive_key_st,
    case=st.sampled_from(["upper", "lower", "mixed"]),
)

# Strategy for generating secret values (length 5-100 as specified)
secret_value_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00",
    ),
    min_size=5,
    max_size=100,
)

# Strategy for non-sensitive key names that should NOT trigger masking
non_sensitive_key_st = st.sampled_from([
    "host",
    "port",
    "database_name",
    "log_level",
    "app_name",
    "timeout",
    "max_retries",
    "region",
    "environment",
    "version",
    "debug_mode",
    "cache_ttl",
    "batch_size",
    "worker_count",
    "output_format",
])


# =============================================================================
# Property 15: Sensitive Value Masking
# Feature: security-hardening, Property 15: Sensitive Value Masking
# **Validates: Requirements 8.2, 8.4**
# =============================================================================

class TestSensitiveValueMasking:
    """
    Property 15: For any (key_name, secret_value) pair where key_name matches
    a known sensitive pattern, the mask_sensitive_value function SHALL return
    "[REDACTED]" and the return value SHALL NOT contain any substring of
    length >= 3 from the original secret_value.
    """

    @given(
        key=sensitive_key_st,
        secret=secret_value_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_sensitive_key_returns_redacted(self, key, secret):
        """
        For any key matching a sensitive pattern with any secret value,
        mask_sensitive_value returns exactly "[REDACTED]".

        # Feature: security-hardening, Property 15: Sensitive Value Masking
        # **Validates: Requirements 8.2, 8.4**
        """
        # Precondition: key must actually match a sensitive pattern
        assume(is_sensitive_key(key))

        result = mask_sensitive_value(key, secret)
        assert result == REDACTED, (
            f"Expected '[REDACTED]' for sensitive key '{key}', got: {result!r}"
        )

    @given(
        key=sensitive_key_case_st,
        secret=secret_value_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_sensitive_key_case_insensitive(self, key, secret):
        """
        Sensitive key matching is case-insensitive: upper, lower, and mixed
        case variants all return "[REDACTED]".

        # Feature: security-hardening, Property 15: Sensitive Value Masking
        # **Validates: Requirements 8.2, 8.4**
        """
        assume(is_sensitive_key(key))

        result = mask_sensitive_value(key, secret)
        assert result == REDACTED, (
            f"Expected '[REDACTED]' for case-variant key '{key}', got: {result!r}"
        )

    @given(
        key=sensitive_key_st,
        secret=secret_value_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_no_secret_substring_leaks_in_result(self, key, secret):
        """
        The return value SHALL NOT contain any substring of length >= 3 from
        the original secret_value, preventing partial credential exposure.

        # Feature: security-hardening, Property 15: Sensitive Value Masking
        # **Validates: Requirements 8.2, 8.4**
        """
        assume(is_sensitive_key(key))

        result = mask_sensitive_value(key, secret)

        # Check that no substring of length >= 3 from the secret appears in the result
        for i in range(len(secret) - 2):
            substring = secret[i:i + 3]
            assert substring not in result, (
                f"Secret substring '{substring}' (from position {i}) "
                f"leaked into result '{result}' for key '{key}'"
            )

    @given(
        key=non_sensitive_key_st,
        value=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_sensitive_key_returns_original_value(self, key, value):
        """
        For any key that does NOT match a sensitive pattern, the function
        SHALL return str(value) unchanged (no masking applied).

        # Feature: security-hardening, Property 15: Sensitive Value Masking
        # **Validates: Requirements 8.2, 8.4**
        """
        assume(not is_sensitive_key(key))

        result = mask_sensitive_value(key, value)
        assert result == str(value), (
            f"Non-sensitive key '{key}' should return original value "
            f"'{value}', got: {result!r}"
        )

    @given(
        key=sensitive_key_st,
        value=st.one_of(
            st.integers(min_value=-1000, max_value=1000),
            st.floats(allow_nan=False, allow_infinity=False, min_value=-1000, max_value=1000),
            st.booleans(),
            st.just(None),
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_sensitive_key_masks_any_value_type(self, key, value):
        """
        Sensitive masking applies regardless of the value's type — even
        non-string values (int, float, bool, None) are redacted.

        # Feature: security-hardening, Property 15: Sensitive Value Masking
        # **Validates: Requirements 8.2, 8.4**
        """
        assume(is_sensitive_key(key))

        result = mask_sensitive_value(key, value)
        assert result == REDACTED, (
            f"Expected '[REDACTED]' for sensitive key '{key}' with value "
            f"type {type(value).__name__}, got: {result!r}"
        )
