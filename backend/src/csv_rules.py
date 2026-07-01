"""Declarative CSV aggregation rules engine.

Handles CSV files with known column layouts using business rules
instead of AI extraction, ensuring deterministic and cost-free processing.
"""

from dataclasses import dataclass
from typing import Optional
import json
import re
from datetime import datetime

import pandas as pd


@dataclass
class CsvAggregationRule:
    """Declarative CSV aggregation rule."""

    folder_pattern: str  # substring match on folder_name
    amount_column: str  # column to aggregate
    amount_operation: str  # "sum"
    date_column: str  # column for date extraction
    date_operation: str  # "max"
    description_template: str  # e.g. "Hosting Fee; {filename}"
    vat_amount: float  # fixed VAT amount


# Rule registry — add new rules here without modifying extraction logic
CSV_RULES: list[CsvAggregationRule] = [
    CsvAggregationRule(
        folder_pattern="airbnb",
        amount_column="Nettobedag",
        amount_operation="sum",
        date_column="Datum van dienst",
        date_operation="max",
        description_template="Hosting Fee; {filename}",
        vat_amount=0.0,
    ),
]


class CsvRuleEngine:
    """Applies declarative CSV aggregation rules."""

    def __init__(self, rules: Optional[list[CsvAggregationRule]] = None):
        self.rules = rules if rules is not None else CSV_RULES

    def get_rule(self, folder_name: str) -> Optional[CsvAggregationRule]:
        """Find matching rule for folder name (substring match)."""
        folder_lower = folder_name.lower()
        for rule in self.rules:
            if rule.folder_pattern in folder_lower:
                return rule
        return None

    def apply(
        self, rule: CsvAggregationRule, lines: list[str], folder_name: str
    ) -> Optional[dict]:
        """Apply a CSV aggregation rule to extracted lines."""
        csv_data = self._extract_csv_data(lines)
        if csv_data is None:
            return None

        df = pd.DataFrame(csv_data)
        filename = self._extract_filename(lines)

        try:
            # Aggregate amount
            total_amount = 0.0
            if rule.amount_column in df.columns:
                if rule.amount_operation == "sum":
                    total_amount = float(df[rule.amount_column].dropna().sum())

            # Extract date
            date = datetime.now().strftime("%Y-%m-%d")
            if rule.date_column in df.columns:
                if rule.date_operation == "max":
                    max_date = df[rule.date_column].max()
                    if pd.notna(max_date):
                        parsed = pd.to_datetime(max_date)
                        date = parsed.strftime("%Y-%m-%d")

            # Build description
            description = rule.description_template.format(filename=filename)

            return {
                "date": date,
                "total_amount": round(total_amount, 2),
                "vat_amount": rule.vat_amount,
                "description": description,
                "vendor": folder_name,
                "parser_used_hint": "csv_rule",
            }

        except Exception as e:
            print(f"Error applying CSV rule for {folder_name}: {e}")
            return None

    def _extract_csv_data(self, lines: list[str]) -> Optional[list[dict]]:
        """Extract JSON CSV data from processed lines."""
        for i, line in enumerate(lines):
            if line == "[CSV_DATA_START]" and i + 1 < len(lines):
                try:
                    return json.loads(lines[i + 1])
                except (json.JSONDecodeError, IndexError):
                    pass
        return None

    def _extract_filename(self, lines: list[str]) -> str:
        """Extract filename from CSV info lines."""
        for line in lines:
            if line.startswith("[CSV File:"):
                match = re.search(r"\[CSV File: (.+)\]", line)
                if match:
                    return match.group(1)
        return ""
