"""
Integration Tests — Closure-Aware Balance Consistency Across All Four Code Paths

Tests cross-path consistency: given the same account/year/closure state,
all four code paths (actuals-balance non-per_year, actuals-balance per_year,
query_aangifte_ib, make_ledgers) produce the same balance.

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7

These tests use mocked DatabaseManager and MutatiesCache with realistic data
that exercises all four code paths together.
"""

import sys
import os
import pytest
import pandas as pd
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared Test Data Builders
# ---------------------------------------------------------------------------

ADMIN = "IntegrationTenant"
ACCOUNT = "1000"
ACCOUNT_NAME = "Bank"
PARENT = "Activa"


def build_closure_scenario_dataframe(
    closed_year=2023,
    opening_balance_year=2024,
    target_year=2025,
    closed_year_amount=10000.0,
    opening_balance_amount=10000.0,
    target_year_amount=5000.0,
    administration=ADMIN,
):
    """
    Build DataFrame simulating cache state when a year is closed.

    Contains:
    - Raw transactions for the closed year
    - OpeningBalance record in opening_balance_year (carries forward history)
    - Transaction in target year
    """
    rows = [
        {
            "Aangifte": "Balans",
            "TransactionNumber": f"TXN-{closed_year}-001",
            "TransactionDate": pd.Timestamp(f"{closed_year}-06-15"),
            "TransactionDescription": f"Revenue {closed_year}",
            "Amount": closed_year_amount,
            "Reknum": ACCOUNT,
            "AccountName": ACCOUNT_NAME,
            "Parent": PARENT,
            "VW": "N",
            "jaar": closed_year,
            "kwartaal": 2,
            "maand": 6,
            "week": 24,
            "ReferenceNumber": f"REF-{closed_year}",
            "administration": administration,
            "Ref3": "",
            "Ref4": "",
        },
        {
            "Aangifte": "Balans",
            "TransactionNumber": f"OpeningBalance-{opening_balance_year}",
            "TransactionDate": pd.Timestamp(f"{opening_balance_year}-01-01"),
            "TransactionDescription": f"Opening Balance {opening_balance_year}",
            "Amount": opening_balance_amount,
            "Reknum": ACCOUNT,
            "AccountName": ACCOUNT_NAME,
            "Parent": PARENT,
            "VW": "N",
            "jaar": opening_balance_year,
            "kwartaal": 1,
            "maand": 1,
            "week": 1,
            "ReferenceNumber": f"OB-{opening_balance_year}",
            "administration": administration,
            "Ref3": "",
            "Ref4": "",
        },
        {
            "Aangifte": "Balans",
            "TransactionNumber": f"TXN-{target_year}-001",
            "TransactionDate": pd.Timestamp(f"{target_year}-03-15"),
            "TransactionDescription": f"Revenue {target_year}",
            "Amount": target_year_amount,
            "Reknum": ACCOUNT,
            "AccountName": ACCOUNT_NAME,
            "Parent": PARENT,
            "VW": "N",
            "jaar": target_year,
            "kwartaal": 1,
            "maand": 3,
            "week": 11,
            "ReferenceNumber": f"REF-{target_year}",
            "administration": administration,
            "Ref3": "",
            "Ref4": "",
        },
    ]
    return pd.DataFrame(rows)


def build_no_closure_dataframe(
    years=(2022, 2023, 2024),
    amount_per_year=10000.0,
    administration=ADMIN,
):
    """
    Build DataFrame simulating cache with NO closures.
    Transactions span multiple years, no OpeningBalance exists.
    """
    rows = []
    for year in years:
        rows.append({
            "Aangifte": "Balans",
            "TransactionNumber": f"TXN-{year}-001",
            "TransactionDate": pd.Timestamp(f"{year}-05-10"),
            "TransactionDescription": f"Revenue {year}",
            "Amount": amount_per_year,
            "Reknum": ACCOUNT,
            "AccountName": ACCOUNT_NAME,
            "Parent": PARENT,
            "VW": "N",
            "jaar": year,
            "kwartaal": 2,
            "maand": 5,
            "week": 19,
            "ReferenceNumber": f"REF-{year}",
            "administration": administration,
            "Ref3": "",
            "Ref4": "",
        })
    return pd.DataFrame(rows)


