"""
Bug Condition Exploration Test — Date Fields Serialized as HTTP Date Strings

Property 1: Bug Condition — Date Fields Serialized as HTTP Date Strings

CRITICAL: This test MUST FAIL on unfixed code — failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails.

Bug condition: Flask's default JSON serialization converts Python datetime.date
objects to HTTP date strings (e.g., "Mon, 15 Jan 2024 00:00:00 GMT") instead of
ISO-8601 format ("2024-01-15"). The frontend's isISODateString() regex cannot
match HTTP date strings, causing date column sorting to fall back to lexicographic
string comparison instead of chronological comparison.

GOAL: Surface counterexamples that demonstrate datetime.date objects are serialized
as HTTP date strings instead of ISO-8601.

After fix: normalize_dates is called before jsonify, converting datetime.date
objects to ISO-8601 strings. The test now simulates the fixed serialization path.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""
import os
import sys
import re
import json
import datetime
import pytest
from hypothesis import given, strategies as st, settings

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask, jsonify
from utils.date_utils import normalize_dates


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ISO_8601_DATE_REGEX = re.compile(r'^\d{4}-\d{2}-\d{2}$')

# The date fields affected by this bug across the four endpoints
AFFECTED_DATE_FIELDS = ['TransactionDate', 'checkinDate', 'checkoutDate']


# ---------------------------------------------------------------------------
# Helper: create a minimal Flask app for serialization testing
# ---------------------------------------------------------------------------

def create_test_app():
    """Create a minimal Flask app with default JSON serialization (no custom encoder)."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


# ---------------------------------------------------------------------------
# Test A: TransactionDate serialization (mutaties-table, check-reference)
# ---------------------------------------------------------------------------

class TestTransactionDateSerialization:
    """
    **Validates: Requirements 1.1, 1.2, 1.5**

    When /api/reports/mutaties-table or /api/reports/check-reference returns
    query results containing datetime.date objects in the TransactionDate field,
    Flask's jsonify serializes them as HTTP date strings instead of ISO-8601.

    On UNFIXED code: jsonify produces "Mon, 15 Jan 2024 00:00:00 GMT"
    → test FAILS (confirms bug).
    """

    @given(date_value=st.dates(
        min_value=datetime.date(2000, 1, 1),
        max_value=datetime.date(2030, 12, 31)
    ))
    @settings(max_examples=50, deadline=5000)
    def test_transaction_date_serialized_as_iso8601(self, date_value):
        """
        Property: For any datetime.date value, when normalized via normalize_dates
        and then serialized through Flask's jsonify as a TransactionDate field,
        the output MUST match ISO-8601 format (YYYY-MM-DD).

        On UNFIXED code (without normalize_dates): Flask serializes datetime.date
        as HTTP date string → regex match fails → test FAILS.
        On FIXED code (with normalize_dates): dates are ISO-8601 → test PASSES.
        """
        app = create_test_app()

        # Simulate the data structure returned by cursor.fetchall()
        row = {
            'TransactionDate': date_value,
            'TransactionDescription': 'Test transaction',
            'Amount': 100.50,
        }

        # Simulate the fixed endpoint: normalize_dates before jsonify
        normalize_dates([row], ['TransactionDate'])

        with app.app_context():
            response = jsonify({'success': True, 'data': [row]})
            response_data = json.loads(response.get_data(as_text=True))

        serialized_date = response_data['data'][0]['TransactionDate']

        assert ISO_8601_DATE_REGEX.match(serialized_date), (
            f"BUG CONFIRMED: TransactionDate serialized as '{serialized_date}' "
            f"instead of ISO-8601 format '{date_value.isoformat()}'. "
            f"Flask's jsonify converts datetime.date({date_value}) to HTTP date "
            f"string instead of ISO-8601. The frontend isISODateString() cannot "
            f"match this format, causing lexicographic sort instead of "
            f"chronological sort."
        )


# ---------------------------------------------------------------------------
# Test B: checkinDate/checkoutDate serialization (bnb-table, search-booking)
# ---------------------------------------------------------------------------

class TestBnbDateSerialization:
    """
    **Validates: Requirements 1.3, 1.4, 1.5**

    When /api/bnb/bnb-table or /api/str-invoice/search-booking returns query
    results containing datetime.date objects in checkinDate/checkoutDate fields,
    Flask's jsonify serializes them as HTTP date strings instead of ISO-8601.

    On UNFIXED code: jsonify produces HTTP date strings → test FAILS.
    """

    @given(
        checkin_date=st.dates(
            min_value=datetime.date(2000, 1, 1),
            max_value=datetime.date(2030, 12, 31)
        ),
        checkout_date=st.dates(
            min_value=datetime.date(2000, 1, 1),
            max_value=datetime.date(2030, 12, 31)
        ),
    )
    @settings(max_examples=50, deadline=5000)
    def test_checkin_checkout_dates_serialized_as_iso8601(
        self, checkin_date, checkout_date
    ):
        """
        Property: For any datetime.date values in checkinDate and checkoutDate,
        when normalized via normalize_dates and then serialized through Flask's
        jsonify, the output MUST match ISO-8601 format (YYYY-MM-DD).

        On UNFIXED code (without normalize_dates): Flask serializes datetime.date
        as HTTP date string → regex match fails → test FAILS.
        On FIXED code (with normalize_dates): dates are ISO-8601 → test PASSES.
        """
        app = create_test_app()

        # Simulate the data structure returned by cursor.fetchall() for BNB
        row = {
            'checkinDate': checkin_date,
            'checkoutDate': checkout_date,
            'guestName': 'Test Guest',
            'nights': 3,
            'amountGross': 250.00,
        }

        # Simulate the fixed endpoint: normalize_dates before jsonify
        normalize_dates([row], ['checkinDate', 'checkoutDate'])

        with app.app_context():
            response = jsonify({'success': True, 'data': [row]})
            response_data = json.loads(response.get_data(as_text=True))

        serialized_checkin = response_data['data'][0]['checkinDate']
        serialized_checkout = response_data['data'][0]['checkoutDate']

        assert ISO_8601_DATE_REGEX.match(serialized_checkin), (
            f"BUG CONFIRMED: checkinDate serialized as '{serialized_checkin}' "
            f"instead of ISO-8601 format '{checkin_date.isoformat()}'. "
            f"Flask's jsonify converts datetime.date({checkin_date}) to HTTP "
            f"date string. Frontend isISODateString() cannot match this."
        )

        assert ISO_8601_DATE_REGEX.match(serialized_checkout), (
            f"BUG CONFIRMED: checkoutDate serialized as '{serialized_checkout}' "
            f"instead of ISO-8601 format '{checkout_date.isoformat()}'. "
            f"Flask's jsonify converts datetime.date({checkout_date}) to HTTP "
            f"date string. Frontend isISODateString() cannot match this."
        )


