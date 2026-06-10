"""
Unit tests for csv_rules module — CSV rule matching logic.

Tests the CSV aggregation rule matching: how rules are matched to folders
and applied to CSV data, including multi-rule scenarios, edge cases in
data handling, and the full get_rule -> apply flow.
"""

import pytest
import json
from datetime import datetime
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from csv_rules import CsvRuleEngine, CsvAggregationRule, CSV_RULES


@pytest.mark.unit
class TestCsvRulesRegistry:
    """Tests for the CSV_RULES registry configuration."""

    def test_csv_rules_is_non_empty_list(self):
        """CSV_RULES registry contains at least one rule."""
        assert isinstance(CSV_RULES, list)
        assert len(CSV_RULES) >= 1

    def test_all_rules_are_csv_aggregation_rule_instances(self):
        """Every entry in CSV_RULES is a CsvAggregationRule dataclass."""
        for rule in CSV_RULES:
            assert isinstance(rule, CsvAggregationRule)

    def test_airbnb_rule_exists(self):
        """The Airbnb rule is present in the registry."""
        patterns = [r.folder_pattern for r in CSV_RULES]
        assert "airbnb" in patterns

    def test_rules_have_lowercase_folder_patterns(self):
        """All folder_pattern values are lowercase for consistent matching."""
        for rule in CSV_RULES:
            assert rule.folder_pattern == rule.folder_pattern.lower(), (
                f"Rule folder_pattern '{rule.folder_pattern}' should be lowercase"
            )

    def test_rules_have_valid_operations(self):
        """All rules use recognized amount_operation and date_operation values."""
        valid_amount_ops = {"sum"}
        valid_date_ops = {"max"}
        for rule in CSV_RULES:
            assert rule.amount_operation in valid_amount_ops, (
                f"Unsupported amount_operation: {rule.amount_operation}"
            )
            assert rule.date_operation in valid_date_ops, (
                f"Unsupported date_operation: {rule.date_operation}"
            )

    def test_rules_have_non_empty_columns(self):
        """All rules specify non-empty column names."""
        for rule in CSV_RULES:
            assert rule.amount_column, "amount_column must not be empty"
            assert rule.date_column, "date_column must not be empty"

    def test_rules_have_description_with_filename_placeholder(self):
        """All rules include {filename} in description_template."""
        for rule in CSV_RULES:
            assert "{filename}" in rule.description_template, (
                f"description_template '{rule.description_template}' missing {{filename}}"
            )


@pytest.mark.unit
class TestMultiRuleMatching:
    """Tests for rule matching with multiple rules configured."""

    @pytest.fixture
    def multi_rule_engine(self):
        """Engine with multiple rules to test priority/matching."""
        rules = [
            CsvAggregationRule(
                folder_pattern="airbnb",
                amount_column="Nettobedag",
                amount_operation="sum",
                date_column="Datum van dienst",
                date_operation="max",
                description_template="Hosting Fee; {filename}",
                vat_amount=0.0,
            ),
            CsvAggregationRule(
                folder_pattern="booking",
                amount_column="Amount",
                amount_operation="sum",
                date_column="CheckOut",
                date_operation="max",
                description_template="Booking.com; {filename}",
                vat_amount=21.0,
            ),
            CsvAggregationRule(
                folder_pattern="vrbo",
                amount_column="Payout",
                amount_operation="sum",
                date_column="PayoutDate",
                date_operation="max",
                description_template="VRBO Payout; {filename}",
                vat_amount=0.0,
            ),
        ]
        return CsvRuleEngine(rules=rules)

    def test_first_matching_rule_wins(self, multi_rule_engine):
        """When multiple rules could match, the first match is returned."""
        rule = multi_rule_engine.get_rule("airbnb-exports")
        assert rule is not None
        assert rule.folder_pattern == "airbnb"

    def test_each_rule_matches_its_own_pattern(self, multi_rule_engine):
        """Each rule matches only folders containing its pattern."""
        assert multi_rule_engine.get_rule("booking-data").folder_pattern == "booking"
        assert multi_rule_engine.get_rule("vrbo-revenue").folder_pattern == "vrbo"
        assert multi_rule_engine.get_rule("airbnb-q4").folder_pattern == "airbnb"

    def test_no_match_returns_none(self, multi_rule_engine):
        """Folder not matching any rule returns None."""
        assert multi_rule_engine.get_rule("expedia-reports") is None

    def test_overlapping_patterns_first_wins(self):
        """If folder matches multiple rules, first in list wins."""
        rules = [
            CsvAggregationRule(
                folder_pattern="air",
                amount_column="Col1",
                amount_operation="sum",
                date_column="Date1",
                date_operation="max",
                description_template="Generic Air; {filename}",
                vat_amount=0.0,
            ),
            CsvAggregationRule(
                folder_pattern="airbnb",
                amount_column="Col2",
                amount_operation="sum",
                date_column="Date2",
                date_operation="max",
                description_template="Airbnb Specific; {filename}",
                vat_amount=0.0,
            ),
        ]
        engine = CsvRuleEngine(rules=rules)
        # "airbnb" contains "air", so the first rule matches
        rule = engine.get_rule("airbnb-folder")
        assert rule.folder_pattern == "air"

    def test_empty_rules_list_never_matches(self):
        """Engine with no rules returns None for any folder."""
        engine = CsvRuleEngine(rules=[])
        assert engine.get_rule("airbnb") is None
        assert engine.get_rule("anything") is None
        assert engine.get_rule("") is None