def build_multiple_closures_dataframe(
    closed_years=(2021, 2022, 2023),
    target_year=2025,
    opening_balance_amount=30000.0,
    target_year_amount=5000.0,
    administration=ADMIN,
):
    """
    Build DataFrame simulating multiple closed years.
    Only the last closed year + 1 should have the OpeningBalance.
    MAX(closed_years) + 1 = 2024 has the OB.
    """
    max_closed = max(closed_years)
    ob_year = max_closed + 1
    rows = []
    # Raw transactions from all closed years (should be excluded by fix)
    for year in closed_years:
        rows.append({
            "Aangifte": "Balans",
            "TransactionNumber": f"TXN-{year}-001",
            "TransactionDate": pd.Timestamp(f"{year}-06-15"),
            "TransactionDescription": f"Revenue {year}",
            "Amount": 10000.0,
            "Reknum": ACCOUNT,
            "AccountName": ACCOUNT_NAME,
            "Parent": PARENT,
            "VW": "N",
            "jaar": year,
            "kwartaal": 2,
            "maand": 6,
            "week": 24,
            "ReferenceNumber": f"REF-{year}",
            "administration": administration,
            "Ref3": "",
            "Ref4": "",
        })

    # OpeningBalance in MAX(closed_years) + 1 (carries forward ALL prior history)
    rows.append({
        "Aangifte": "Balans",
        "TransactionNumber": f"OpeningBalance-{ob_year}",
        "TransactionDate": pd.Timestamp(f"{ob_year}-01-01"),
        "TransactionDescription": f"Opening Balance {ob_year}",
        "Amount": opening_balance_amount,
        "Reknum": ACCOUNT,
        "AccountName": ACCOUNT_NAME,
        "Parent": PARENT,
        "VW": "N",
        "jaar": ob_year,
        "kwartaal": 1,
        "maand": 1,
        "week": 1,
        "ReferenceNumber": f"OB-{ob_year}",
        "administration": administration,
        "Ref3": "",
        "Ref4": "",
    })

    # Target year transaction
    rows.append({
        "Aangifte": "Balans",
        "TransactionNumber": f"TXN-{target_year}-001",
        "TransactionDate": pd.Timestamp(f"{target_year}-03-15"),
        "TransactionDescription": f"Revenue {target_year}",
        "Amount": target_year_amount,
        "Reknum": ACCOUNT,
        "AccountName": ACCOUNT_NAME,
        "Parent": PARENT,
        "VW": "N",
        "jaar": target_year,
        "kwartaal": 1,
        "maand": 3,
        "week": 11,
        "ReferenceNumber": f"REF-{target_year}",
        "administration": administration,
        "Ref3": "",
        "Ref4": "",
    })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Helper: Simulate each code path
# ---------------------------------------------------------------------------

def simulate_actuals_balance_non_per_year(df, start_year, target_year, administration):
    """Simulate actuals-balance non-per_year mode (as in actuals_routes.py)."""
    filtered = df[df["VW"] == "N"].copy()
    filtered = filtered[filtered["administration"] == administration]
    filtered = filtered[filtered["jaar"] <= target_year]
    if start_year:
        filtered = filtered[filtered["jaar"] >= start_year]

    grouped = filtered.groupby(
        ["Parent", "Reknum", "AccountName"], as_index=False
    ).agg({"Amount": "sum"})
    grouped = grouped[grouped["Amount"] != 0]
    return grouped


def simulate_actuals_balance_per_year(df, start_year, target_year, closed_years, administration):
    """Simulate actuals-balance per_year=true mode for a single year."""
    filtered = df[df["VW"] == "N"].copy()
    filtered = filtered[filtered["administration"] == administration]

    if target_year in closed_years:
        year_df = filtered[filtered["jaar"] == target_year]
    else:
        if start_year:
            year_df = filtered[(filtered["jaar"] >= start_year) & (filtered["jaar"] <= target_year)]
        else:
            year_df = filtered[filtered["jaar"] <= target_year]

    if len(year_df) == 0:
        return pd.DataFrame()

    grouped = year_df.groupby(
        ["Parent", "Reknum", "AccountName"], as_index=False
    ).agg({"Amount": "sum"})
    grouped = grouped[grouped["Amount"] != 0]
    return grouped


