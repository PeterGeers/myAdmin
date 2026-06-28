"""
Budget Query Service

Handles read-only budget operations:
- Budget version listing
- Budget line listing
- Hierarchy rollup computation
- Dashboard budget vs actuals comparison
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Optional

from database import DatabaseManager


class BudgetQueryService:
    """Read-only service for budget queries and rollup computations.

    Tenant Isolation:
        Every public method requires an `administration` parameter as its first
        argument. All database queries include an `administration` filter,
        ensuring data is scoped to the requesting tenant.
    """

    def __init__(self, db: DatabaseManager) -> None:
        """
        Initialize BudgetQueryService.

        Args:
            db: Shared DatabaseManager instance.
        """
        self.db = db

    # -------------------------------------------------------------------------
    # Monetary Utilities (used by rollup calculations)
    # -------------------------------------------------------------------------

    @staticmethod
    def round_monetary(amount: Decimal) -> Decimal:
        """
        Round a monetary amount to 2 decimal places using banker's rounding.

        Args:
            amount: The decimal amount to round.

        Returns:
            The amount rounded to 2 decimal places.
        """
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)


    # -------------------------------------------------------------------------
    # Budget Version Queries
    # -------------------------------------------------------------------------

    def list_versions(
        self, administration: str, year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        List budget versions for a tenant, optionally filtered by fiscal year.

        Args:
            administration: Tenant identifier.
            year: Optional fiscal year filter.

        Returns:
            Dict with 'success' and 'data' (list of versions).

        Validates: Requirements 1.1, 8.2
        """
        if year is not None:
            query = """
                SELECT id, administration, name, fiscal_year, status, is_active,
                       status_changed_at, created_at, updated_at
                FROM budget_versions
                WHERE administration = %s AND fiscal_year = %s
                ORDER BY fiscal_year DESC, name ASC
            """
            params = (administration, year)
        else:
            query = """
                SELECT id, administration, name, fiscal_year, status, is_active,
                       status_changed_at, created_at, updated_at
                FROM budget_versions
                WHERE administration = %s
                ORDER BY fiscal_year DESC, name ASC
            """
            params = (administration,)

        results = self.db.execute_query(query, params)
        versions = results if results else []

        return {'success': True, 'data': versions}

    # -------------------------------------------------------------------------
    # Budget Line Queries
    # -------------------------------------------------------------------------

    def list_lines(
        self, administration: str, version_id: int
    ) -> Dict[str, Any]:
        """
        List all budget lines for a version.

        Args:
            administration: Tenant identifier.
            version_id: The budget version ID.

        Returns:
            Dict with 'success' and 'data' (list of line dicts).

        Validates: Requirements 3.4
        """
        results = self.db.execute_query(
            """
            SELECT id, version_id, administration, account_code, period_mode,
                   detail_dimension_type, detail_dimension_value,
                   month_01, month_02, month_03, month_04, month_05, month_06,
                   month_07, month_08, month_09, month_10, month_11, month_12,
                   created_at, updated_at
            FROM budget_lines
            WHERE version_id = %s AND administration = %s
            ORDER BY account_code, detail_dimension_type, detail_dimension_value
            """,
            (version_id, administration),
        )

        lines = results if results else []
        return {'success': True, 'data': lines}

    # -------------------------------------------------------------------------
    # Hierarchy Rollup
    # -------------------------------------------------------------------------

    @staticmethod
    def _sum_months(row: Dict[str, Any], months: Optional[List[int]] = None) -> Decimal:
        """
        Sum the specified months from a row dict containing m01..m12 keys.

        Args:
            row: Dict with keys 'm01' through 'm12' holding Decimal/numeric values.
            months: Optional list of month numbers (1-12) to include.
                    If None, sums all 12 months (full year).

        Returns:
            The summed total as a Decimal.

        Validates: Requirements 6.7, 7.1, 7.2
        """
        all_months = [
            Decimal(str(row.get(f'm{i:02d}', 0) or 0)) for i in range(1, 13)
        ]
        if months is None:
            return sum(all_months, Decimal('0.00'))
        return sum(
            (all_months[m - 1] for m in months if 1 <= m <= 12),
            Decimal('0.00'),
        )

    def get_rollup(
        self,
        administration: str,
        version_id: int,
        level: str,
        parent_code: Optional[str] = None,
        subparent_code: Optional[str] = None,
        months: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Compute hierarchy rollup for budget lines at the requested level.

        Joins budget_lines to rekeningschema at query time to use the live
        hierarchy. Aggregates at parent, subparent, or account level.

        Args:
            administration: Tenant identifier.
            version_id: The budget version to aggregate.
            level: Aggregation level — 'parent', 'subparent', or 'account'.
            parent_code: Required filter when level='subparent'.
            subparent_code: Required filter when level='account'.
            months: Optional list of month numbers (1-12) to sum.
                    If None, sums all 12 months (full year).

        Returns:
            Dict with 'success' and 'data' (list of rollup rows) or 'error'.

        Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
        """
        valid_levels = ('parent', 'subparent', 'account')
        if level not in valid_levels:
            return {
                'success': False,
                'error': f"Invalid level '{level}'. Use: parent, subparent, account",
            }

        if level == 'subparent' and not parent_code:
            return {
                'success': False,
                'error': "parent_code is required when level is 'subparent'",
            }

        if level == 'account' and not subparent_code:
            return {
                'success': False,
                'error': "subparent_code is required when level is 'account'",
            }

        month_cols = ', '.join(
            f'SUM(bl.month_{i:02d}) AS m{i:02d}' for i in range(1, 13)
        )

        if level == 'parent':
            query = f"""
                SELECT r.Parent AS code,
                       {month_cols}
                FROM budget_lines bl
                JOIN rekeningschema r
                    ON r.Account = bl.account_code COLLATE utf8mb4_unicode_ci
                    AND r.administration = bl.administration COLLATE utf8mb4_unicode_ci
                WHERE bl.version_id = %s AND bl.administration = %s
                GROUP BY r.Parent
            """
            params: tuple = (version_id, administration)

        elif level == 'subparent':
            query = f"""
                SELECT r.SubParent AS code, MAX(r.Parent) AS parent_code,
                       {month_cols}
                FROM budget_lines bl
                JOIN rekeningschema r
                    ON r.Account = bl.account_code COLLATE utf8mb4_unicode_ci
                    AND r.administration = bl.administration COLLATE utf8mb4_unicode_ci
                WHERE bl.version_id = %s AND bl.administration = %s AND r.Parent = %s
                GROUP BY r.SubParent
            """
            params = (version_id, administration, parent_code)

        else:  # level == 'account'
            # At account level we don't aggregate — return individual lines
            month_cols_individual = ', '.join(
                f'bl.month_{i:02d} AS m{i:02d}' for i in range(1, 13)
            )
            query = f"""
                SELECT bl.account_code AS code, r.SubParent AS subparent_code,
                       r.AccountName AS name,
                       {month_cols_individual}
                FROM budget_lines bl
                JOIN rekeningschema r
                    ON r.Account = bl.account_code COLLATE utf8mb4_unicode_ci
                    AND r.administration = bl.administration COLLATE utf8mb4_unicode_ci
                WHERE bl.version_id = %s AND bl.administration = %s AND r.SubParent = %s
            """
            params = (version_id, administration, subparent_code)

        rows = self.db.execute_query(query, params)
        rows = rows if rows else []

        # Build result data with period totals
        data: List[Dict[str, Any]] = []

        for row in rows:
            code = row.get('code') or ''
            budget_total = self._sum_months(row, months)

            entry: Dict[str, Any] = {
                'code': code if code else 'Unassigned',
                'name': row.get('name', ''),
                'budget': float(self.round_monetary(budget_total)),
            }

            # Include hierarchy references when available
            if level == 'subparent':
                entry['parent_code'] = row.get('parent_code', '')
                # Handle NULL SubParent → "Unassigned"
                if not code:
                    entry['code'] = 'Unassigned'
            elif level == 'account':
                entry['subparent_code'] = row.get('subparent_code', '')

            data.append(entry)

        # For parent and subparent levels, resolve names via secondary query
        if level in ('parent', 'subparent') and data:
            codes_to_resolve = [d['code'] for d in data if d['code'] != 'Unassigned']
            if codes_to_resolve:
                placeholders = ', '.join(['%s'] * len(codes_to_resolve))
                name_query = f"""
                    SELECT DISTINCT Account, AccountName
                    FROM rekeningschema
                    WHERE administration = %s AND Account IN ({placeholders})
                """
                name_params = (administration, *codes_to_resolve)
                name_rows = self.db.execute_query(name_query, name_params)
                name_map: Dict[str, str] = {}
                if name_rows:
                    for nr in name_rows:
                        name_map[nr['Account']] = nr.get('AccountName', '')

                for entry in data:
                    if entry['code'] != 'Unassigned' and entry['code'] in name_map:
                        entry['name'] = name_map[entry['code']]

        # Ensure "Unassigned" entries have a name
        for entry in data:
            if entry['code'] == 'Unassigned':
                entry['name'] = 'Unassigned'

        return {'success': True, 'data': data}


    # -------------------------------------------------------------------------
    # Dashboard
    # -------------------------------------------------------------------------

    def _parse_period(self, period: str) -> List[int]:
        """
        Convert a period string to a list of month numbers (1-12).

        Supported formats:
        - 'month-1' through 'month-12' → single month
        - 'q1'–'q4' → quarter months
        - 'ytd' → month 1 through current calendar month
        - 'full' → all 12 months

        Args:
            period: The period string to parse.

        Returns:
            List of month numbers included in the period.

        Validates: Requirements 6.7
        """
        if period and period.startswith('month-'):
            try:
                month_num = int(period.split('-')[1])
                if 1 <= month_num <= 12:
                    return [month_num]
            except (ValueError, IndexError):
                pass
            return list(range(1, 13))

        quarters = {'q1': [1, 2, 3], 'q2': [4, 5, 6], 'q3': [7, 8, 9], 'q4': [10, 11, 12]}
        if period in quarters:
            return quarters[period]

        if period == 'ytd':
            return list(range(1, datetime.now().month + 1))

        # 'full' or unrecognized defaults to full year
        return list(range(1, 13))

    def get_dashboard(
        self,
        administration: str,
        level: str,
        period: str,
        version_id: Optional[int] = None,
        year: Optional[int] = None,
        parent_code: Optional[str] = None,
        subparent_code: Optional[str] = None,
        reference_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dashboard budget vs actuals comparison.

        Accepts either a version_id (preferred) or a year for backward compatibility.
        When version_id is provided, looks up that specific version.
        When year is provided, finds the first active version for that year.

        Args:
            administration: Tenant identifier.
            level: Aggregation level — 'parent', 'subparent', or 'account'.
            period: Period filter — 'month-N', 'q1'–'q4', 'ytd', or 'full'.
            version_id: Specific budget version ID (preferred).
            year: Fiscal year for comparison (legacy, used if version_id not given).
            parent_code: Filter to a specific parent (for drill-down).
            subparent_code: Filter to a specific subparent (for drill-down).
            reference_number: Optional ReferenceNumber filter for both budget and actuals.

        Returns:
            Dict with 'success' and 'data' containing year, level, period,
            active_version, and rows with budget/actual/variance per code.
        """
        # Default period to 'ytd' if not specified
        if not period:
            period = 'ytd'

        month_list = self._parse_period(period)

        # 1. Resolve version: by version_id or by year lookup
        if version_id:
            version_results = self.db.execute_query(
                """
                SELECT id, name, fiscal_year FROM budget_versions
                WHERE id = %s AND administration = %s
                """,
                (version_id, administration),
            )
            if not version_results:
                return {'success': False, 'error': "Budget version not found"}
            active_version = version_results[0]
            resolved_year = active_version['fiscal_year']
        elif year:
            version_results = self.db.execute_query(
                """
                SELECT id, name, fiscal_year FROM budget_versions
                WHERE administration = %s AND fiscal_year = %s AND is_active = TRUE
                LIMIT 1
                """,
                (administration, year),
            )
            if not version_results:
                return {
                    'success': True,
                    'data': {
                        'year': year,
                        'level': level,
                        'period': period,
                        'active_version': None,
                        'rows': [],
                        'notification': f"No active budget version for {year}",
                    },
                }
            active_version = version_results[0]
            resolved_year = year
        else:
            return {'success': False, 'error': "Either version_id or year is required"}

        vid = active_version['id']
        version_name = active_version['name']

        # 2. Get budget rollup
        budget_map: Dict[str, float] = {}

        if reference_number:
            # When filtering by reference_number, query budget_lines filtered by
            # detail_dimension_value where detail_dimension_type='ReferenceNumber'
            budget_data = self._get_budget_rollup_filtered(
                administration, vid, level, parent_code, subparent_code,
                month_list, reference_number
            )
        else:
            rollup_result = self.get_rollup(
                administration, vid, level, parent_code, subparent_code, month_list
            )
            if rollup_result['success']:
                for row in rollup_result['data']:
                    budget_map[row['code']] = row['budget']
            budget_data = None

        if budget_data is not None:
            budget_map = budget_data

        # 3. Get actuals rollup from vw_mutaties
        actuals_map = self._get_actuals_rollup(
            administration, resolved_year, level, parent_code, subparent_code,
            month_list, reference_number
        )

        # 4. Resolve names for all codes
        all_codes = set(budget_map.keys()) | set(actuals_map.keys())
        all_codes.discard('Unassigned')
        name_map = self._resolve_names(administration, list(all_codes))

        # 5. Merge budget and actuals
        rows: List[Dict[str, Any]] = []
        for code in sorted(all_codes | {'Unassigned'} if 'Unassigned' in (set(budget_map.keys()) | set(actuals_map.keys())) else sorted(all_codes)):
            budget_val = budget_map.get(code, 0.0)
            actual_val = actuals_map.get(code, 0.0)
            variance = round(actual_val - budget_val, 2)

            rows.append({
                'code': code,
                'name': name_map.get(code, 'Unassigned' if code == 'Unassigned' else ''),
                'budget': budget_val,
                'actual': actual_val,
                'variance': variance,
            })

        return {
            'success': True,
            'data': {
                'year': resolved_year,
                'level': level,
                'period': period,
                'active_version': {'id': vid, 'name': version_name},
                'rows': rows,
            },
        }

    # -------------------------------------------------------------------------
    # Private Query Helpers
    # -------------------------------------------------------------------------

    def _get_budget_rollup_filtered(
        self,
        administration: str,
        version_id: int,
        level: str,
        parent_code: Optional[str],
        subparent_code: Optional[str],
        months: List[int],
        reference_number: str,
    ) -> Dict[str, float]:
        """
        Get budget rollup filtered by reference_number (detail_dimension_value).

        Only includes budget_lines where detail_dimension_type='ReferenceNumber'
        and detail_dimension_value matches the given reference_number.

        Args:
            administration: Tenant identifier.
            version_id: Budget version ID.
            level: Aggregation level.
            parent_code: Parent filter for subparent level.
            subparent_code: SubParent filter for account level.
            months: List of month numbers to sum.
            reference_number: The ReferenceNumber to filter on.

        Returns:
            Dict mapping code to budget total (float).
        """
        month_cols = ', '.join(
            f'SUM(bl.month_{i:02d}) AS m{i:02d}' for i in range(1, 13)
        )

        if level == 'parent':
            query = f"""
                SELECT r.Parent AS code,
                       {month_cols}
                FROM budget_lines bl
                JOIN rekeningschema r
                    ON r.Account = bl.account_code COLLATE utf8mb4_unicode_ci
                    AND r.administration = bl.administration COLLATE utf8mb4_unicode_ci
                WHERE bl.version_id = %s AND bl.administration = %s
                  AND bl.detail_dimension_type = 'ReferenceNumber'
                  AND bl.detail_dimension_value = %s
                GROUP BY r.Parent
            """
            params: tuple = (version_id, administration, reference_number)

        elif level == 'subparent':
            query = f"""
                SELECT r.SubParent AS code,
                       {month_cols}
                FROM budget_lines bl
                JOIN rekeningschema r
                    ON r.Account = bl.account_code COLLATE utf8mb4_unicode_ci
                    AND r.administration = bl.administration COLLATE utf8mb4_unicode_ci
                WHERE bl.version_id = %s AND bl.administration = %s AND r.Parent = %s
                  AND bl.detail_dimension_type = 'ReferenceNumber'
                  AND bl.detail_dimension_value = %s
                GROUP BY r.SubParent
            """
            params = (version_id, administration, parent_code, reference_number)

        else:  # account
            month_cols_individual = ', '.join(
                f'bl.month_{i:02d} AS m{i:02d}' for i in range(1, 13)
            )
            query = f"""
                SELECT bl.account_code AS code,
                       {month_cols_individual}
                FROM budget_lines bl
                JOIN rekeningschema r
                    ON r.Account = bl.account_code COLLATE utf8mb4_unicode_ci
                    AND r.administration = bl.administration COLLATE utf8mb4_unicode_ci
                WHERE bl.version_id = %s AND bl.administration = %s AND r.SubParent = %s
                  AND bl.detail_dimension_type = 'ReferenceNumber'
                  AND bl.detail_dimension_value = %s
            """
            params = (version_id, administration, subparent_code, reference_number)

        rows = self.db.execute_query(query, params)
        rows = rows if rows else []

        budget_map: Dict[str, float] = {}
        for row in rows:
            code = row.get('code') or 'Unassigned'
            total = self._sum_months(row, months)
            budget_map[code] = float(self.round_monetary(total))

        return budget_map

    def _get_actuals_rollup(
        self,
        administration: str,
        year: int,
        level: str,
        parent_code: Optional[str],
        subparent_code: Optional[str],
        months: List[int],
        reference_number: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Get actuals rollup from vw_mutaties grouped by hierarchy level.

        Args:
            administration: Tenant identifier.
            year: Fiscal year.
            level: Aggregation level — 'parent', 'subparent', or 'account'.
            parent_code: Parent filter for subparent level.
            subparent_code: SubParent filter for account level.
            months: List of month numbers to include.
            reference_number: Optional ReferenceNumber filter.

        Returns:
            Dict mapping code to actual total (float).
        """
        placeholders = ', '.join(['%s'] * len(months))

        if level == 'parent':
            query = f"""
                SELECT r.Parent AS code, SUM(vm.Amount) AS actual
                FROM vw_mutaties vm
                JOIN rekeningschema r
                    ON r.Account = vm.Reknum COLLATE utf8mb4_unicode_ci
                    AND r.administration = vm.administration COLLATE utf8mb4_unicode_ci
                WHERE vm.administration = %s AND vm.jaar = %s
                  AND vm.maand IN ({placeholders})
            """
            params_list: list = [administration, year, *months]

        elif level == 'subparent':
            query = f"""
                SELECT r.SubParent AS code, SUM(vm.Amount) AS actual
                FROM vw_mutaties vm
                JOIN rekeningschema r
                    ON r.Account = vm.Reknum COLLATE utf8mb4_unicode_ci
                    AND r.administration = vm.administration COLLATE utf8mb4_unicode_ci
                WHERE vm.administration = %s AND vm.jaar = %s
                  AND vm.maand IN ({placeholders})
                  AND r.Parent = %s
            """
            params_list = [administration, year, *months, parent_code]

        else:  # account
            query = f"""
                SELECT vm.Reknum AS code, SUM(vm.Amount) AS actual
                FROM vw_mutaties vm
                JOIN rekeningschema r
                    ON r.Account = vm.Reknum COLLATE utf8mb4_unicode_ci
                    AND r.administration = vm.administration COLLATE utf8mb4_unicode_ci
                WHERE vm.administration = %s AND vm.jaar = %s
                  AND vm.maand IN ({placeholders})
                  AND r.SubParent = %s
            """
            params_list = [administration, year, *months, subparent_code]

        if reference_number:
            query += "  AND vm.ReferenceNumber = %s"
            params_list.append(reference_number)

        if level == 'parent':
            query += "\n                GROUP BY r.Parent"
        elif level == 'subparent':
            query += "\n                GROUP BY r.SubParent"
        else:
            query += "\n                GROUP BY vm.Reknum"

        rows = self.db.execute_query(query, tuple(params_list))
        rows = rows if rows else []

        actuals_map: Dict[str, float] = {}
        for row in rows:
            code = row.get('code') or 'Unassigned'
            actual = Decimal(str(row.get('actual', 0) or 0))
            actuals_map[code] = float(self.round_monetary(actual))

        return actuals_map

    def _resolve_names(
        self, administration: str, codes: List[str]
    ) -> Dict[str, str]:
        """
        Resolve account/parent/subparent codes to names via rekeningschema.

        Args:
            administration: Tenant identifier.
            codes: List of codes to resolve.

        Returns:
            Dict mapping code to AccountName.
        """
        if not codes:
            return {}

        placeholders = ', '.join(['%s'] * len(codes))
        name_query = f"""
            SELECT DISTINCT Account, AccountName
            FROM rekeningschema
            WHERE administration = %s AND Account IN ({placeholders})
        """
        name_rows = self.db.execute_query(name_query, (administration, *codes))

        name_map: Dict[str, str] = {}
        if name_rows:
            for nr in name_rows:
                name_map[nr['Account']] = nr.get('AccountName', '')

        return name_map
