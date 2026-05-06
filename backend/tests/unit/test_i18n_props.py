"""
Property-based tests for i18n module.

Uses Hypothesis to verify correctness properties from the design document.
Feature: missing-py-tests, Property 4: Locale Detection Totality

Requirements: 3.4
Reference: .kiro/specs/missing-py-tests/design.md
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from flask import Flask

from i18n import get_locale


SUPPORTED_LOCALES = {'nl', 'en'}

# Strategy: valid HTTP header values (no newline characters — Werkzeug rejects those
# at the transport layer before they ever reach application code)
header_text_st = st.text(max_size=100).filter(
    lambda s: '\r' not in s and '\n' not in s
)


# ---------------------------------------------------------------------------
# Property 4: Locale Detection Totality
# Feature: missing-py-tests, Property 4: Locale Detection Totality
# Validates: Requirements 3.4
# ---------------------------------------------------------------------------

class TestLocaleDetectionTotality:
    """
    Property 4: Locale Detection Totality

    For any string value passed as an X-Language header (including empty,
    malformed, or adversarial inputs), get_locale SHALL return a value from
    the supported locale set {'nl', 'en'} — never None, never an unsupported locale.

    Feature: missing-py-tests, Property 4: Locale Detection Totality
    **Validates: Requirements 3.4**
    """

    @settings(max_examples=100)
    @given(header_value=header_text_st)
    def test_any_header_value_returns_supported_locale(self, header_value):
        """
        Feature: missing-py-tests, Property 4: Locale Detection Totality

        For any arbitrary X-Language header value, get_locale always returns
        a value from {'nl', 'en'}.
        """
        app = Flask(__name__)
        with app.test_request_context(headers={'X-Language': header_value}):
            result = get_locale()

        assert result is not None, "get_locale returned None"
        assert result in SUPPORTED_LOCALES, (
            f"get_locale returned '{result}' which is not in {SUPPORTED_LOCALES}"
        )

    @settings(max_examples=100)
    @given(header_value=st.one_of(
        header_text_st,
        st.just(''),
        st.sampled_from(['nl', 'en', 'fr', 'de', 'es', 'NL', 'EN', 'nl-NL', 'en-US']),
        st.binary(max_size=50).map(
            lambda b: b.decode('utf-8', errors='replace').replace('\r', '').replace('\n', '')
        ),
    ))
    def test_diverse_inputs_always_return_supported_locale(self, header_value):
        """
        Feature: missing-py-tests, Property 4: Locale Detection Totality

        For diverse inputs including binary-decoded strings, locale codes,
        and arbitrary text, get_locale always returns a supported locale.
        """
        app = Flask(__name__)
        with app.test_request_context(headers={'X-Language': header_value}):
            result = get_locale()

        assert result in SUPPORTED_LOCALES, (
            f"get_locale returned '{result}' for input '{header_value[:20]}...'"
        )
