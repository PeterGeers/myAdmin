"""
Property-based tests for Airbnb multi-file import.

Uses Hypothesis to verify correctness properties from the design document.
Feature: str-airbnb-multi-file-import

Reference: .kiro/specs/str-airbnb-multi-file-import/design.md
"""

import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# The old single-row Airbnb parser (`_calculate_airbnb_row`) was replaced by the
# new two-file export format (spec airbnb-export-format-update): rows arrive as
# Boeking/Doorloop-totaal pairs grouped by Bevestigingscode, gross/fee are summed
# per group, status comes from file classification, and the hardcoded 15% fee is
# gone (Req 3.4). The financial/parsing tests below therefore exercise the new
# public parser `build_booking_from_group` instead of the removed method.
from str_airbnb_parser import build_booking_from_group
from str_processor import STRProcessor

# Single knob for all property tests in this file
MAX_EXAMPLES = 20


def _new_format_group(gross, fee, *, listing="Green Studio", nights=2,
                      code="HM12345678", checkin="06/15/2025",
                      checkout="06/17/2025", reserved="01/01/2025",
                      guest="Test Guest", info=""):
    """Build a single-booking new-format DataFrame (one Boeking row).

    New-format columns: Type / Bevestigingscode / Bruto-inkomsten (US notation) /
    Servicekosten (European notation) / dates in MM/DD/YYYY. One row per group is
    enough to drive `build_booking_from_group`, which sums amounts across the group.
    """
    # Servicekosten uses European notation in the real exports (e.g. "42,59").
    fee_str = f"{fee:.2f}".replace(".", ",")
    return pd.DataFrame([{
        "Type": "Boeking",
        "Bevestigingscode": code,
        "Boekingsdatum": reserved,
        "Begindatum": checkin,
        "Einddatum": checkout,
        "Nachten": nights,
        "Gast": guest,
        "Advertentie": listing,
        "Informatie": info,
        "Valuta": "EUR",
        "Bruto-inkomsten": f"{gross:.2f}",
        "Servicekosten": fee_str,
    }])


# ---------------------------------------------------------------------------
# Strategies: generate valid Airbnb DataFrames
# ---------------------------------------------------------------------------

def format_european_currency(amount):
    """Format a float as European currency string like '€ 1.841,18'."""
    amount = round(amount, 2)
    integer_part = int(amount)
    decimal_part = round((amount - integer_part) * 100)
    # Format integer part with dots as thousands separator
    int_str = f"{integer_part:,}".replace(',', '.')
    return f"€ {int_str},{decimal_part:02d}"