@pytest.mark.unit
class TestRuleMatchingEdgeCases:
    """Edge cases in folder name matching."""

    @pytest.fixture
    def engine(self):
        """Default engine with standard rules."""
        return CsvRuleEngine()

    def test_folder_with_path_separators(self, engine):
        """Folder path containing the pattern still matches."""
        rule = engine.get_rule("uploads/airbnb/2024")
        assert rule is not None
        assert rule.folder_pattern == "airbnb"

    def test_folder_with_special_characters(self, engine):
        """Folder name with special chars around the pattern matches."""
        rule = engine.get_rule("[airbnb]-exports")
        assert rule is not None

    def test_folder_unicode_no_match(self, engine):
        """Unicode folder name that doesn't contain pattern returns None."""
        rule = engine.get_rule("données-hébergement")
        assert rule is None

    def test_folder_with_whitespace(self, engine):
        """Folder with whitespace containing pattern still matches."""
        rule = engine.get_rule("  airbnb  ")
        assert rule is not None

    def test_partial_pattern_no_match(self, engine):
        """Partial pattern does not match (e.g., 'airbn' alone)."""
        rule = engine.get_rule("airbn")
        assert rule is None

    def test_folder_name_exactly_equals_pattern(self, engine):
        """Folder name that is exactly the pattern matches."""
        rule = engine.get_rule("airbnb")
        assert rule is not None


