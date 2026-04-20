"""
Property-based tests for TaxRateService.

Uses hypothesis to verify correctness properties from the design document.
Feature: parameter-driven-config

Requirements: 2.3, 2.4, 2.5, 2.6, 2.7, 8.3
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import json
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.tax_rate_service import TaxRateService, MAX_DATE


# ---------------------------------------------------------------------------
# Helpers: in-memory mock DB simulating tax_rates table
# ---------------------------------------------------------------------------

def make_tax_db(rows=None):
    """
    Mock DB backed by an in-memory list of tax_rate row dicts.
    Each row must have: id, administration, tax_type, tax_code, rate,
    ledger_account, effective_from, effective_to, description,
    calc_method, calc_params
    """
    store = list(rows or [])
    next_id = [max((r['id'] for r in store), default=0) + 1]

    def execute_query(query, params=None, fetch=True, commit=False, pool_type='primary'):
        sql = query.strip().upper()

        if sql.startswith('SELECT') and params and len(params) == 5:
            admin, ttype, tcode, d1, d2 = params
            matches = [
                r for r in store
                if r['administration'] == admin
                and r['tax_type'] == ttype
                and r['tax_code'] == tcode
                and r['effective_from'] <= d1
                and r['effective_to'] >= d2
            ]
            matches.sort(key=lambda r: r['effective_from'], reverse=True)
            return matches[:1] if matches else []

        if sql.startswith('SELECT') and params and len(params) == 4:
            admin, d1, d2, admin2 = params
            matches = [
                r for r in store
                if r['tax_type'] == 'btw'
                and r['administration'] in (admin, '_system_')
                and r['effective_from'] <= d1
                and r['effective_to'] >= d2
            ]
            matches.sort(key=lambda r: (
                r['tax_code'],
                0 if r['administration'] == admin else 1
            ))
            return matches

        if sql.startswith('INSERT') and commit:
            row_id = next_id[0]
            next_id[0] += 1
            (admin, ttype, tcode, rate, ledger, eff_from, eff_to,
             desc, calc_method, calc_params_json, created_by) = params
            store.append({
                'id': row_id, 'administration': admin,
                'tax_type': ttype, 'tax_code': tcode,
                'rate': rate, 'ledger_account': ledger,
                'effective_from': eff_from, 'effective_to': eff_to,
                'description': desc, 'calc_method': calc_method,
                'calc_params': calc_params_json,
            })
            return row_id

        if sql.startswith('UPDATE') and commit:
            close_day, admin, ttype, tcode, new_from, new_from2 = params
            for r in store:
                if (r['administration'] == admin
                        and r['tax_type'] == ttype
                        and r['tax_code'] == tcode
                        and r['effective_from'] <= new_from
                        and r['effective_to'] >= new_from2):
                    r['effective_to'] = close_day
            return None

        if sql.startswith('DELETE') and commit:
            rate_id, admin = params
            before = len(store)
            store[:] = [
                r for r in store
                if not (r['id'] == rate_id and r['administration'] == admin)
            ]
            return before - len(store)

        return []

    db = Mock()
    db.execute_query = Mock(side_effect=execute_query)
    db._store = store
    return db


# Strategies
date_st = st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31))
rate_st = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)
tax_code_st = st.sampled_from(['zero', 'low', 'high', 'standard'])


def make_row(row_id, admin, tax_type, tax_code, rate, eff_from, eff_to,
             ledger=None, desc=None, calc_method='percentage', calc_params=None):
    return {
        'id': row_id, 'administration': admin,
        'tax_type': tax_type, 'tax_code': tax_code,
        'rate': rate, 'ledger_account': ledger,
        'effective_from': eff_from, 'effective_to': eff_to,
        'description': desc, 'calc_method': calc_method,
        'calc_params': calc_params,
    }


# ---------------------------------------------------------------------------
# Property 4: Tax Rate Date-Filtered Resolution with Tenant Preference
# Feature: parameter-driven-config, Property 4: Tax Rate Date-Filtered Resolution
# Validates: Requirements 2.3, 2.4, 2.5, 2.6
# ---------------------------------------------------------------------------

class TestTaxRateDateFilteredResolution:
    """Tenant-specific rates preferred, system fallback works, None when no match."""

    @settings(max_examples=100)
    @given(
        ref_date=date_st,
        tenant_rate=st.one_of(st.none(), rate_st),
        system_rate=st.one_of(st.none(), rate_st),
    )
    def test_tenant_preferred_over_system(self, ref_date, tenant_rate, system_rate):
        rows = []
        base = date(2000, 1, 1)
        end = MAX_DATE

        if system_rate is not None:
            rows.append(make_row(1, '_system_', 'btw', 'high', system_rate, base, end))
        if tenant_rate is not None:
            rows.append(make_row(2, 'T1', 'btw', 'high', tenant_rate, base, end))

        db = make_tax_db(rows)
        svc = TaxRateService(db)
        result = svc.get_tax_rate('T1', 'btw', 'high', ref_date)

        if tenant_rate is not None:
            assert result is not None
            assert result['rate'] == tenant_rate
            assert result['scope_origin'] == 'tenant'
        elif system_rate is not None:
            assert result is not None
            assert result['rate'] == system_rate
            assert result['scope_origin'] == 'system'
        else:
            assert result is None

    @settings(max_examples=100)
    @given(
        ref_date=date_st,
        eff_from=date_st,
        eff_to=date_st,
    )
    def test_date_range_filtering(self, ref_date, eff_from, eff_to):
        assume(eff_from <= eff_to)
        rows = [make_row(1, '_system_', 'btw', 'low', 9.0, eff_from, eff_to)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)
        result = svc.get_tax_rate('T1', 'btw', 'low', ref_date)

        if eff_from <= ref_date <= eff_to:
            assert result is not None
            assert result['rate'] == 9.0
        else:
            assert result is None

    @settings(max_examples=50)
    @given(ref_date=date_st)
    def test_returns_none_when_no_rates(self, ref_date):
        db = make_tax_db([])
        svc = TaxRateService(db)
        assert svc.get_tax_rate('T1', 'btw', 'high', ref_date) is None


# ---------------------------------------------------------------------------
# Property 5: VAT Code Completeness for Date
# Feature: parameter-driven-config, Property 5: VAT Code Completeness for Date
# Validates: Requirements 2.7
# ---------------------------------------------------------------------------

class TestVATCodeCompleteness:
    """get_all_vat_codes returns matching entries, preferring tenant over system."""

    @settings(max_examples=100)
    @given(ref_date=date_st)
    def test_returns_all_active_codes(self, ref_date):
        base = date(2000, 1, 1)
        end = MAX_DATE
        rows = [
            make_row(1, '_system_', 'btw', 'zero', 0.0, base, end, '2010'),
            make_row(2, '_system_', 'btw', 'low', 9.0, base, end, '2021'),
            make_row(3, '_system_', 'btw', 'high', 21.0, base, end, '2020'),
        ]
        db = make_tax_db(rows)
        svc = TaxRateService(db)
        result = svc.get_all_vat_codes('T1', ref_date)

        codes = {r['code'] for r in result}
        assert codes == {'zero', 'low', 'high'}

    @settings(max_examples=100)
    @given(ref_date=date_st)
    def test_tenant_overrides_system_per_code(self, ref_date):
        base = date(2000, 1, 1)
        end = MAX_DATE
        rows = [
            make_row(1, '_system_', 'btw', 'high', 21.0, base, end, '2020'),
            make_row(2, 'T1', 'btw', 'high', 19.0, base, end, '2020'),
        ]
        db = make_tax_db(rows)
        svc = TaxRateService(db)
        result = svc.get_all_vat_codes('T1', ref_date)

        assert len(result) == 1
        assert result[0]['code'] == 'high'
        assert result[0]['rate'] == 19.0  # tenant rate wins

    @settings(max_examples=100)
    @given(
        ref_date=date_st,
        eff_from=date_st,
        eff_to=date_st,
    )
    def test_excludes_codes_outside_date_range(self, ref_date, eff_from, eff_to):
        assume(eff_from <= eff_to)
        rows = [make_row(1, '_system_', 'btw', 'low', 9.0, eff_from, eff_to)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)
        result = svc.get_all_vat_codes('T1', ref_date)

        if eff_from <= ref_date <= eff_to:
            assert len(result) == 1
        else:
            assert len(result) == 0


# ---------------------------------------------------------------------------
# Property 12: Tax Rate Auto-Close on Overlap
# Feature: parameter-driven-config, Property 12: Tax Rate Auto-Close on Overlap
# Validates: Requirements 8.3
# ---------------------------------------------------------------------------

class TestTaxRateAutoCloseOnOverlap:
    """Creating a new rate auto-closes overlapping existing rate."""

    @settings(max_examples=100)
    @given(
        existing_from=date_st,
        new_from=date_st,
    )
    def test_auto_close_sets_effective_to(self, existing_from, new_from):
        assume(existing_from < new_from)
        existing_to = MAX_DATE

        rows = [make_row(1, 'T1', 'btw', 'high', 21.0, existing_from, existing_to)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        svc.create_tax_rate('T1', 'btw', 'high', 25.0, new_from, description='New rate')

        # The existing rate should have been auto-closed
        existing = db._store[0]
        expected_close = new_from - timedelta(days=1)
        assert existing['effective_to'] == expected_close

        # The new rate should exist
        new_rate = db._store[1]
        assert new_rate['rate'] == 25.0
        assert new_rate['effective_from'] == new_from

    @settings(max_examples=50)
    @given(
        existing_from=date_st,
        new_from=date_st,
    )
    def test_no_auto_close_when_no_overlap(self, existing_from, new_from):
        """If existing rate ends before new rate starts, no auto-close."""
        assume(existing_from < new_from)
        existing_to = new_from - timedelta(days=1)
        assume(existing_from <= existing_to)

        rows = [make_row(1, 'T1', 'btw', 'high', 21.0, existing_from, existing_to)]
        db = make_tax_db(rows)
        svc = TaxRateService(db)

        svc.create_tax_rate('T1', 'btw', 'high', 25.0, new_from)

        # Existing rate should be unchanged
        existing = db._store[0]
        assert existing['effective_to'] == existing_to