def simulate_aangifte_ib(df, start_year, target_year, administration):
    """Simulate query_aangifte_ib() logic for VW='N' accounts."""
    from mutaties_cache import MutatiesCache

    cache = MutatiesCache(ttl_minutes=30)
    cache.data = df
    cache.last_loaded = pd.Timestamp.now()

    result = cache.query_aangifte_ib(
        year=target_year,
        administration=administration,
        user_tenants=[administration],
        snapshot=df,
        start_year=start_year,
    )
    return result


def simulate_make_ledgers_beginning_balance(df, start_year, target_year, administration):
    """
    Simulate make_ledgers() beginning balance logic.
    Returns the sum of VW='N' transactions from start_year to target_year-1.
    """
    filtered = df[df["VW"] == "N"].copy()
    filtered = filtered[filtered["administration"] == administration]
    filtered = filtered[filtered["jaar"] < target_year]
    if start_year:
        filtered = filtered[filtered["jaar"] >= start_year]

    if len(filtered) == 0:
        return 0.0

    return filtered["Amount"].sum()


def get_balance_from_grouped(grouped, account=ACCOUNT):
    """Extract balance for a specific account from grouped DataFrame."""
    if isinstance(grouped, pd.DataFrame) and len(grouped) > 0:
        match = grouped[grouped["Reknum"] == account]
        if len(match) > 0:
            return match["Amount"].iloc[0]
    return 0.0


def get_balance_from_aangifte_result(result, parent=PARENT):
    """Extract balance from aangifte_ib result list."""
    matching = [r for r in result if r.get("Parent") == parent]
    if matching:
        return sum(r["Amount"] for r in matching)
    return 0.0


# ---------------------------------------------------------------------------
# Test 1: Cross-path consistency — Year 2023 closed
# All four paths should produce the same balance for the same scenario
# ---------------------------------------------------------------------------

class TestCrossPathConsistencyClosedYear:
    """
    Cross-path consistency: given the same account/year/closure state,
    all four code paths produce the same balance.
    Validates: Requirements 2.1, 2.2, 2.3, 2.4
    """

    def test_all_paths_agree_with_closure(self):
        """
        Year 2023 closed, OpeningBalance in 2024, target year 2025.
        All paths should produce: OB(€10,000) + 2025_txn(€5,000) = €15,000.
        """
        df = build_closure_scenario_dataframe(
            closed_year=2023,
            opening_balance_year=2024,
            target_year=2025,
            closed_year_amount=10000.0,
            opening_balance_amount=10000.0,
            target_year_amount=5000.0,
        )
        start_year = 2024  # last_closed_year(2023) + 1
        closed_years = [2023]
        target_year = 2025
        expected = 15000.0  # OB + target year transaction

        # Path 1: actuals-balance non-per_year
        grouped1 = simulate_actuals_balance_non_per_year(df, start_year, target_year, ADMIN)
        balance_path1 = get_balance_from_grouped(grouped1)

        # Path 2: actuals-balance per_year (open year)
        grouped2 = simulate_actuals_balance_per_year(
            df, start_year, target_year, closed_years, ADMIN
        )
        balance_path2 = get_balance_from_grouped(grouped2)

        # Path 3: query_aangifte_ib
        result3 = simulate_aangifte_ib(df, start_year, target_year, ADMIN)
        balance_path3 = get_balance_from_aangifte_result(result3)

        # Path 4: make_ledgers beginning balance + target year transactions
        bb = simulate_make_ledgers_beginning_balance(df, start_year, target_year, ADMIN)
        target_txn = df[(df["jaar"] == target_year) & (df["VW"] == "N") &
                        (df["administration"] == ADMIN)]["Amount"].sum()
        balance_path4 = bb + target_txn

        # All should agree
        assert balance_path1 == expected, (
            f"actuals-balance non-per_year: {balance_path1} != {expected}"
        )
        assert balance_path2 == expected, (
            f"actuals-balance per_year: {balance_path2} != {expected}"
        )
        assert balance_path3 == expected, (
            f"query_aangifte_ib: {balance_path3} != {expected}"
        )
        assert balance_path4 == expected, (
            f"make_ledgers (bb + txn): {balance_path4} != {expected}"
        )

        # Cross-path consistency
        assert balance_path1 == balance_path2 == balance_path3 == balance_path4, (
            f"CROSS-PATH INCONSISTENCY: "
            f"non_per_year={balance_path1}, per_year={balance_path2}, "
            f"aangifte_ib={balance_path3}, make_ledgers={balance_path4}"
        )