@pytest.mark.unit
class TestApplyFullFlow:
    """End-to-end tests: get_rule + apply together."""

    @pytest.fixture
    def engine(self):
        """Default engine."""
        return CsvRuleEngine()

    def test_full_flow_airbnb_csv(self, engine):
        """Complete flow: match folder, apply rule, get result."""
        rule = engine.get_rule("airbnb-march")
        assert rule is not None

        csv_data = [
            {"Nettobedag": 75.50, "Datum van dienst": "2024-03-05"},
            {"Nettobedag": 120.00, "Datum van dienst": "2024-03-20"},
        ]
        lines = [
            "[CSV File: airbnb-maart-2024.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb-march")

        assert result is not None
        assert result['total_amount'] == 195.50
        assert result['date'] == '2024-03-20'
        assert result['vat_amount'] == 0.0
        assert result['description'] == "Hosting Fee; airbnb-maart-2024.csv"
        assert result['vendor'] == "airbnb-march"
        assert result['parser_used_hint'] == 'csv_rule'

    def test_full_flow_no_matching_rule(self, engine):
        """Non-matching folder returns None from get_rule, no apply needed."""
        rule = engine.get_rule("random-vendor")
        assert rule is None

    def test_apply_with_negative_amounts(self, engine):
        """Negative amounts (refunds) are correctly summed."""
        rule = engine.get_rule("airbnb")
        csv_data = [
            {"Nettobedag": 200.00, "Datum van dienst": "2024-01-10"},
            {"Nettobedag": -50.00, "Datum van dienst": "2024-01-15"},
            {"Nettobedag": 100.00, "Datum van dienst": "2024-01-20"},
        ]
        lines = [
            "[CSV File: jan-2024.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 250.00

    def test_apply_with_single_row(self, engine):
        """Single-row CSV data works correctly."""
        rule = engine.get_rule("airbnb")
        csv_data = [
            {"Nettobedag": 99.99, "Datum van dienst": "2024-06-15"},
        ]
        lines = [
            "[CSV File: single.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 99.99
        assert result['date'] == '2024-06-15'

    def test_apply_with_large_amounts(self, engine):
        """Large monetary values are handled without overflow."""
        rule = engine.get_rule("airbnb")
        csv_data = [
            {"Nettobedag": 99999.99, "Datum van dienst": "2024-12-01"},
            {"Nettobedag": 88888.88, "Datum van dienst": "2024-12-31"},
        ]
        lines = [
            "[CSV File: big.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 188888.87

    def test_apply_rounding_precision(self, engine):
        """Result is rounded to 2 decimal places."""
        rule = engine.get_rule("airbnb")
        csv_data = [
            {"Nettobedag": 1.111, "Datum van dienst": "2024-01-01"},
            {"Nettobedag": 2.222, "Datum van dienst": "2024-01-02"},
            {"Nettobedag": 3.333, "Datum van dienst": "2024-01-03"},
        ]
        lines = [
            "[CSV File: rounding.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        # 1.111 + 2.222 + 3.333 = 6.666 -> rounded to 6.67
        assert result['total_amount'] == 6.67


@pytest.mark.unit
class TestApplyErrorHandling:
    """Error handling and edge cases in apply method."""

    @pytest.fixture
    def engine(self):
        """Default engine."""
        return CsvRuleEngine()

    @pytest.fixture
    def rule(self):
        """Airbnb rule."""
        return CSV_RULES[0]

    def test_apply_empty_lines_list(self, engine, rule):
        """Empty lines list returns None."""
        result = engine.apply(rule, [], "airbnb")
        assert result is None

    def test_apply_csv_data_start_without_data_line(self, engine, rule):
        """[CSV_DATA_START] as last line with no data returns None."""
        lines = [
            "[CSV File: test.csv]",
            "[CSV_DATA_START]",
        ]
        result = engine.apply(rule, lines, "airbnb")
        assert result is None

    def test_apply_with_extra_columns_in_data(self, engine, rule):
        """Extra columns in CSV data are ignored."""
        csv_data = [
            {
                "Nettobedag": 100.0,
                "Datum van dienst": "2024-05-01",
                "ExtraCol": "ignored",
                "AnotherCol": 42,
            },
        ]
        lines = [
            "[CSV File: extra-cols.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 100.0

    def test_apply_with_all_null_amounts(self, engine, rule):
        """All null amounts results in total_amount of 0.0."""
        csv_data = [
            {"Nettobedag": None, "Datum van dienst": "2024-01-01"},
            {"Nettobedag": None, "Datum van dienst": "2024-01-02"},
        ]
        lines = [
            "[CSV File: nulls.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert result['total_amount'] == 0.0

    def test_apply_with_mixed_date_formats(self, engine, rule):
        """Dates in different formats are handled by pandas parsing."""
        csv_data = [
            {"Nettobedag": 50.0, "Datum van dienst": "2024-01-15"},
            {"Nettobedag": 75.0, "Datum van dienst": "2024-02-28"},
        ]
        lines = [
            "[CSV File: dates.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert result['date'] == '2024-02-28'

    def test_apply_description_includes_filename(self, engine, rule):
        """Description template correctly interpolates filename."""
        csv_data = [
            {"Nettobedag": 10.0, "Datum van dienst": "2024-07-01"},
        ]
        lines = [
            "[CSV File: my-special-file.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert "my-special-file.csv" in result['description']
        assert result['description'] == "Hosting Fee; my-special-file.csv"

    def test_apply_no_filename_marker_uses_empty_string(self, engine, rule):
        """Missing [CSV File:] marker results in empty filename in description."""
        csv_data = [
            {"Nettobedag": 10.0, "Datum van dienst": "2024-07-01"},
        ]
        lines = [
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        result = engine.apply(rule, lines, "airbnb")

        assert result is not None
        assert result['description'] == "Hosting Fee; "


@pytest.mark.unit
class TestCustomRuleApply:
    """Tests for applying custom rules with different configurations."""

    def test_custom_rule_different_columns(self):
        """Custom rule with different column names works correctly."""
        custom_rule = CsvAggregationRule(
            folder_pattern="booking",
            amount_column="TotalPayout",
            amount_operation="sum",
            date_column="CheckoutDate",
            date_operation="max",
            description_template="Booking.com Revenue; {filename}",
            vat_amount=21.0,
        )
        engine = CsvRuleEngine(rules=[custom_rule])

        csv_data = [
            {"TotalPayout": 500.0, "CheckoutDate": "2024-04-10"},
            {"TotalPayout": 300.0, "CheckoutDate": "2024-04-20"},
        ]
        lines = [
            "[CSV File: booking-april.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        rule = engine.get_rule("booking-exports")
        result = engine.apply(rule, lines, "booking-exports")

        assert result is not None
        assert result['total_amount'] == 800.0
        assert result['date'] == '2024-04-20'
        assert result['vat_amount'] == 21.0
        assert result['description'] == "Booking.com Revenue; booking-april.csv"
        assert result['vendor'] == "booking-exports"
        assert result['parser_used_hint'] == 'csv_rule'

    def test_custom_rule_with_nonzero_vat(self):
        """Rule with non-zero vat_amount passes it through correctly."""
        rule = CsvAggregationRule(
            folder_pattern="vendor",
            amount_column="Net",
            amount_operation="sum",
            date_column="Date",
            date_operation="max",
            description_template="Invoice; {filename}",
            vat_amount=9.50,
        )
        engine = CsvRuleEngine(rules=[rule])

        csv_data = [{"Net": 100.0, "Date": "2024-01-01"}]
        lines = [
            "[CSV File: invoice.csv]",
            "[CSV_DATA_START]",
            json.dumps(csv_data),
        ]

        matched = engine.get_rule("vendor-data")
        result = engine.apply(matched, lines, "vendor-data")

        assert result is not None
        assert result['vat_amount'] == 9.50