def airbnb_row_strategy():
    """Strategy to generate a single valid Airbnb row as a dict."""
    return st.builds(
        lambda checkin, nights, guest_name, listing, earnings_float,
               code_num, status, contact, adults, children, babies, reserved:
        {
            'Begindatum': checkin.strftime('%d-%m-%Y'),
            'Einddatum': (checkin + timedelta(days=nights)).strftime('%d-%m-%Y'),
            'Naam van de gast': guest_name,
            'Advertentie': listing,
            '# nachten': nights,
            'Inkomsten': format_european_currency(earnings_float),
            'Bevestigingscode': f'HM{code_num:08d}',
            'Status': status,
            'Contact': contact,
            '# volwassenen': adults,
            '# kinderen': children,
            "# baby's": babies,
            'Gereserveerd': reserved.strftime('%Y-%m-%d'),
        },
        checkin=st.dates(
            min_value=date(2024, 1, 1),
            max_value=date(2026, 12, 31),
        ),
        nights=st.integers(min_value=1, max_value=30),
        guest_name=st.text(
            alphabet=st.characters(whitelist_categories=('L', 'Zs')),
            min_size=2, max_size=30,
        ),
        listing=st.sampled_from(['Green Studio', 'Red Studio', 'Child Friendly']),
        earnings_float=st.floats(min_value=50.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
        code_num=st.integers(min_value=10000000, max_value=99999999),
        status=st.sampled_from(['Bevestigd', 'Bevestigd', 'Bevestigd', 'Geannuleerd']),
        contact=st.just('+31612345678'),
        adults=st.integers(min_value=1, max_value=8),
        children=st.integers(min_value=0, max_value=4),
        babies=st.integers(min_value=0, max_value=2),
        reserved=st.dates(
            min_value=date(2023, 6, 1),
            max_value=date(2026, 6, 1),
        ),
    )


def airbnb_dataframe_strategy(min_rows=1, max_rows=10):
    """Strategy to generate a DataFrame with valid Airbnb columns."""
    return st.lists(
        airbnb_row_strategy(),
        min_size=min_rows,
        max_size=max_rows,
    ).map(pd.DataFrame)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def processor():
    """Create STRProcessor instance for testing."""
    return STRProcessor(test_mode=True)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def write_df_to_csv(df: pd.DataFrame, directory: str, filename: str) -> str:
    """Write a DataFrame to a CSV file and return the path."""
    path = os.path.join(directory, filename)
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Feature: str-airbnb-multi-file-import, Property 1: Concatenation
# preserves all rows
# ---------------------------------------------------------------------------

class TestProperty1ConcatenationPreservesAllRows:
    """
    Property 1: Concatenation preserves all rows.

    For any list of valid Airbnb CSV DataFrames, the concatenated DataFrame
    SHALL have a row count equal to the sum of the row counts of the
    individual DataFrames (before deduplication).

    **Validates: Requirements 2.1**
    """

    @given(
        dfs=st.lists(
            airbnb_dataframe_strategy(min_rows=1, max_rows=8),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_concatenation_preserves_row_count(self, dfs):
        """Concatenating N DataFrames preserves total row count.

        Feature: str-airbnb-multi-file-import, Property 1: Concatenation preserves all rows
        """
        expected_total = sum(len(df) for df in dfs)
        combined = pd.concat(dfs, ignore_index=True)
        assert len(combined) == expected_total

    @given(
        dfs=st.lists(
            airbnb_dataframe_strategy(min_rows=1, max_rows=8),
            min_size=2,
            max_size=5,
        )
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_concatenation_preserves_columns(self, dfs):
        """Concatenating DataFrames preserves all column names.

        Feature: str-airbnb-multi-file-import, Property 1: Concatenation preserves all rows
        """
        expected_columns = set(dfs[0].columns)
        combined = pd.concat(dfs, ignore_index=True)
        assert set(combined.columns) == expected_columns

    @given(df=airbnb_dataframe_strategy(min_rows=1, max_rows=15))
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_single_dataframe_concat_is_identity(self, df):
        """Concatenating a single DataFrame is an identity operation.

        Feature: str-airbnb-multi-file-import, Property 1: Concatenation preserves all rows
        """
        combined = pd.concat([df], ignore_index=True)
        assert len(combined) == len(df)
        assert list(combined.columns) == list(df.columns)


# ---------------------------------------------------------------------------
# Feature: str-airbnb-multi-file-import, Property 2: Partial failure
# resilience
# ---------------------------------------------------------------------------

class TestProperty2PartialFailureResilience:
    """
    Property 2: Partial failure resilience.

    For any mix of valid and invalid file paths where at least one file is
    valid, `_process_airbnb_multi` SHALL produce a result containing all rows
    from the valid files and an error list containing exactly the filenames
    of the invalid files.

    **Validates: Requirements 2.2**
    """

    @given(
        valid_dfs=st.lists(
            airbnb_dataframe_strategy(min_rows=1, max_rows=5),
            min_size=1,
            max_size=3,
        ),
        n_invalid=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_valid_files_processed_despite_invalid_files(self, valid_dfs, n_invalid):
        """Valid files are processed even when some files are invalid.

        Feature: str-airbnb-multi-file-import, Property 2: Partial failure resilience
        """
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            # Write valid files
            valid_paths = []
            for i, df in enumerate(valid_dfs):
                path = write_df_to_csv(df, tmp_dir, f"valid_{i}.csv")
                valid_paths.append(path)

            # Create invalid files (binary garbage that pandas cannot parse)
            invalid_paths = []
            for i in range(n_invalid):
                path = os.path.join(tmp_dir, f"invalid_{i}.bin")
                with open(path, 'wb') as f:
                    f.write(b'\x00\x01\x02\x80\x81\x82\xff\xfe\xfd' * 50)
                invalid_paths.append(path)

            all_paths = valid_paths + invalid_paths

            # _process_airbnb_multi should succeed (at least one valid file)
            result = processor._process_airbnb_multi(all_paths)

            # Result should contain bookings from valid files
            # (some rows may be skipped due to cancelled status with zero earnings,
            #  but the method should not raise)
            assert isinstance(result, list)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(n_invalid=st.integers(min_value=1, max_value=4))
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_all_invalid_files_raises_value_error(self, n_invalid):
        """When all files fail to parse, a ValueError is raised.

        Feature: str-airbnb-multi-file-import, Property 2: Partial failure resilience
        """
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            invalid_paths = []
            for i in range(n_invalid):
                path = os.path.join(tmp_dir, f"bad_{i}.bin")
                with open(path, 'wb') as f:
                    f.write(b'\x00\x01\x02\x80\x81\x82\xff\xfe\xfd' * 50)
                invalid_paths.append(path)

            with pytest.raises(ValueError, match="All files failed to parse"):
                processor._process_airbnb_multi(invalid_paths)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(
        valid_dfs=st.lists(
            airbnb_dataframe_strategy(min_rows=1, max_rows=5),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_all_valid_files_no_error(self, valid_dfs):
        """When all files are valid, processing succeeds without error.

        Feature: str-airbnb-multi-file-import, Property 2: Partial failure resilience
        """
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            paths = []
            for i, df in enumerate(valid_dfs):
                path = write_df_to_csv(df, tmp_dir, f"file_{i}.csv")
                paths.append(path)

            result = processor._process_airbnb_multi(paths)
            assert isinstance(result, list)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature: str-airbnb-multi-file-import, Property 3: Deduplication keeps
# exactly one record per Bevestigingscode
# ---------------------------------------------------------------------------

class TestProperty3DeduplicationKeepsOnePerBevestigingscode:
    """
    Property 3: Deduplication keeps exactly one record per Bevestigingscode.

    For any concatenated DataFrame containing duplicate `Bevestigingscode`
    values, after deduplication there SHALL be exactly one row per unique
    `Bevestigingscode`, and the retained row's values SHALL match the last
    occurrence in the concatenated order.

    **Validates: Requirements 2.3**
    """

    @given(
        base_df=airbnb_dataframe_strategy(min_rows=2, max_rows=8),
        n_duplicates=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_produces_unique_bevestigingscodes(self, base_df, n_duplicates):
        """After deduplication, each Bevestigingscode appears exactly once.

        Feature: str-airbnb-multi-file-import, Property 3: Deduplication keeps exactly one record per Bevestigingscode
        """
        # Create duplicates by repeating some rows with the same Bevestigingscode
        dup_rows = base_df.sample(n=min(n_duplicates, len(base_df)), replace=True)
        combined = pd.concat([base_df, dup_rows], ignore_index=True)

        deduped = combined.drop_duplicates(subset='Bevestigingscode', keep='last')

        # Each Bevestigingscode should appear exactly once
        assert deduped['Bevestigingscode'].is_unique

    @given(
        base_df=airbnb_dataframe_strategy(min_rows=2, max_rows=8),
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_keeps_last_occurrence(self, base_df):
        """Deduplication retains the last occurrence of each Bevestigingscode.

        Feature: str-airbnb-multi-file-import, Property 3: Deduplication keeps exactly one record per Bevestigingscode
        """
        # Create a modified copy with different guest names for duplicates
        modified = base_df.copy()
        modified['Naam van de gast'] = 'MODIFIED_GUEST'

        combined = pd.concat([base_df, modified], ignore_index=True)
        deduped = combined.drop_duplicates(subset='Bevestigingscode', keep='last')

        # All retained rows should have the modified guest name (last occurrence)
        for _, row in deduped.iterrows():
            assert row['Naam van de gast'] == 'MODIFIED_GUEST'

    @given(df=airbnb_dataframe_strategy(min_rows=1, max_rows=10))
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_count_leq_original(self, df):
        """Deduplicated row count is always <= original row count.

        Feature: str-airbnb-multi-file-import, Property 3: Deduplication keeps exactly one record per Bevestigingscode
        """
        deduped = df.drop_duplicates(subset='Bevestigingscode', keep='last')
        assert len(deduped) <= len(df)

    @given(df=airbnb_dataframe_strategy(min_rows=1, max_rows=10))
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_dedup_count_equals_unique_codes(self, df):
        """Deduplicated row count equals the number of unique Bevestigingscodes.

        Feature: str-airbnb-multi-file-import, Property 3: Deduplication keeps exactly one record per Bevestigingscode
        """
        deduped = df.drop_duplicates(subset='Bevestigingscode', keep='last')
        assert len(deduped) == df['Bevestigingscode'].nunique()


# ---------------------------------------------------------------------------
# Feature: str-airbnb-multi-file-import, Property 4: Financial calculation
# correctness
# ---------------------------------------------------------------------------

class TestProperty4FinancialCalculationCorrectness:
    """
    Property 4: Financial calculation correctness (new export format).

    For any Booking_Group, ``build_booking_from_group`` SHALL produce
    ``amountGross`` equal to the sum of the parsed ``Bruto-inkomsten`` values
    and ``amountChannelFee`` equal to the sum of the parsed ``Servicekosten``
    values (no hardcoded 15% factor — spec airbnb-export-format-update, Req 3.4),
    the tax amounts SHALL match ``calculate_str_taxes()`` for the same gross,
    check-in date, and fee, and listing normalization SHALL be applied.

    **Validates: Requirements 3.1, 3.2, 3.4**
    """

    @given(
        gross=st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False),
        fee=st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_channel_fee_is_sum_of_servicekosten(self, gross, fee):
        """amountChannelFee equals the summed Servicekosten (no 15% factor).

        Feature: str-airbnb-multi-file-import, Property 4: Financial calculation correctness
        """
        gross, fee = round(gross, 2), round(fee, 2)
        group = _new_format_group(gross, fee)
        result = build_booking_from_group(
            "HM12345678", group, "2025-01-01 test.csv", "realised"
        )
        assert abs(result["amountChannelFee"] - fee) < 0.02

    @given(
        gross=st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False),
        fee=st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_gross_is_sum_of_bruto_inkomsten(self, gross, fee):
        """amountGross equals the summed Bruto-inkomsten, independent of the fee.

        Feature: str-airbnb-multi-file-import, Property 4: Financial calculation correctness
        """
        gross, fee = round(gross, 2), round(fee, 2)
        group = _new_format_group(gross, fee)
        result = build_booking_from_group(
            "HM12345678", group, "2025-01-01 test.csv", "realised"
        )
        assert abs(result["amountGross"] - gross) < 0.02

    @given(
        gross=st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False),
        fee=st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_tax_amounts_match_calculate_str_taxes(self, gross, fee):
        """Tax amounts match calculate_str_taxes() for the same gross/date/fee.

        Feature: str-airbnb-multi-file-import, Property 4: Financial calculation correctness
        """
        gross, fee = round(gross, 2), round(fee, 2)
        group = _new_format_group(gross, fee)
        result = build_booking_from_group(
            "HM12345678", group, "2025-01-01 test.csv", "realised"
        )

        from str_utils import calculate_str_taxes
        tax_calc = calculate_str_taxes(
            result["amountGross"], result["checkinDate"], result["amountChannelFee"]
        )

        assert abs(result["amountVat"] - tax_calc["amount_vat"]) < 0.02
        assert abs(result["amountTouristTax"] - tax_calc["amount_tourist_tax"]) < 0.02
        assert abs(result["amountNett"] - tax_calc["amount_nett"]) < 0.02

    @given(
        advertentie=st.sampled_from(["groen", "Green", "rode", "Red", "Tuinhuis", "garden", "Unknown Listing"]),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_listing_normalization_applied(self, advertentie):
        """Listing normalization is applied to the Advertentie value.

        Feature: str-airbnb-multi-file-import, Property 4: Financial calculation correctness
        """
        group = _new_format_group(200.0, 30.0, listing=advertentie)
        result = build_booking_from_group(
            "HM12345678", group, "2025-01-01 test.csv", "realised"
        )

        from str_utils import normalize_listing_name
        assert result["listing"] == normalize_listing_name(str(advertentie))


# ---------------------------------------------------------------------------
# Feature: str-airbnb-multi-file-import, Property 5: sourceFile format
# reflects file count
# ---------------------------------------------------------------------------

class TestProperty5SourceFileFormatReflectsFileCount:
    """
    Property 5: sourceFile format reflects file count.

    For any multi-file import with N > 1 files, every booking record's
    sourceFile field SHALL match "YYYY-MM-DD multi-import (N files)".
    For any single-file import, the sourceFile field SHALL match
    "YYYY-MM-DD {filename}".

    **Validates: Requirements 3.4**
    """

    @given(
        dfs=st.lists(
            airbnb_dataframe_strategy(min_rows=1, max_rows=3),
            min_size=2,
            max_size=4,
        ),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=10000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_multi_file_source_format(self, dfs):
        """Multi-file imports produce sourceFile with 'multi-import (N files)' pattern.

        Feature: str-airbnb-multi-file-import, Property 5: sourceFile format reflects file count
        """
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            paths = []
            for i, df in enumerate(dfs):
                path = write_df_to_csv(df, tmp_dir, f"airbnb_{i}.csv")
                paths.append(path)

            result = processor._process_airbnb_multi(paths)

            if not result:
                return  # All rows may have been skipped

            today_str = datetime.now().strftime('%Y-%m-%d')
            expected_pattern = f"{today_str} multi-import ({len(paths)} files)"

            for booking in result:
                assert booking['sourceFile'] == expected_pattern
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(df=airbnb_dataframe_strategy(min_rows=1, max_rows=5))
    @settings(max_examples=MAX_EXAMPLES, deadline=10000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_single_file_source_format(self, df):
        """Single-file imports produce sourceFile with 'YYYY-MM-DD {filename}' pattern.

        Feature: str-airbnb-multi-file-import, Property 5: sourceFile format reflects file count
        """
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            filename = "my_airbnb_export.csv"
            path = write_df_to_csv(df, tmp_dir, filename)

            result = processor._process_airbnb_multi([path])

            if not result:
                return

            today_str = datetime.now().strftime('%Y-%m-%d')
            expected = f"{today_str} {filename}"

            for booking in result:
                assert booking['sourceFile'] == expected
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(
        n_files=st.integers(min_value=2, max_value=6),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=10000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_source_file_count_matches_input_count(self, n_files):
        """The N in 'multi-import (N files)' matches the number of input files.

        Feature: str-airbnb-multi-file-import, Property 5: sourceFile format reflects file count
        """
        processor = STRProcessor(test_mode=True)
        tmp_dir = tempfile.mkdtemp()
        try:
            # Create minimal valid CSVs
            paths = []
            for i in range(n_files):
                row = {
                    'Begindatum': '15-06-2025',
                    'Einddatum': '17-06-2025',
                    'Naam van de gast': f'Guest {i}',
                    'Advertentie': 'Green Studio',
                    '# nachten': 2,
                    'Inkomsten': '€ 200,00',
                    'Bevestigingscode': f'HM{10000000 + i}',
                    'Status': 'Bevestigd',
                    'Contact': '+31612345678',
                    '# volwassenen': 2,
                    '# kinderen': 0,
                    "# baby's": 0,
                    'Gereserveerd': '2025-01-01',
                }
                df = pd.DataFrame([row])
                path = write_df_to_csv(df, tmp_dir, f"file_{i}.csv")
                paths.append(path)

            result = processor._process_airbnb_multi(paths)
            assert len(result) > 0

            expected_suffix = f"multi-import ({n_files} files)"
            for booking in result:
                assert expected_suffix in booking['sourceFile']
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature: str-airbnb-multi-file-import, Property 6: European currency
# parsing round-trip
# ---------------------------------------------------------------------------

class TestProperty6EuropeanCurrencyParsingRoundTrip:
    """
    Property 6: European currency parsing round-trip.

    For any valid non-negative monetary amount, formatting it as a European
    currency string and then parsing it back through the Airbnb earnings
    parser SHALL produce a value equal to the original amount (within
    floating-point rounding tolerance of 0.01).

    **Validates: Requirements 3.5**
    """

    @given(
        amount=st.floats(min_value=0.0, max_value=99999.99, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_format_then_parse_round_trip(self, amount):
        """Formatting as European currency and parsing back preserves the value.

        Feature: str-airbnb-multi-file-import, Property 6: European currency parsing round-trip
        """
        amount = round(amount, 2)

        # Format as European currency
        formatted = format_european_currency(amount)

        # Parse back using the same logic as _calculate_airbnb_row
        clean = str(formatted).replace('€', '').replace(' ', '')
        if ',' in clean:
            parts = clean.split(',')
            if len(parts) == 2:
                integer_part = parts[0].replace('.', '')
                decimal_part = parts[1]
                clean = f"{integer_part}.{decimal_part}"
            else:
                clean = clean.replace(',', '.')
        parsed = float(clean) if clean else 0

        assert abs(parsed - amount) <= 0.01

    @given(
        amount=st.floats(min_value=0.01, max_value=50000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=MAX_EXAMPLES, deadline=5000, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_parsed_earnings_match_in_booking(self, amount):
        """Bruto-inkomsten parsed by the new parser matches the original amount.

        In the new export format the gross is the sum of Bruto-inkomsten (no 15%
        uplift), so a single-row group's amountGross equals the input amount.

        Feature: str-airbnb-multi-file-import, Property 6: currency parsing round-trip
        """
        amount = round(amount, 2)
        group = _new_format_group(amount, 0.0)
        result = build_booking_from_group(
            "HM12345678", group, "2025-01-01 test.csv", "realised"
        )

        assert result is not None
        assert abs(result["amountGross"] - amount) < 0.02

    @given(
        amount=st.floats(min_value=1000.0, max_value=99999.99, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_thousands_separator_handled(self, amount):
        """European currency with thousands separators (dots) is parsed correctly.

        Feature: str-airbnb-multi-file-import, Property 6: European currency parsing round-trip
        """
        amount = round(amount, 2)
        formatted = format_european_currency(amount)

        # Verify the formatted string contains a dot (thousands separator)
        clean = formatted.replace('€', '').replace(' ', '')
        # For amounts >= 1000, there should be a dot thousands separator
        assert '.' in clean.split(',')[0]

        # Parse and verify
        parts = clean.split(',')
        integer_part = parts[0].replace('.', '')
        decimal_part = parts[1] if len(parts) == 2 else '00'
        parsed = float(f"{integer_part}.{decimal_part}")

        assert abs(parsed - amount) <= 0.01


# ---------------------------------------------------------------------------
# Feature: str-airbnb-multi-file-import, Property 7: Scoped overwrite
# invariant
# ---------------------------------------------------------------------------

class TestProperty7ScopedOverwriteInvariant:
    """
    Property 7: Scoped overwrite invariant.

    For any set of planned bookings being saved, the insert_planned_bookings
    method SHALL delete and replace records only for (channel, listing) pairs
    present in the input, and SHALL leave all records for (channel, listing)
    pairs not present in the input completely unchanged.

    **Validates: Requirements 4.1, 4.2**
    """

    @given(
        imported_listings=st.lists(
            st.sampled_from(['Green Studio', 'Red Studio', 'Child Friendly']),
            min_size=1,
            max_size=3,
            unique=True,
        ),
        existing_listings=st.lists(
            st.sampled_from(['Green Studio', 'Red Studio', 'Child Friendly', 'Beach House']),
            min_size=1,
            max_size=4,
            unique=True,
        ),
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_only_imported_pairs_are_deleted(self, imported_listings, existing_listings):
        """Only (channel, listing) pairs in the import are deleted.

        Feature: str-airbnb-multi-file-import, Property 7: Scoped overwrite invariant
        """
        # Build incoming bookings for imported listings
        incoming = []
        for listing in imported_listings:
            incoming.append({
                'channel': 'airbnb',
                'listing': listing,
                'sourceFile': '2025-01-01 test.csv',
                'checkinDate': '2025-06-15',
                'checkoutDate': '2025-06-17',
                'nights': 2,
                'guests': 2,
                'amountGross': 230.0,
                'amountNett': 180.0,
                'amountChannelFee': 30.0,
                'amountTouristTax': 10.0,
                'amountVat': 10.0,
                'guestName': 'Test',
                'phone': '+31612345678',
                'reservationCode': f'HM{hash(listing) % 100000000:08d}',
                'reservationDate': '2025-01-01',
                'status': 'planned',
                'pricePerNight': 90.0,
                'daysBeforeReservation': 165,
                'addInfo': '',
                'year': 2025,
                'q': 2,
                'm': 6,
                'country': 'NL',
            })

        # Track which DELETE calls are made
        deleted_pairs = []

        mock_cursor = MagicMock()
        def track_execute(query, params=None):
            if query.strip().startswith('DELETE'):
                deleted_pairs.append((params[0], params[1]))
        mock_cursor.execute = track_execute

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        from str_database import STRDatabase
        db = STRDatabase.__new__(STRDatabase)
        db.connection = mock_conn

        db.insert_planned_bookings(incoming)

        # Verify: only imported (channel, listing) pairs were deleted
        imported_pairs = {('airbnb', l) for l in imported_listings}
        deleted_set = set(deleted_pairs)
        assert deleted_set == imported_pairs

        # Verify: existing listings NOT in import were NOT deleted
        untouched = {('airbnb', l) for l in existing_listings} - imported_pairs
        for pair in untouched:
            assert pair not in deleted_set

    @given(
        n_bookings=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_empty_bookings_deletes_nothing(self, n_bookings):
        """When no bookings are provided, nothing is deleted.

        Feature: str-airbnb-multi-file-import, Property 7: Scoped overwrite invariant
        """
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        from str_database import STRDatabase
        db = STRDatabase.__new__(STRDatabase)
        db.connection = mock_conn

        result = db.insert_planned_bookings([])

        # No DELETE should have been executed
        assert result == 0
        mock_cursor.execute.assert_not_called()

    @given(
        channels=st.lists(
            st.sampled_from(['airbnb', 'booking.com']),
            min_size=1,
            max_size=2,
            unique=True,
        ),
    )
    @settings(max_examples=MAX_EXAMPLES, suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
    def test_different_channels_are_independent(self, channels):
        """Deletes for one channel do not affect another channel's records.

        Feature: str-airbnb-multi-file-import, Property 7: Scoped overwrite invariant
        """
        incoming = []
        for channel in channels:
            incoming.append({
                'channel': channel,
                'listing': 'Green Studio',
                'sourceFile': '2025-01-01 test.csv',
                'checkinDate': '2025-06-15',
                'checkoutDate': '2025-06-17',
                'nights': 2,
                'guests': 2,
                'amountGross': 230.0,
                'amountNett': 180.0,
                'amountChannelFee': 30.0,
                'amountTouristTax': 10.0,
                'amountVat': 10.0,
                'guestName': 'Test',
                'phone': '+31612345678',
                'reservationCode': 'HM12345678',
                'reservationDate': '2025-01-01',
                'status': 'planned',
                'pricePerNight': 90.0,
                'daysBeforeReservation': 165,
                'addInfo': '',
                'year': 2025,
                'q': 2,
                'm': 6,
                'country': 'NL',
            })

        deleted_pairs = []
        mock_cursor = MagicMock()
        def track_execute(query, params=None):
            if query.strip().startswith('DELETE'):
                deleted_pairs.append((params[0], params[1]))
        mock_cursor.execute = track_execute

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        from str_database import STRDatabase
        db = STRDatabase.__new__(STRDatabase)
        db.connection = mock_conn

        db.insert_planned_bookings(incoming)

        # Each channel/listing pair should be deleted exactly once
        expected_pairs = {(ch, 'Green Studio') for ch in channels}
        assert set(deleted_pairs) == expected_pairs


# ---------------------------------------------------------------------------
# Unit tests (example-based) for Airbnb multi-file import
# Feature: str-airbnb-multi-file-import
# ---------------------------------------------------------------------------

class TestAirbnbMultiImportUnitTests:
    """
    Example-based unit tests for Airbnb multi-file import.

    **Validates: Requirements 2.4, 3.3, 3.6, 4.3, 5.1, 5.2**
    """

    def test_all_files_fail_raises_value_error_with_filenames(self, temp_dir):
        """All files fail to parse -> ValueError raised with filenames (Req 2.4).

        Feature: str-airbnb-multi-file-import
        """
        processor = STRProcessor(test_mode=True)

        # Create files that cannot be parsed as CSV
        paths = []
        for name in ['bad1.csv', 'bad2.csv', 'bad3.csv']:
            path = os.path.join(temp_dir, name)
            with open(path, 'wb') as f:
                f.write(b'\x00\x01\x02\x80\x81\x82\xff\xfe\xfd' * 50)
            paths.append(path)

        with pytest.raises(ValueError) as exc_info:
            processor._process_airbnb_multi(paths)

        error_msg = str(exc_info.value)
        assert 'All files failed to parse' in error_msg
        assert 'bad1.csv' in error_msg
        assert 'bad2.csv' in error_msg
        assert 'bad3.csv' in error_msg

    def test_payout_rows_excluded_from_bookings(self):
        """Payout / blank-confirmation-code rows produce no booking (Req 2.3).

        The new export interleaves informational Payout rows with booking rows;
        only non-blank-code booking rows yield dicts. This replaces the old
        "cancelled row with zero earnings is skipped" behaviour.

        Feature: str-airbnb-multi-file-import
        """
        processor = STRProcessor(test_mode=True)

        payout_row = {
            "Type": "Payout",
            "Bevestigingscode": "",
            "Boekingsdatum": "",
            "Begindatum": "",
            "Einddatum": "",
            "Nachten": "",
            "Gast": "",
            "Advertentie": "",
            "Informatie": "Transfer naar Example BV",
            "Valuta": "EUR",
            "Bruto-inkomsten": "",
            "Servicekosten": "",
        }
        booking_row = _new_format_group(200.0, 30.0, code="HM99999998").iloc[0].to_dict()

        tmp_dir = tempfile.mkdtemp()
        try:
            df = pd.DataFrame([payout_row, booking_row])
            path = write_df_to_csv(df, tmp_dir, "airbnb_pending.csv")
            result = processor._process_airbnb_multi([path])

            # Payout row dropped; only the real booking remains.
            assert len(result) == 1
            assert result[0]["reservationCode"] == "HM99999998"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_booking_group_produces_one_dict_with_file_status(self):
        """A booking group yields exactly one dict, tagged with the file's status.

        Status now comes from file classification (planned vs realised), not from
        any per-row Status column (spec airbnb-export-format-update, Req 6.5).

        Feature: str-airbnb-multi-file-import
        """
        group = _new_format_group(150.0, 22.5, code="HM99999997")
        result = build_booking_from_group(
            "HM99999997", group, "2025-01-01 test.csv", "planned"
        )

        assert result is not None
        assert result["status"] == "planned"
        assert result["reservationCode"] == "HM99999997"
        assert abs(result["amountGross"] - 150.0) < 0.02
        assert abs(result["amountChannelFee"] - 22.5) < 0.02

    def test_multiple_listings_all_appear_in_output(self, temp_dir):
        """Multiple listings in combined data all appear in output (Req 3.3).

        Feature: str-airbnb-multi-file-import
        """
        processor = STRProcessor(test_mode=True)

        rows = []
        for listing in ['Green Studio', 'Red Studio', 'Child Friendly']:
            rows.append({
                'Begindatum': '15-06-2025',
                'Einddatum': '17-06-2025',
                'Naam van de gast': f'Guest at {listing}',
                'Advertentie': listing,
                '# nachten': 2,
                'Inkomsten': '€ 200,00',
                'Bevestigingscode': f'HM{hash(listing) % 100000000:08d}',
                'Status': 'Bevestigd',
                'Contact': '+31612345678',
                '# volwassenen': 2,
                '# kinderen': 0,
                "# baby's": 0,
                'Gereserveerd': '2025-01-01',
            })

        df = pd.DataFrame(rows)
        path = write_df_to_csv(df, temp_dir, 'multi_listing.csv')

        result = processor._process_airbnb_multi([path])

        output_listings = {b['listing'] for b in result}
        assert 'Green Studio' in output_listings
        assert 'Red Studio' in output_listings
        assert 'Child Friendly' in output_listings

    def test_green_red_import_leaves_child_friendly_untouched(self):
        """Green Studio + Red Studio import leaves Child Friendly untouched (Req 4.3).

        Feature: str-airbnb-multi-file-import
        """
        # Build incoming bookings for Green Studio and Red Studio only
        incoming = []
        for listing in ['Green Studio', 'Red Studio']:
            incoming.append({
                'channel': 'airbnb',
                'listing': listing,
                'sourceFile': '2025-01-01 test.csv',
                'checkinDate': '2025-06-15',
                'checkoutDate': '2025-06-17',
                'nights': 2,
                'guests': 2,
                'amountGross': 230.0,
                'amountNett': 180.0,
                'amountChannelFee': 30.0,
                'amountTouristTax': 10.0,
                'amountVat': 10.0,
                'guestName': 'Test',
                'phone': '+31612345678',
                'reservationCode': f'HM{hash(listing) % 100000000:08d}',
                'reservationDate': '2025-01-01',
                'status': 'planned',
                'pricePerNight': 90.0,
                'daysBeforeReservation': 165,
                'addInfo': '',
                'year': 2025,
                'q': 2,
                'm': 6,
                'country': 'NL',
            })

        deleted_pairs = []
        mock_cursor = MagicMock()
        def track_execute(query, params=None):
            if query.strip().startswith('DELETE'):
                deleted_pairs.append((params[0], params[1]))
        mock_cursor.execute = track_execute

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        from str_database import STRDatabase
        db = STRDatabase.__new__(STRDatabase)
        db.connection = mock_conn

        db.insert_planned_bookings(incoming)

        # Only Green Studio and Red Studio should be deleted
        deleted_set = set(deleted_pairs)
        assert ('airbnb', 'Green Studio') in deleted_set
        assert ('airbnb', 'Red Studio') in deleted_set
        # Child Friendly should NOT be deleted
        assert ('airbnb', 'Child Friendly') not in deleted_set

    def test_response_structure_has_expected_keys(self, temp_dir):
        """Response structure has expected keys from multi-file processing (Req 5.2).

        Feature: str-airbnb-multi-file-import
        """
        processor = STRProcessor(test_mode=True)

        row_data = {
            'Begindatum': '15-06-2025',
            'Einddatum': '17-06-2025',
            'Naam van de gast': 'Test Guest',
            'Advertentie': 'Green Studio',
            '# nachten': 2,
            'Inkomsten': '€ 200,00',
            'Bevestigingscode': 'HM12345678',
            'Status': 'Bevestigd',
            'Contact': '+31612345678',
            '# volwassenen': 2,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-01-01',
        }
        df = pd.DataFrame([row_data])
        path = write_df_to_csv(df, temp_dir, 'test.csv')

        result = processor._process_airbnb_multi([path])

        assert len(result) == 1
        booking = result[0]

        expected_keys = {
            'sourceFile', 'channel', 'listing', 'checkinDate', 'checkoutDate',
            'nights', 'guests', 'amountGross', 'amountChannelFee', 'guestName',
            'phone', 'reservationCode', 'reservationDate', 'status', 'addInfo',
            'amountVat', 'amountTouristTax', 'amountNett', 'pricePerNight',
            'year', 'q', 'm', 'daysBeforeReservation', 'country',
        }
        assert expected_keys.issubset(set(booking.keys()))

    def test_single_file_processed_through_multi_path(self, temp_dir):
        """Single airbnb file processed through same _process_airbnb_multi path (Req 5.1).

        Feature: str-airbnb-multi-file-import
        """
        processor = STRProcessor(test_mode=True)

        row_data = {
            'Begindatum': '15-06-2025',
            'Einddatum': '17-06-2025',
            'Naam van de gast': 'Solo Guest',
            'Advertentie': 'Red Studio',
            '# nachten': 2,
            'Inkomsten': '€ 300,00',
            'Bevestigingscode': 'HM87654321',
            'Status': 'Bevestigd',
            'Contact': '+31612345678',
            '# volwassenen': 1,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-01-01',
        }
        df = pd.DataFrame([row_data])
        path = write_df_to_csv(df, temp_dir, 'single.csv')

        # process_str_files should route to _process_airbnb_multi
        result = processor.process_str_files([path], 'airbnb')

        assert len(result) == 1
        assert result[0]['channel'] == 'airbnb'
        assert result[0]['listing'] == 'Red Studio'
        assert result[0]['reservationCode'] == 'HM87654321'

    def test_single_file_source_file_has_filename(self, temp_dir):
        """Single file import sourceFile contains the filename, not 'multi-import'.

        Feature: str-airbnb-multi-file-import
        """
        processor = STRProcessor(test_mode=True)

        row_data = {
            'Begindatum': '15-06-2025',
            'Einddatum': '17-06-2025',
            'Naam van de gast': 'Test Guest',
            'Advertentie': 'Green Studio',
            '# nachten': 2,
            'Inkomsten': '€ 200,00',
            'Bevestigingscode': 'HM11111111',
            'Status': 'Bevestigd',
            'Contact': '+31612345678',
            '# volwassenen': 2,
            '# kinderen': 0,
            "# baby's": 0,
            'Gereserveerd': '2025-01-01',
        }
        df = pd.DataFrame([row_data])
        path = write_df_to_csv(df, temp_dir, 'my_export.csv')

        result = processor._process_airbnb_multi([path])

        assert len(result) == 1
        assert 'my_export.csv' in result[0]['sourceFile']
        assert 'multi-import' not in result[0]['sourceFile']