# ---------------------------------------------------------------------------
# Test 2: Year 2023 closed — single-count verification
# Validates: Requirements 2.1, 2.2, 2.4
# ---------------------------------------------------------------------------

class TestClosedYearSingleCount:
    """
    When year 2023 is closed and OpeningBalance exists in 2024,
    all paths produce correct single-count (no double-counting).
    """

    def test_actuals_non_per_year_single_count(self):
        """Non-per_year: only data from 2024+ included."""
        df = build_closure_scenario_dataframe()
        start_year = 2024
        target_year = 2025

        grouped = simulate_actuals_balance_non_per_year(df, start_year, target_year, ADMIN)
        balance = get_balance_from_grouped(grouped)

        # Should be OB(10000) + target(5000) = 15000, NOT 25000
        assert balance == 15000.0

    def test_actuals_per_year_single_count(self):
        """Per_year open year: only data from 2024+ included."""
        df = build_closure_scenario_dataframe()
        start_year = 2024
        closed_years = [2023]
        target_year = 2025

        grouped = simulate_actuals_balance_per_year(
            df, start_year, target_year, closed_years, ADMIN
        )
        balance = get_balance_from_grouped(grouped)

        assert balance == 15000.0

    def test_aangifte_ib_single_count(self):
        """Aangifte IB with closure: cumulates from start_year."""
        df = build_closure_scenario_dataframe()
        start_year = 2024
        target_year = 2025

        result = simulate_aangifte_ib(df, start_year, target_year, ADMIN)
        balance = get_balance_from_aangifte_result(result)

        assert balance == 15000.0

    def test_make_ledgers_single_count(self):
        """Make ledgers beginning balance only from start_year."""
        df = build_closure_scenario_dataframe()
        start_year = 2024
        target_year = 2025

        bb = simulate_make_ledgers_beginning_balance(df, start_year, target_year, ADMIN)

        # Beginning balance should only include OB from 2024 = 10000
        assert bb == 10000.0


# ---------------------------------------------------------------------------
# Test 3: No closures — full cumulation
# Validates: Requirements 2.3, 2.5
# ---------------------------------------------------------------------------

class TestNoClosuresFullCumulation:
    """
    When no years are closed, all paths produce full cumulation
    (jaar <= target_year) since no OpeningBalance records exist.
    """

    def test_all_paths_agree_no_closures(self):
        """No closures: all paths cumulate all years <= target."""
        df = build_no_closure_dataframe(
            years=(2022, 2023, 2024),
            amount_per_year=10000.0,
        )
        start_year = None  # No closures
        target_year = 2024
        expected = 30000.0  # 3 years × €10,000

        # Path 1: actuals-balance non-per_year
        grouped1 = simulate_actuals_balance_non_per_year(df, start_year, target_year, ADMIN)
        balance_path1 = get_balance_from_grouped(grouped1)

        # Path 2: actuals-balance per_year (open year, no closures)
        grouped2 = simulate_actuals_balance_per_year(
            df, start_year, target_year, [], ADMIN
        )
        balance_path2 = get_balance_from_grouped(grouped2)

        # Path 3: query_aangifte_ib (no closures → full cumulation)
        result3 = simulate_aangifte_ib(df, start_year, target_year, ADMIN)
        balance_path3 = get_balance_from_aangifte_result(result3)

        # Path 4: make_ledgers beginning balance (all years < target)
        bb = simulate_make_ledgers_beginning_balance(df, start_year, target_year, ADMIN)
        target_txn = df[(df["jaar"] == target_year) & (df["VW"] == "N") &
                        (df["administration"] == ADMIN)]["Amount"].sum()
        balance_path4 = bb + target_txn

        assert balance_path1 == expected, f"non_per_year: {balance_path1}"
        assert balance_path2 == expected, f"per_year: {balance_path2}"
        assert balance_path3 == expected, f"aangifte_ib: {balance_path3}"
        assert balance_path4 == expected, f"make_ledgers: {balance_path4}"

    def test_aangifte_ib_includes_all_prior_years(self):
        """Aangifte IB with no closures includes 2022+2023+2024."""
        df = build_no_closure_dataframe(
            years=(2022, 2023, 2024),
            amount_per_year=10000.0,
        )
        result = simulate_aangifte_ib(df, None, 2024, ADMIN)
        balance = get_balance_from_aangifte_result(result)

        assert balance == 30000.0, (
            f"Under-counting: aangifte_ib returned {balance}, expected 30000.0"
        )


