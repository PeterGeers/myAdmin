"""
Unit tests for CsvRuleEngine module.

Tests rule matching, CSV aggregation, filename extraction, and error handling.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

import pytest
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from csv_rules import CsvRuleEngine, CsvAggregationRule, CSV_RULES


class TestGetRule:
    """Tests for CsvRuleEngine.get_rule() method."""

    @pytest.fixture
    def engine(self):
        """Create CsvRuleEngine with default rules."""
        return CsvRuleEngine()

    def test_get_rule_matches_airbnb(self, engine):
        """get_rule returns the Airbnb rule for 'airbnb' folder."""
        rule = engine.get_rule("airbnb")
        assert rule is not None
        assert rule.folder_pattern == "airbnb"
        assert rule.amount_column == "Nettobedag"
        assert rule.amount_operation == "sum"
        assert rule.date_column == "Datum van dienst"
        assert rule.date_operation == "max"
        assert rule.description_template == "Hosting Fee; {filename}"
        assert rule.vat_amount == 0.0

    def test_get_rule_matches_case_insensitive_upper(self, engine):
        """get_rule matches 'Airbnb' (mixed case) via lowercase comparison."""
        rule = engine.get_rule("Airbnb")
        assert rule is not None
        assert rule.folder_pattern == "airbnb"

    def test_get_rule_matches_case_insensitive_all_caps(self, engine):
        """get_rule matches 'AIRBNB' (all caps) via lowercase comparison."""
        rule = engine.get_rule("AIRBNB")
        assert rule is not None
        assert rule.folder_pattern == "airbnb"

    def test_get_rule_matches_substring(self, engine):
        """get_rule matches when folder contains 'airbnb' as substring."""
        rule = engine.get_rule("my-airbnb-folder")
        assert rule is not None
        assert rule.folder_pattern == "airbnb"

    def test_get_rule_no_match(self, engine):
        """get_rule returns None for non-matching folder."""
        rule = engine.get_rule("booking")
        assert rule is None

    def test_get_rule_no_match_empty_string(self, engine):
        """get_rule returns None for empty string."""
        rule = engine.get_rule("")
        assert rule is None

    def test_get_rule_custom_rules(self):
        """get_rule works with custom rule list."""
        custom_rule = CsvAggregationRule(
            folder_pattern="booking",
            amount_column="Amount",
            amount_operation="sum",
            date_column="Date",
            date_operation="max",
            description_template="Booking; {filename}",
            vat_amount=21.0,
        )
        engine = CsvRuleEngine(rules=[custom_rule])
        rule = engine.get_rule("booking")
        assert rule is not None
        assert rule.folder_pattern == "booking"


class TestApply:
    """Tests for CsvRuleEngine.apply() method."""

    @pytest.fixture
    def engine(self):
        """Create CsvRuleEngine with default rules."""
        return CsvRuleEngine()

    @pytest.fixture
    def airbnb_rule(self):
        """Get the Airbnb rule."""
        return CSV_RULES[0]

    def test_apply_aggregates_correctly(self, engine, airbnb_rule):
        """apply() correctly sums amounts and finds max date."""
        csv_data = [
            {"Nettobedag": 100.50, "Datum van dienst": "2024-03-01"},
            {"Nettobedag": 200.25, "Datum van dienst": "2024-03-15"},
            {"Nettobedag": 50.00, "Datum van dienst": "2024-03-10"},
        ]
        lines = [
            "[CSV File: march-2024.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(airbnb_rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 350.75
        assert result['date'] == '2024-03-15'
        assert result['vat_amount'] == 0.0
        assert result['description'] == "Hosting Fee; march-2024.csv"
        assert result['vendor'] == "airbnb"
        assert result['parser_used_hint'] == 'csv_rule'

    def test_apply_returns_none_for_malformed_json(self, engine, airbnb_rule):
        """apply() returns None when JSON data is invalid."""
        lines = [
            "[CSV File: test.csv]",
            "[CSV_DATA_START]",
            "not valid json {{{",
        ]

        result = engine.apply(airbnb_rule, lines, "airbnb")
        assert result is None

    def test_apply_returns_none_for_missing_csv_marker(self, engine, airbnb_rule):
        """apply() returns None when [CSV_DATA_START] marker is missing."""
        lines = [
            "[CSV File: test.csv]",
            "some random text",
            json.dumps([{"Nettobedag": 100}]),
        ]

        result = engine.apply(airbnb_rule, lines, "airbnb")
        assert result is None

    def test_apply_handles_missing_amount_column(self, engine, airbnb_rule):
        """apply() handles missing expected amount column gracefully."""
        csv_data = [
            {"WrongColumn": 100.50, "Datum van dienst": "2024-03-01"},
            {"WrongColumn": 200.25, "Datum van dienst": "2024-03-15"},
        ]
        lines = [
            "[CSV File: test.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(airbnb_rule, lines, "airbnb")

        # Should still return a result but with total_amount = 0.0
        assert result is not None
        assert result['total_amount'] == 0.0

    def test_apply_handles_missing_date_column(self, engine, airbnb_rule):
        """apply() handles missing expected date column gracefully."""
        csv_data = [
            {"Nettobedag": 100.50, "WrongDate": "2024-03-01"},
            {"Nettobedag": 200.25, "WrongDate": "2024-03-15"},
        ]
        lines = [
            "[CSV File: test.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(airbnb_rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 300.75
        # Date should fall back to today's date format
        assert len(result['date']) == 10  # YYYY-MM-DD format

    def test_apply_handles_null_values_in_amount(self, engine, airbnb_rule):
        """apply() skips null values when summing amounts."""
        csv_data = [
            {"Nettobedag": 100.0, "Datum van dienst": "2024-03-01"},
            {"Nettobedag": None, "Datum van dienst": "2024-03-15"},
            {"Nettobedag": 50.0, "Datum van dienst": "2024-03-10"},
        ]
        lines = [
            "[CSV File: test.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(airbnb_rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 150.0

    def test_apply_empty_csv_data(self, engine, airbnb_rule):
        """apply() handles empty CSV data array."""
        lines = [
            "[CSV File: empty.csv]",
            "[CSV_DATA_START]",
            json.dumps([]),
        ]

        result = engine.apply(airbnb_rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 0.0


class TestExtractFilename:
    """Tests for CsvRuleEngine._extract_filename() method."""

    @pytest.fixture
    def engine(self):
        """Create CsvRuleEngine with default rules."""
        return CsvRuleEngine()

    def test_extract_filename_standard(self, engine):
        """_extract_filename extracts from [CSV File: name.csv] marker."""
        lines = [
            "[CSV File: march-2024.csv]",
            "[CSV_DATA_START]",
            "[]",
        ]
        assert engine._extract_filename(lines) == "march-2024.csv"

    def test_extract_filename_with_spaces(self, engine):
        """_extract_filename handles filenames with spaces."""
        lines = [
            "[CSV File: my file name.csv]",
            "other content",
        ]
        assert engine._extract_filename(lines) == "my file name.csv"

    def test_extract_filename_missing_marker(self, engine):
        """_extract_filename returns empty string when marker is missing."""
        lines = [
            "no csv file marker here",
            "[CSV_DATA_START]",
            "[]",
        ]
        assert engine._extract_filename(lines) == ""

    def test_extract_filename_empty_lines(self, engine):
        """_extract_filename returns empty string for empty lines."""
        assert engine._extract_filename([]) == ""


class TestExtractCsvData:
    """Tests for CsvRuleEngine._extract_csv_data() method."""

    @pytest.fixture
    def engine(self):
        """Create CsvRuleEngine with default rules."""
        return CsvRuleEngine()

    def test_extract_csv_data_valid_json(self, engine):
        """_extract_csv_data parses JSON array after [CSV_DATA_START] marker."""
        data = [{"col1": "val1", "col2": 42}]
        lines = [
            "[CSV_DATA_START]",
            json.dumps(data),
        ]
        result = engine._extract_csv_data(lines)
        assert result == data

    def test_extract_csv_data_marker_not_first_line(self, engine):
        """_extract_csv_data finds marker anywhere in lines."""
        data = [{"amount": 100}]
        lines = [
            "[CSV File: test.csv]",
            "some other info",
            "[CSV_DATA_START]",
            json.dumps(data),
        ]
        result = engine._extract_csv_data(lines)
        assert result == data

    def test_extract_csv_data_invalid_json(self, engine):
        """_extract_csv_data returns None for invalid JSON."""
        lines = [
            "[CSV_DATA_START]",
            "not valid json",
        ]
        result = engine._extract_csv_data(lines)
        assert result is None

    def test_extract_csv_data_no_marker(self, engine):
        """_extract_csv_data returns None when marker is missing."""
        lines = [
            "just some text",
            json.dumps([{"col": "val"}]),
        ]
        result = engine._extract_csv_data(lines)
        assert result is None

    def test_extract_csv_data_marker_at_end(self, engine):
        """_extract_csv_data returns None when marker is last line (no data after)."""
        lines = [
            "some text",
            "[CSV_DATA_START]",
        ]
        result = engine._extract_csv_data(lines)
        assert result is None

    def test_extract_csv_data_empty_lines(self, engine):
        """_extract_csv_data returns None for empty lines."""
        result = engine._extract_csv_data([])
        assert result is None
