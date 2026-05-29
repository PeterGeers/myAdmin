"""
Property-based tests for CsvRuleEngine module.

Uses Hypothesis to verify correctness properties from the design document.
Feature: vendor-parser-cleanup, Property 5: CSV rule routing
Feature: vendor-parser-cleanup, Property 6: CSV aggregation correctness

Requirements: 6.1, 6.3, 6.4
Reference: .kiro/specs/vendor-parser-cleanup/design.md
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from csv_rules import CsvRuleEngine, CsvAggregationRule, CSV_RULES


# Strategy: generate folder names that contain "airbnb" (case-insensitive variants)
airbnb_case_variants = st.sampled_from(['airbnb', 'Airbnb', 'AIRBNB', 'AirBnB', 'airBNB'])

# Folder names that match: prefix + airbnb variant + suffix
matching_folder_st = st.builds(
    lambda prefix, variant, suffix: f"{prefix}{variant}{suffix}",
    prefix=st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P'), whitelist_characters='-_ '),
        min_size=0,
        max_size=10,
    ),
    variant=airbnb_case_variants,
    suffix=st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P'), whitelist_characters='-_ '),
        min_size=0,
        max_size=10,
    ),
)

# Folder names that do NOT contain "airbnb" (case-insensitive)
non_matching_folder_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=30,
).filter(lambda s: 'airbnb' not in s.lower())


# ---------------------------------------------------------------------------
# Property 5: CSV rule routing
# Feature: vendor-parser-cleanup, Property 5: CSV rule routing
# Validates: Requirements 6.1, 6.4
# ---------------------------------------------------------------------------

class TestCsvRuleRouting:
    """
    Property 5: CSV rule routing

    For any folder name and CSV file content, if the folder name matches a
    configured CSV aggregation rule then the CsvRuleEngine SHALL be applied
    and AIExtractor SHALL NOT be called. If the folder name does NOT match
    any rule, then AIExtractor SHALL be called with the CSV text content.

    **Validates: Requirements 6.1, 6.4**
    """

    @settings(max_examples=100)
    @given(folder_name=matching_folder_st)
    def test_matching_folders_route_to_csv_rule_engine(self, folder_name):
        """
        For any folder name containing 'airbnb' (case-insensitive),
        CsvRuleEngine.get_rule() SHALL return a matching rule,
        indicating the CSV rule engine handles this folder.

        **Validates: Requirements 6.1**
        """
        engine = CsvRuleEngine()
        rule = engine.get_rule(folder_name)

        # A matching folder must return a rule (not None)
        assert rule is not None, (
            f"Expected CsvRuleEngine to match folder '{folder_name}' "
            f"but get_rule() returned None"
        )
        # The matched rule should be for airbnb
        assert rule.folder_pattern == "airbnb", (
            f"Expected matched rule to have folder_pattern='airbnb', "
            f"got '{rule.folder_pattern}'"
        )

    @settings(max_examples=100)
    @given(folder_name=non_matching_folder_st)
    def test_non_matching_folders_fall_through_to_ai(self, folder_name):
        """
        For any folder name NOT containing 'airbnb' (case-insensitive),
        CsvRuleEngine.get_rule() SHALL return None, indicating the folder
        falls through to AI extraction.

        **Validates: Requirements 6.4**
        """
        engine = CsvRuleEngine()
        rule = engine.get_rule(folder_name)

        # A non-matching folder must return None (fall through to AI)
        assert rule is None, (
            f"Expected CsvRuleEngine to NOT match folder '{folder_name}' "
            f"but get_rule() returned a rule with pattern '{rule.folder_pattern}'"
        )


# ---------------------------------------------------------------------------
# Strategy helpers for Property 6
# ---------------------------------------------------------------------------

# Generate valid date strings in YYYY-MM-DD format (constrained to reasonable range)
date_st = st.dates(
    min_value=pd.Timestamp('2020-01-01').date(),
    max_value=pd.Timestamp('2030-12-31').date(),
).map(lambda d: d.strftime('%Y-%m-%d'))

# Generate numeric values for Nettobedag (positive and negative floats)
amount_st = st.floats(
    min_value=-10000.0,
    max_value=10000.0,
    allow_nan=False,
    allow_infinity=False,
)

# Generate a list of CSV row data (at least 1 row)
csv_row_st = st.fixed_dictionaries({
    'Nettobedag': amount_st,
    'Datum van dienst': date_st,
})

csv_data_st = st.lists(csv_row_st, min_size=1, max_size=20)

# Generate filenames for the CSV file marker
filename_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_.'),
    min_size=1,
    max_size=30,
).map(lambda s: f"{s}.csv")


# ---------------------------------------------------------------------------
# Property 6: CSV aggregation correctness
# Feature: vendor-parser-cleanup, Property 6: CSV aggregation correctness
# Validates: Requirements 6.3
# ---------------------------------------------------------------------------

class TestCsvAggregationCorrectness:
    """
    Property 6: CSV aggregation correctness

    For any CSV data containing a Nettobedag column (with numeric values) and
    a Datum van dienst column (with date values), when the Airbnb CSV rule is
    applied, the resulting total_amount SHALL equal the sum of all non-null
    Nettobedag values (rounded to 2 decimals), the date SHALL equal the maximum
    Datum van dienst value formatted as YYYY-MM-DD, vat_amount SHALL be 0.0,
    and description SHALL start with "Hosting Fee".

    **Validates: Requirements 6.3**
    """

    @settings(max_examples=100)
    @given(csv_data=csv_data_st, filename=filename_st)
    def test_total_amount_equals_sum_of_nettobedag(self, csv_data, filename):
        """
        For any CSV data with Nettobedag values, the resulting total_amount
        SHALL equal the sum of all Nettobedag values rounded to 2 decimals.

        **Validates: Requirements 6.3**
        """
        engine = CsvRuleEngine()
        rule = engine.get_rule("airbnb")
        assert rule is not None

        # Build lines in the format expected by CsvRuleEngine
        lines = [
            f"[CSV File: {filename}]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")
        assert result is not None, "CsvRuleEngine.apply() returned None for valid data"

        # Reference calculation using pandas
        df = pd.DataFrame(csv_data)
        expected_sum = round(float(df['Nettobedag'].dropna().sum()), 2)

        assert result['total_amount'] == expected_sum, (
            f"Expected total_amount={expected_sum}, got {result['total_amount']}. "
            f"Nettobedag values: {[row['Nettobedag'] for row in csv_data]}"
        )

    @settings(max_examples=100)
    @given(csv_data=csv_data_st, filename=filename_st)
    def test_date_equals_max_datum_van_dienst(self, csv_data, filename):
        """
        For any CSV data with Datum van dienst values, the resulting date
        SHALL equal the maximum date formatted as YYYY-MM-DD.

        **Validates: Requirements 6.3**
        """
        engine = CsvRuleEngine()
        rule = engine.get_rule("airbnb")
        assert rule is not None

        lines = [
            f"[CSV File: {filename}]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")
        assert result is not None, "CsvRuleEngine.apply() returned None for valid data"

        # Reference calculation using pandas
        df = pd.DataFrame(csv_data)
        expected_max_date = pd.to_datetime(df['Datum van dienst']).max().strftime('%Y-%m-%d')

        assert result['date'] == expected_max_date, (
            f"Expected date='{expected_max_date}', got '{result['date']}'. "
            f"Datum van dienst values: {[row['Datum van dienst'] for row in csv_data]}"
        )

    @settings(max_examples=100)
    @given(csv_data=csv_data_st, filename=filename_st)
    def test_vat_amount_is_zero(self, csv_data, filename):
        """
        For any CSV data processed by the Airbnb rule, vat_amount SHALL be 0.0.

        **Validates: Requirements 6.3**
        """
        engine = CsvRuleEngine()
        rule = engine.get_rule("airbnb")
        assert rule is not None

        lines = [
            f"[CSV File: {filename}]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")
        assert result is not None, "CsvRuleEngine.apply() returned None for valid data"

        assert result['vat_amount'] == 0.0, (
            f"Expected vat_amount=0.0, got {result['vat_amount']}"
        )

    @settings(max_examples=100)
    @given(csv_data=csv_data_st, filename=filename_st)
    def test_description_starts_with_hosting_fee(self, csv_data, filename):
        """
        For any CSV data processed by the Airbnb rule, description SHALL
        start with "Hosting Fee".

        **Validates: Requirements 6.3**
        """
        engine = CsvRuleEngine()
        rule = engine.get_rule("airbnb")
        assert rule is not None

        lines = [
            f"[CSV File: {filename}]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")
        assert result is not None, "CsvRuleEngine.apply() returned None for valid data"

        assert result['description'].startswith("Hosting Fee"), (
            f"Expected description to start with 'Hosting Fee', "
            f"got '{result['description']}'"
        )
        # Also verify the filename is included in the description
        assert filename in result['description'], (
            f"Expected filename '{filename}' in description, "
            f"got '{result['description']}'"
        )