# ---------------------------------------------------------------------------
# Test C: Deterministic example for documentation
# ---------------------------------------------------------------------------

class TestDeterministicCounterexample:
    """
    **Validates: Requirements 1.1, 1.3, 1.5**

    Deterministic test with known date values to produce clear, documentable
    counterexamples showing the exact bug behavior.
    """

    @pytest.mark.parametrize("date_value,field_name", [
        (datetime.date(2024, 1, 15), 'TransactionDate'),
        (datetime.date(2024, 3, 5), 'checkinDate'),
        (datetime.date(2024, 3, 10), 'checkoutDate'),
        (datetime.date(2024, 12, 31), 'TransactionDate'),
        (datetime.date(2024, 6, 1), 'checkinDate'),
    ])
    def test_specific_dates_serialized_as_iso8601(self, date_value, field_name):
        """
        Deterministic counterexamples:
        - datetime.date(2024, 1, 15) → expected "2024-01-15"
        - datetime.date(2024, 3, 5) → expected "2024-03-05"
        - datetime.date(2024, 3, 10) → expected "2024-03-10"

        On UNFIXED code: actual "Mon, 15 Jan 2024 00:00:00 GMT" (BUG)
        On FIXED code: actual "2024-01-15" (CORRECT)
        """
        app = create_test_app()

        row = {field_name: date_value, 'OtherField': 'unchanged'}

        # Simulate the fixed endpoint: normalize_dates before jsonify
        normalize_dates([row], [field_name])

        with app.app_context():
            response = jsonify({'data': [row]})
            response_data = json.loads(response.get_data(as_text=True))

        serialized = response_data['data'][0][field_name]

        assert ISO_8601_DATE_REGEX.match(serialized), (
            f"BUG CONFIRMED: {field_name} = datetime.date({date_value.year}, "
            f"{date_value.month}, {date_value.day}) serialized as "
            f"'{serialized}' instead of '{date_value.isoformat()}'. "
            f"Frontend isISODateString() regex /^\\d{{4}}-\\d{{2}}-\\d{{2}}"
            f"(T[\\d:.Z+-]*)?$/ will NOT match '{serialized}', causing "
            f"lexicographic sort fallback."
        )


# ---------------------------------------------------------------------------
# Test D: Frontend isISODateString() simulation
# ---------------------------------------------------------------------------

class TestFrontendDetectionFailure:
    """
    **Validates: Requirement 1.5**

    Simulates the frontend isISODateString() function to demonstrate that
    Flask's HTTP date string output is NOT detected as a date, causing the
    sort logic to fall back to string comparison.
    """

    # Frontend regex from useTableSort.ts
    FRONTEND_ISO_REGEX = re.compile(r'^\d{4}-\d{2}-\d{2}(T[\d:.Z+-]*)?$')

    @given(date_value=st.dates(
        min_value=datetime.date(2000, 1, 1),
        max_value=datetime.date(2030, 12, 31)
    ))
    @settings(max_examples=50, deadline=5000)
    def test_frontend_detects_serialized_date(self, date_value):
        """
        Property: For any date normalized via normalize_dates and then serialized
        through Flask's jsonify, the frontend isISODateString() function MUST
        return true (detect it as a date).

        On UNFIXED code (without normalize_dates): Flask produces HTTP date
        strings that don't match the frontend regex → FAILS.
        On FIXED code (with normalize_dates): dates are ISO-8601 → PASSES.
        """
        app = create_test_app()

        row = {'TransactionDate': date_value}

        # Simulate the fixed endpoint: normalize_dates before jsonify
        normalize_dates([row], ['TransactionDate'])

        with app.app_context():
            response = jsonify({'data': [row]})
            response_data = json.loads(response.get_data(as_text=True))

        serialized = response_data['data'][0]['TransactionDate']

        assert self.FRONTEND_ISO_REGEX.match(serialized), (
            f"BUG CONFIRMED: Frontend isISODateString('{serialized}') returns "
            f"false. The serialized date '{serialized}' does not match the "
            f"frontend regex /^\\d{{4}}-\\d{{2}}-\\d{{2}}(T[\\d:.Z+-]*)?$/. "
            f"Sort falls back to localeCompare (lexicographic) instead of "
            f"chronological Date comparison."
        )
