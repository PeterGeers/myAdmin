"""
Property-based tests for security_audit module.

Uses Hypothesis to verify correctness properties from the design document.
Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance

Requirements: 3.3
Reference: .kiro/specs/missing-py-tests/design.md
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import patch, MagicMock

from security_audit import SecurityAudit


# Known SQL injection patterns that MUST always be detected
KNOWN_PATTERNS = [
    "1=1",
    "OR 1=1",
    'OR ""=""',
    "OR ''=''",
    "UNION SELECT",
    "EXEC ",
    "DROP TABLE",
    "INSERT INTO",
    "DELETE FROM",
]


@st.composite
def sql_with_injection(draw):
    """Generate a SQL query containing a known injection pattern with surrounding text."""
    pattern = draw(st.sampled_from(KNOWN_PATTERNS))
    prefix = draw(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'Z')),
        min_size=0,
        max_size=30
    ))
    suffix = draw(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'Z')),
        min_size=0,
        max_size=30
    ))
    return f"{prefix} {pattern} {suffix}"


@st.composite
def sql_with_injection_casing(draw):
    """Generate injection patterns with random casing variations."""
    pattern = draw(st.sampled_from(KNOWN_PATTERNS))
    # Apply random casing to each character
    cased = ""
    for char in pattern:
        if draw(st.booleans()):
            cased += char.upper()
        else:
            cased += char.lower()
    prefix = draw(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'Z')),
        min_size=0,
        max_size=20
    ))
    return f"{prefix} {cased}"


@st.composite
def sql_with_injection_whitespace(draw):
    """Generate injection patterns with extra whitespace variations."""
    pattern = draw(st.sampled_from(KNOWN_PATTERNS))
    # Add extra whitespace between words (only space characters)
    words = pattern.split()
    if len(words) > 1:
        spaces = draw(st.sampled_from(['  ', '   ', '\t', ' \t ']))
        spaced_pattern = spaces.join(words)
    else:
        spaced_pattern = pattern
    return f"SELECT * FROM users WHERE {spaced_pattern}"


# ---------------------------------------------------------------------------
# Property 3: SQL Injection Detection Invariance
# Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------

class TestSqlInjectionDetectionInvariance:
    """
    Property 3: SQL Injection Detection Invariance

    For any string containing a known SQL injection pattern (e.g., ' OR 1=1 --,
    ; DROP TABLE, UNION SELECT), check_sql_injection SHALL detect the threat
    regardless of surrounding text content, casing, or whitespace variations.

    Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance
    **Validates: Requirements 3.3**
    """

    @pytest.fixture(autouse=True)
    def setup_audit(self, mock_db):
        """Create SecurityAudit instance for all tests."""
        with patch('security_audit.DatabaseManager', return_value=mock_db):
            self.audit = SecurityAudit()

    @settings(max_examples=100)
    @given(query=sql_with_injection())
    def test_known_patterns_detected_regardless_of_surrounding_text(self, query):
        """
        Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance

        For any query containing a known SQL injection pattern surrounded by
        arbitrary text, check_sql_injection SHALL detect the threat.
        """
        result = self.audit.check_sql_injection(query)
        assert result['safe'] is False, (
            f"Expected unsafe for query containing injection pattern: {query!r}"
        )

    @settings(max_examples=100)
    @given(query=sql_with_injection_casing())
    def test_known_patterns_detected_regardless_of_casing(self, query):
        """
        Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance

        For any query containing a known SQL injection pattern with arbitrary
        casing, check_sql_injection SHALL detect the threat.
        """
        result = self.audit.check_sql_injection(query)
        assert result['safe'] is False, (
            f"Expected unsafe for case-varied query: {query!r}"
        )

    @settings(max_examples=100)
    @given(query=sql_with_injection_whitespace())
    def test_known_patterns_detected_regardless_of_whitespace(self, query):
        """
        Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance

        For any query containing a known SQL injection pattern with whitespace
        variations, check_sql_injection SHALL detect the threat.
        """
        result = self.audit.check_sql_injection(query)
        assert result['safe'] is False, (
            f"Expected unsafe for whitespace-varied query: {query!r}"
        )

    @settings(max_examples=100)
    @given(query=sql_with_injection())
    def test_detection_never_raises_exception(self, query):
        """
        Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance

        For any input, check_sql_injection SHALL never raise an exception —
        it always returns a result dict.
        """
        result = self.audit.check_sql_injection(query)
        assert isinstance(result, dict)
        assert 'safe' in result
        assert 'issues' in result
        assert isinstance(result['safe'], bool)
        assert isinstance(result['issues'], list)