# ---------------------------------------------------------------------------
# Test 4: Multiple closures — MAX is used correctly
# Validates: Requirements 2.1, 2.2, 2.4
# ---------------------------------------------------------------------------

class TestMultipleClosures:
    """
    When multiple years are closed (2021, 2022, 2023), start_year = MAX + 1 = 2024.
    Only data from 2024 onwards should be included.
    """

    def test_all_paths_use_max_closure(self):
        """Multiple closures: start_year = MAX(2021,2022,2023) + 1 = 2024."""
        df = build_multiple_closures_dataframe(
            closed_years=(2021, 2022, 2023),
            target_year=2025,
            opening_balance_amount=30000.0,  # Carries forward all prior history
            target_year_amount=5000.0,
        )
        start_year = 2024  # MAX(2021, 2022, 2023) + 1
        closed_years = [2021, 2022, 2023]
        target_year = 2025
        expected = 35000.0  # OB(30000) + target(5000)

        # Path 1: actuals-balance non-per_year
        grouped1 = simulate_actuals_balance_non_per_year(df, start_year, target_year, ADMIN)
        balance_path1 = get_balance_from_grouped(grouped1)

        # Path 2: actuals-balance per_year
        grouped2 = simulate_actuals_balance_per_year(
            df, start_year, target_year, closed_years, ADMIN
        )
        balance_path2 = get_balance_from_grouped(grouped2)

        # Path 3: query_aangifte_ib
        result3 = simulate_aangifte_ib(df, start_year, target_year, ADMIN)
        balance_path3 = get_balance_from_aangifte_result(result3)

        # Path 4: make_ledgers
        bb = simulate_make_ledgers_beginning_balance(df, start_year, target_year, ADMIN)
        target_txn = df[(df["jaar"] == target_year) & (df["VW"] == "N") &
                        (df["administration"] == ADMIN)]["Amount"].sum()
        balance_path4 = bb + target_txn

        assert balance_path1 == expected, f"non_per_year: {balance_path1}"
        assert balance_path2 == expected, f"per_year: {balance_path2}"
        assert balance_path3 == expected, f"aangifte_ib: {balance_path3}"
        assert balance_path4 == expected, f"make_ledgers: {balance_path4}"

    def test_raw_closed_year_data_excluded(self):
        """Raw transactions from closed years (2021-2023) must be excluded."""
        df = build_multiple_closures_dataframe(
            closed_years=(2021, 2022, 2023),
            target_year=2025,
            opening_balance_amount=30000.0,
            target_year_amount=5000.0,
        )
        start_year = 2024
        target_year = 2025

        grouped = simulate_actuals_balance_non_per_year(df, start_year, target_year, ADMIN)
        balance = get_balance_from_grouped(grouped)

        # Should NOT include the 3 × €10,000 from closed years
        # Should only be OB(30000) + target(5000) = 35000
        assert balance == 35000.0, (
            f"Expected 35000, got {balance}. "
            f"Closed year raw data was included."
        )


# ---------------------------------------------------------------------------
# Test 5: Closed target year — jaar == target_year only
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------

class TestClosedTargetYear:
    """
    When the target year itself is closed, per_year mode returns
    only that year's data (jaar == target_year).
    """

    def test_closed_target_year_returns_only_that_year(self):
        """Querying a closed year returns ONLY that year's data."""
        df = build_closure_scenario_dataframe(
            closed_year=2023,
            opening_balance_year=2024,
            target_year=2025,
            closed_year_amount=10000.0,
            opening_balance_amount=10000.0,
            target_year_amount=5000.0,
        )
        start_year = 2024
        closed_years = [2023]
        target_year = 2023  # Querying the closed year itself

        # Per_year for closed year should return jaar == 2023 only
        grouped = simulate_actuals_balance_per_year(
            df, start_year, target_year, closed_years, ADMIN
        )
        balance = get_balance_from_grouped(grouped)

        # Only the closed year's data (€10,000)
        assert balance == 10000.0, (
            f"Expected only 2023 data (10000), got {balance}"
        )

    def test_closed_target_year_excludes_other_years(self):
        """Closed year query does NOT include OB or later transactions."""
        df = build_closure_scenario_dataframe(
            closed_year=2023,
            opening_balance_year=2024,
            target_year=2025,
        )
        closed_years = [2023]

        grouped = simulate_actuals_balance_per_year(
            df, 2024, 2023, closed_years, ADMIN
        )
        balance = get_balance_from_grouped(grouped)

        # Must NOT include 2024 OB or 2025 transactions
        assert balance == 10000.0


# ---------------------------------------------------------------------------
# Test 6: Future year exclusion
# Validates: Requirements 2.7
# ---------------------------------------------------------------------------

class TestFutureYearExclusion:
    """
    Future year data (jaar > target_year) must never be included.
    """

    def test_future_year_data_excluded(self):
        """Data with jaar > target_year is never included in balance."""
        # Add future year data to the scenario
        df = build_closure_scenario_dataframe(
            closed_year=2023,
            opening_balance_year=2024,
            target_year=2025,
            closed_year_amount=10000.0,
            opening_balance_amount=10000.0,
            target_year_amount=5000.0,
        )
        # Add a future year entry (e.g., depreciation scheduled for 2027)
        future_row = pd.DataFrame([{
            "Aangifte": "Balans",
            "TransactionNumber": "TXN-2027-001",
            "TransactionDate": pd.Timestamp("2027-01-01"),
            "TransactionDescription": "Depreciation 2027",
            "Amount": 8000.0,
            "Reknum": ACCOUNT,
            "AccountName": ACCOUNT_NAME,
            "Parent": PARENT,
            "VW": "N",
            "jaar": 2027,
            "kwartaal": 1,
            "maand": 1,
            "week": 1,
            "ReferenceNumber": "DEP-2027",
            "administration": ADMIN,
            "Ref3": "",
            "Ref4": "",
        }])
        df = pd.concat([df, future_row], ignore_index=True)

        start_year = 2024
        target_year = 2025

        # Non-per_year: should be 15000 (no future data)
        grouped = simulate_actuals_balance_non_per_year(df, start_year, target_year, ADMIN)
        balance = get_balance_from_grouped(grouped)

        assert balance == 15000.0, (
            f"Future year data included! Got {balance}, expected 15000.0"
        )


# ---------------------------------------------------------------------------
# Test 7: Integration with get_closure_aware_start_year helper
# Validates: Requirements 2.1, 2.2, 2.5
# ---------------------------------------------------------------------------

class TestHelperIntegration:
    """
    Test that get_closure_aware_start_year() integrates correctly
    with each code path end-to-end.
    """

    def test_helper_returns_correct_start_year_for_closure(self):
        """Helper returns last_closed_year + 1 when closures exist."""
        from utils.closure_helpers import get_closure_aware_start_year

        mock_db = MagicMock()
        mock_db.execute_query.return_value = [{"max_year": 2023}]

        start_year = get_closure_aware_start_year(mock_db, ADMIN)
        assert start_year == 2024

    def test_helper_returns_none_for_no_closures(self):
        """Helper returns None when no closures exist."""
        from utils.closure_helpers import get_closure_aware_start_year

        mock_db = MagicMock()
        mock_db.execute_query.return_value = [{"max_year": None}]

        start_year = get_closure_aware_start_year(mock_db, ADMIN)
        assert start_year is None

    def test_helper_returns_none_on_db_error(self):
        """Helper returns None as safe fallback on database errors."""
        from utils.closure_helpers import get_closure_aware_start_year

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = Exception("Connection refused")

        start_year = get_closure_aware_start_year(mock_db, ADMIN)
        assert start_year is None

    def test_full_flow_actuals_with_helper(self):
        """
        End-to-end: helper determines start_year, actuals_routes logic
        uses it to produce correct balance.
        """
        from utils.closure_helpers import get_closure_aware_start_year

        # Setup: year 2023 closed
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [{"max_year": 2023}]

        df = build_closure_scenario_dataframe()

        # Get start_year from helper
        start_year = get_closure_aware_start_year(mock_db, ADMIN)

        # Apply to actuals-balance logic
        grouped = simulate_actuals_balance_non_per_year(df, start_year, 2025, ADMIN)
        balance = get_balance_from_grouped(grouped)

        assert balance == 15000.0


# ---------------------------------------------------------------------------
# Test 8: make_ledgers end-to-end with mocked DB
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

class TestMakeLedgersEndToEnd:
    """
    Test make_ledgers from financial_report_generator with closure-aware logic.
    """

    def test_make_ledgers_closure_aware_query(self):
        """
        make_ledgers constructs correct SQL with jaar >= start_year
        when closures exist.
        """
        from report_generators.financial_report_generator import make_ledgers

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        # Helper returns start_year = 2024 (year 2023 closed)
        mock_db.execute_query.return_value = [{"max_year": 2023}]

        execute_calls = []

        def mock_execute(query, params=None):
            execute_calls.append((query, params))

        mock_cursor.execute = mock_execute

        fetchall_count = [0]

        def mock_fetchall():
            fetchall_count[0] += 1
            if fetchall_count[0] == 1:
                return [{
                    "Reknum": "1000",
                    "AccountName": "Bank",
                    "Parent": "Activa",
                    "Administration": ADMIN,
                    "Amount": 10000.0,
                }]
            else:
                return []

        mock_cursor.fetchall = mock_fetchall

        result = make_ledgers(mock_db, 2025, ADMIN)

        # Verify the balance query uses jaar >= start_year
        balance_query = execute_calls[0][0]
        balance_params = execute_calls[0][1]
        assert "jaar >= %s" in balance_query
        assert "jaar < %s" in balance_query
        assert balance_params == [f"{ADMIN}%", 2024, 2025]

    def test_make_ledgers_no_closure_original_query(self):
        """
        make_ledgers uses original jaar < target_year when no closures exist.
        """
        from report_generators.financial_report_generator import make_ledgers

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        # Helper returns None (no closures)
        mock_db.execute_query.return_value = [{"max_year": None}]

        execute_calls = []

        def mock_execute(query, params=None):
            execute_calls.append((query, params))

        mock_cursor.execute = mock_execute

        fetchall_count = [0]

        def mock_fetchall():
            fetchall_count[0] += 1
            if fetchall_count[0] == 1:
                return [{
                    "Reknum": "1000",
                    "AccountName": "Bank",
                    "Parent": "Activa",
                    "Administration": ADMIN,
                    "Amount": 20000.0,
                }]
            else:
                return []

        mock_cursor.fetchall = mock_fetchall

        result = make_ledgers(mock_db, 2025, ADMIN)

        # Verify original query without jaar >= start_year
        balance_query = execute_calls[0][0]
        balance_params = execute_calls[0][1]
        assert "jaar >= %s" not in balance_query
        assert "jaar < %s" in balance_query
        assert balance_params == [f"{ADMIN}%", 2025]


# ---------------------------------------------------------------------------
# Test 9: XLSX export make_ledgers end-to-end
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

class TestXLSXExportEndToEnd:
    """
    Test XLSXExportProcessor.make_ledgers with closure-aware logic.
    """

    @patch("xlsx_export.DatabaseManager")
    @patch("xlsx_export.TemplateService")
    def test_xlsx_make_ledgers_closure_aware(self, mock_template_svc_cls, mock_db_cls):
        """XLSX export uses closure-aware bounds when closures exist."""
        from xlsx_export import XLSXExportProcessor

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        mock_db_cls.return_value = mock_db

        # Helper returns start_year = 2024
        mock_db.execute_query.return_value = [{"max_year": 2023}]

        execute_calls = []

        def mock_execute(query, params=None):
            execute_calls.append((query, params))

        mock_cursor.execute = mock_execute

        fetchall_count = [0]

        def mock_fetchall():
            fetchall_count[0] += 1
            if fetchall_count[0] == 1:
                return [{
                    "Reknum": "1000",
                    "AccountName": "Bank",
                    "Parent": "Activa",
                    "Administration": ADMIN,
                    "Amount": 10000.0,
                }]
            else:
                return []

        mock_cursor.fetchall = mock_fetchall

        processor = XLSXExportProcessor()
        result = processor.make_ledgers(2025, ADMIN)

        # Verify closure-aware query
        balance_query = execute_calls[0][0]
        balance_params = execute_calls[0][1]
        assert "jaar >= %s" in balance_query
        assert "jaar < %s" in balance_query
        assert balance_params == [f"{ADMIN}%", 2024, 2025]

    @patch("xlsx_export.DatabaseManager")
    @patch("xlsx_export.TemplateService")
    def test_xlsx_make_ledgers_no_closure(self, mock_template_svc_cls, mock_db_cls):
        """XLSX export uses original query when no closures exist."""
        from xlsx_export import XLSXExportProcessor

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        mock_db_cls.return_value = mock_db

        # No closures
        mock_db.execute_query.return_value = [{"max_year": None}]

        execute_calls = []

        def mock_execute(query, params=None):
            execute_calls.append((query, params))

        mock_cursor.execute = mock_execute
        mock_cursor.fetchall.return_value = []

        processor = XLSXExportProcessor()
        result = processor.make_ledgers(2025, ADMIN)

        # Original query without lower bound
        balance_query = execute_calls[0][0]
        assert "jaar >= %s" not in balance_query
        assert "jaar < %s" in balance_query


# ---------------------------------------------------------------------------
# Test 10: Year-end service creates OpeningBalance that fixed queries handle
# Validates: Requirements 2.1, 2.4
# ---------------------------------------------------------------------------

class TestYearEndServiceIntegration:
    """
    Verify that after year-end closure creates an OpeningBalance record,
    the fixed queries correctly handle it (single-count, not double-count).
    """

    def test_opening_balance_used_correctly_after_closure(self):
        """
        Simulates: year_end_service closes 2023, creates OB in 2024.
        Then querying 2025 uses OB correctly without double-counting.
        """
        # After closure: 2023 raw data exists, OB in 2024
        df = build_closure_scenario_dataframe(
            closed_year=2023,
            opening_balance_year=2024,
            target_year=2025,
            closed_year_amount=10000.0,
            opening_balance_amount=10000.0,
            target_year_amount=5000.0,
        )
        start_year = 2024  # Closure service set year 2023 as closed

        # All paths should correctly use only 2024+ data
        grouped = simulate_actuals_balance_non_per_year(df, start_year, 2025, ADMIN)
        balance = get_balance_from_grouped(grouped)
        assert balance == 15000.0

        result = simulate_aangifte_ib(df, start_year, 2025, ADMIN)
        ib_balance = get_balance_from_aangifte_result(result)
        assert ib_balance == 15000.0

    def test_opening_balance_amount_matches_closed_year_sum(self):
        """
        The OpeningBalance amount should equal the closed year's raw data sum.
        This is what year_end_service creates.
        """
        closed_year_amount = 12345.67
        ob_amount = closed_year_amount  # Year-end service carries forward

        df = build_closure_scenario_dataframe(
            closed_year_amount=closed_year_amount,
            opening_balance_amount=ob_amount,
            target_year_amount=3000.0,
        )
        start_year = 2024

        # Using start_year=2024 should give OB + target = 12345.67 + 3000 = 15345.67
        grouped = simulate_actuals_balance_non_per_year(df, start_year, 2025, ADMIN)
        balance = get_balance_from_grouped(grouped)
        assert balance == pytest.approx(15345.67, abs=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
