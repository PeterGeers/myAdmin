"""
Budget Service

Handles budget management business logic including:
- Budget version CRUD and status transitions
- Budget line entry with monthly/annual modes
- Annual amount division with banker's rounding
- Budget copy between fiscal years
- Hierarchy rollup computation
- Dashboard budget vs actuals comparison
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Optional

from database import DatabaseManager
from db_exceptions import DatabaseError, IntegrityError


class BudgetService:
    """Service class for budget management operations.

    Tenant Isolation:
        Every public method requires an `administration` parameter as its first
        argument. This value originates from the @tenant_required() decorator in
        budget_routes.py and represents the authenticated user's current tenant.

        All database queries (SELECT, INSERT, UPDATE, DELETE) include an
        `administration` filter, ensuring data is scoped to the requesting tenant.
        This applies to budget_versions, budget_lines, and all JOIN queries
        against rekeningschema and vw_mutaties.
    """

    def __init__(self, test_mode: bool = False) -> None:
        """
        Initialize BudgetService.

        Args:
            test_mode: Whether to run in test mode (uses test database).
        """
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)

    # -------------------------------------------------------------------------
    # Monetary Utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def round_monetary(amount: Decimal) -> Decimal:
        """
        Round a monetary amount to 2 decimal places using banker's rounding.

        Banker's rounding (ROUND_HALF_EVEN) rounds to the nearest even digit
        when the value is exactly halfway between two possibilities. This
        reduces cumulative rounding bias in financial calculations.

        Args:
            amount: The decimal amount to round.

        Returns:
            The amount rounded to 2 decimal places.

        Validates: Requirements 3.5, 6.9
        """
        return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)

    @staticmethod
    def divide_annual(annual_amount: Decimal, months: int = 12) -> List[Decimal]:
        """
        Divide an annual amount into equal monthly amounts with banker's rounding.

        The last month absorbs any rounding remainder so that the sum of all
        monthly amounts exactly equals the original annual amount.

        Args:
            annual_amount: The total annual amount to divide.
            months: Number of months to divide into (default 12).

        Returns:
            List of monthly Decimal amounts whose sum equals annual_amount.

        Validates: Requirements 2.3, 3.2
        """
        monthly = (annual_amount / months).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_EVEN
        )
        amounts = [monthly] * months
        # Adjust last month for rounding remainder
        remainder = annual_amount - sum(amounts)
        amounts[-1] += remainder
        return amounts

    # -------------------------------------------------------------------------
    # Budget Version Management
    # -------------------------------------------------------------------------

    def create_version(
        self, administration: str, name: str, fiscal_year: int
    ) -> Dict[str, Any]:
        """
        Create a new budget version with status Draft.

        Args:
            administration: Tenant identifier.
            name: Version name (1–100 characters).
            fiscal_year: 4-digit fiscal year.

        Returns:
            Dict with 'success' and 'data' (the created version) or 'error'.

        Validates: Requirements 1.1, 1.2, 8.2
        """
        try:
            version_id = self.db.execute_query(
                """
                INSERT INTO budget_versions (administration, name, fiscal_year, status, is_active)
                VALUES (%s, %s, %s, 'Draft', FALSE)
                """,
                (administration, name, fiscal_year),
                fetch=False,
                commit=True,
            )
        except IntegrityError:
            return {
                'success': False,
                'error': f"Budget version '{name}' already exists for fiscal year {fiscal_year}",
            }

        return {
            'success': True,
            'data': {
                'id': version_id,
                'name': name,
                'fiscal_year': fiscal_year,
                'status': 'Draft',
                'is_active': False,
            },
        }

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

    def delete_version(
        self, administration: str, version_id: int
    ) -> Dict[str, Any]:
        """
        Delete a budget version. Only Draft versions can be deleted.

        Args:
            administration: Tenant identifier.
            version_id: ID of the version to delete.

        Returns:
            Dict with 'success' or 'error'.

        Validates: Requirements 1.1, 8.2
        """
        # Fetch the version to check it exists and belongs to tenant
        results = self.db.execute_query(
            """
            SELECT id, status FROM budget_versions
            WHERE id = %s AND administration = %s
            """,
            (version_id, administration),
        )

        if not results:
            # Defense-in-depth: returns "not found" for cross-tenant access attempts
            # rather than 403, so we don't reveal existence of other tenants' resources.
            return {'success': False, 'error': "Budget version not found"}

        version = results[0]

        if version['status'] != 'Draft':
            return {'success': False, 'error': "Only Draft versions can be deleted"}

        self.db.execute_query(
            "DELETE FROM budget_versions WHERE id = %s AND administration = %s",
            (version_id, administration),
            fetch=False,
            commit=True,
        )

        return {'success': True, 'data': {'id': version_id}}

    def transition_status(
        self, administration: str, version_id: int, action: str
    ) -> Dict[str, Any]:
        """
        Transition a budget version's status following the Draft→Approved→Revised sequence.

        Valid transitions:
        - action='approve': Draft → Approved
        - action='revise': Approved → Revised (creates a copy with all budget lines)

        For 'revise', the original Approved version is preserved unchanged and a new
        Revised version is created with all budget lines copied over.

        Args:
            administration: Tenant identifier for isolation.
            version_id: The ID of the budget version to transition.
            action: The transition action ('approve' or 'revise').

        Returns:
            Dict with 'success' key and either 'data' (version info) or 'error' message.

        Validates: Requirements 1.3, 1.4, 1.5
        """
        # Validate action
        valid_actions = ('approve', 'revise')
        if action not in valid_actions:
            return {
                'success': False,
                'error': "Invalid action. Use 'approve' or 'revise'"
            }

        # Fetch current version (tenant-isolated)
        query = """
            SELECT id, name, fiscal_year, status, is_active, status_changed_at,
                   created_at, updated_at
            FROM budget_versions
            WHERE id = %s AND administration = %s
        """
        result = self.db.execute_query(query, (version_id, administration))

        if not result:
            return {'success': False, 'error': "Budget version not found"}

        version = result[0]
        current_status = version['status']

        # Define allowed transitions
        allowed_transitions = {
            'Draft': 'Approved',
            'Approved': 'Revised',
        }

        # Determine target status from action
        action_to_target = {
            'approve': 'Approved',
            'revise': 'Revised',
        }
        target_status = action_to_target[action]

        # Validate the transition is allowed from current status
        allowed_target = allowed_transitions.get(current_status)
        if allowed_target != target_status:
            allowed_msg = allowed_target if allowed_target else "none"
            return {
                'success': False,
                'error': (
                    f"Cannot transition from {current_status} to {target_status}. "
                    f"Allowed: {allowed_msg}"
                )
            }

        now = datetime.now()

        if action == 'approve':
            # Simple status update: Draft → Approved
            update_query = """
                UPDATE budget_versions
                SET status = %s, status_changed_at = %s
                WHERE id = %s AND administration = %s
            """
            self.db.execute_query(
                update_query,
                (target_status, now, version_id, administration),
                fetch=False, commit=True
            )
            return {
                'success': True,
                'data': {
                    'id': version_id,
                    'name': version['name'],
                    'fiscal_year': version['fiscal_year'],
                    'status': target_status,
                    'is_active': version['is_active'],
                    'status_changed_at': now.isoformat()
                }
            }

        # action == 'revise': create a copy of the Approved version
        revised_name = f"{version['name']} (Revised)"

        # Check if that name already exists, and if so, append a counter
        existing = self.db.execute_query(
            """
            SELECT COUNT(*) as cnt FROM budget_versions
            WHERE administration = %s AND fiscal_year = %s AND name LIKE %s
            """,
            (administration, version['fiscal_year'], f"{version['name']} (Revised%"),
        )
        if existing and existing[0]['cnt'] > 0:
            count = existing[0]['cnt'] + 1
            revised_name = f"{version['name']} (Revised {count})"

        with self.db.transaction() as (cursor, conn):
            insert_version_query = """
                INSERT INTO budget_versions
                    (administration, name, fiscal_year, status, is_active, status_changed_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                insert_version_query,
                (administration, revised_name, version['fiscal_year'],
                 'Revised', False, now)
            )
            new_version_id = cursor.lastrowid

            # Copy all budget lines from the original version to the new version
            copy_lines_query = """
                INSERT INTO budget_lines
                    (version_id, administration, account_code, period_mode,
                     detail_dimension_type, detail_dimension_value,
                     month_01, month_02, month_03, month_04, month_05, month_06,
                     month_07, month_08, month_09, month_10, month_11, month_12)
                SELECT %s, administration, account_code, period_mode,
                       detail_dimension_type, detail_dimension_value,
                       month_01, month_02, month_03, month_04, month_05, month_06,
                       month_07, month_08, month_09, month_10, month_11, month_12
                FROM budget_lines
                WHERE version_id = %s AND administration = %s
            """
            cursor.execute(
                copy_lines_query,
                (new_version_id, version_id, administration)
            )

        return {
            'success': True,
            'data': {
                'id': new_version_id,
                'name': revised_name,
                'fiscal_year': version['fiscal_year'],
                'status': 'Revised',
                'is_active': False,
                'status_changed_at': now.isoformat()
            }
        }

    def activate_version(
        self, administration: str, version_id: int, active: bool = True
    ) -> Dict[str, Any]:
        """
        Toggle the active flag on a budget version.

        Multiple versions can be active simultaneously (e.g. for dashboard comparison).
        Only versions with status Approved or Revised may be activated.

        Args:
            administration: Tenant identifier.
            version_id: ID of the version to toggle.
            active: True to activate, False to deactivate.

        Returns:
            Dict with 'success' and 'data' (updated version) or 'error'.
        """
        # Fetch the version to validate existence, tenant ownership, and status
        results = self.db.execute_query(
            """
            SELECT id, name, fiscal_year, status, is_active
            FROM budget_versions
            WHERE id = %s AND administration = %s
            """,
            (version_id, administration),
        )

        if not results:
            return {'success': False, 'error': "Budget version not found"}

        version = results[0]

        if active and version['status'] not in ('Approved', 'Revised'):
            return {
                'success': False,
                'error': "Only Approved or Revised versions may be activated",
            }

        # Simply set the is_active flag — no deactivation of other versions
        self.db.execute_query(
            """
            UPDATE budget_versions
            SET is_active = %s
            WHERE id = %s AND administration = %s
            """,
            (active, version_id, administration),
            fetch=False,
            commit=True,
        )

        return {
            'success': True,
            'data': {
                'id': version['id'],
                'name': version['name'],
                'fiscal_year': version['fiscal_year'],
                'status': version['status'],
                'is_active': active,
            },
        }

    # -------------------------------------------------------------------------
    # Budget Line Entry
    # -------------------------------------------------------------------------

    def create_line(
        self,
        administration: str,
        version_id: int,
        account_code: str,
        period_mode: str,
        amounts: Optional[List[float]] = None,
        annual_amount: Optional[float] = None,
        detail_dimension_type: Optional[str] = None,
        detail_dimension_value: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new budget line for a version.

        Args:
            administration: Tenant identifier.
            version_id: The budget version to add the line to.
            account_code: Ledger account code.
            period_mode: 'Monthly' or 'Annual'.
            amounts: List of 12 monthly amounts (required for Monthly mode).
            annual_amount: Single annual amount (required for Annual mode).
            detail_dimension_type: Optional dimension type ('platform' or 'ReferenceNumber').
            detail_dimension_value: Optional dimension value.
            notes: Optional notes (e.g. AI reasoning).

        Returns:
            Dict with 'success' and 'data' or 'error'.
        """
        # Compute 12 monthly amounts based on period_mode
        if period_mode == 'Monthly':
            if amounts is None or len(amounts) != 12:
                return {'success': False, 'error': "Monthly mode requires exactly 12 amounts"}
            monthly_amounts = [
                self.round_monetary(Decimal(str(a))) for a in amounts
            ]
        elif period_mode == 'Annual':
            if annual_amount is None:
                return {'success': False, 'error': "Annual mode requires an annual_amount"}
            monthly_amounts = self.divide_annual(Decimal(str(annual_amount)))
        else:
            return {'success': False, 'error': "Invalid period_mode. Use 'Monthly' or 'Annual'"}

        # Build dimension description for error messages
        dim_desc = f"{detail_dimension_type}={detail_dimension_value}" if detail_dimension_type else "none"

        try:
            line_id = self.db.execute_query(
                """
                INSERT INTO budget_lines
                    (version_id, administration, account_code, period_mode,
                     detail_dimension_type, detail_dimension_value, notes,
                     month_01, month_02, month_03, month_04, month_05, month_06,
                     month_07, month_08, month_09, month_10, month_11, month_12)
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id, administration, account_code, period_mode,
                    detail_dimension_type, detail_dimension_value, notes,
                    *monthly_amounts,
                ),
                fetch=False,
                commit=True,
            )
        except IntegrityError:
            return {
                'success': False,
                'error': f"Budget line already exists for account {account_code} with dimension {dim_desc}",
            }

        total = sum(monthly_amounts)
        return {
            'success': True,
            'data': {
                'id': line_id,
                'account_code': account_code,
                'total': float(total),
            },
        }

    def update_line(
        self,
        administration: str,
        line_id: int,
        amounts: Optional[List[float]] = None,
        annual_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Update a budget line's monthly amounts.

        Args:
            administration: Tenant identifier.
            line_id: The budget line ID.
            amounts: List of 12 monthly amounts (for Monthly update).
            annual_amount: Single annual amount (for Annual update).

        Returns:
            Dict with 'success' and 'data' or 'error'.

        Validates: Requirements 3.1, 3.2, 3.5
        """
        # Fetch existing line with tenant check
        results = self.db.execute_query(
            """
            SELECT id, version_id, account_code, period_mode
            FROM budget_lines
            WHERE id = %s AND administration = %s
            """,
            (line_id, administration),
        )

        if not results:
            return {'success': False, 'error': "Budget line not found"}

        line = results[0]

        # Compute new monthly amounts
        if amounts is not None:
            if len(amounts) != 12:
                return {'success': False, 'error': "Monthly mode requires exactly 12 amounts"}
            monthly_amounts = [
                self.round_monetary(Decimal(str(a))) for a in amounts
            ]
        elif annual_amount is not None:
            monthly_amounts = self.divide_annual(Decimal(str(annual_amount)))
        else:
            return {'success': False, 'error': "Provide either amounts (12 values) or annual_amount"}

        self.db.execute_query(
            """
            UPDATE budget_lines
            SET month_01 = %s, month_02 = %s, month_03 = %s, month_04 = %s,
                month_05 = %s, month_06 = %s, month_07 = %s, month_08 = %s,
                month_09 = %s, month_10 = %s, month_11 = %s, month_12 = %s
            WHERE id = %s AND administration = %s
            """,
            (*monthly_amounts, line_id, administration),
            fetch=False,
            commit=True,
        )

        total = sum(monthly_amounts)
        return {
            'success': True,
            'data': {
                'id': line_id,
                'account_code': line['account_code'],
                'total': float(total),
            },
        }

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

    def delete_line(
        self, administration: str, line_id: int
    ) -> Dict[str, Any]:
        """
        Delete a budget line.

        Args:
            administration: Tenant identifier.
            line_id: The budget line ID to delete.

        Returns:
            Dict with 'success' and 'data' or 'error'.

        Validates: Requirements 3.4
        """
        # Verify line exists and belongs to tenant
        results = self.db.execute_query(
            """
            SELECT id FROM budget_lines
            WHERE id = %s AND administration = %s
            """,
            (line_id, administration),
        )

        if not results:
            return {'success': False, 'error': "Budget line not found"}

        self.db.execute_query(
            "DELETE FROM budget_lines WHERE id = %s AND administration = %s",
            (line_id, administration),
            fetch=False,
            commit=True,
        )

        return {'success': True, 'data': {'id': line_id, 'deleted': True}}

    # -------------------------------------------------------------------------
    # Annualization Utility
    # -------------------------------------------------------------------------

    def _compute_monthly_amounts(
        self, monthly_actuals: Dict[int, Decimal]
    ) -> List[Decimal]:
        """
        Compute 12 monthly budget amounts from prior-year actuals.

        - If 12 months of data: use actual amounts directly
        - If 1-11 months: annualize (total × 12 / N) and distribute equally
        - If 0 months: return 12 zeros

        Args:
            monthly_actuals: Dict mapping month number (1-12) to actual amount.

        Returns:
            List of 12 Decimal amounts.
        """
        months_with_data = len(monthly_actuals)

        if months_with_data == 0:
            return [Decimal('0.00')] * 12

        if months_with_data == 12:
            # Use actual monthly amounts directly
            return [
                self.round_monetary(monthly_actuals.get(m, Decimal('0.00')))
                for m in range(1, 13)
            ]

        # Partial year: annualize and distribute equally
        sum_of_actuals = sum(monthly_actuals.values())
        annualized_total = self.round_monetary(
            Decimal(str(sum_of_actuals)) * 12 / months_with_data
        )
        return self.divide_annual(annualized_total)

    # -------------------------------------------------------------------------
    # Copy Budget
    # -------------------------------------------------------------------------

    def copy_budget(
        self,
        administration: str,
        source_version_id: int,
        target_fiscal_year: int,
        version_name: str,
    ) -> Dict[str, Any]:
        """
        Copy a budget version to a new fiscal year.

        Creates a new Draft version with the provided name and copies all budget
        lines from the source, preserving monthly amounts, period modes, and
        dimension associations. Lines referencing accounts that no longer exist
        in the tenant's chart of accounts are excluded, and warnings are returned.

        Args:
            administration: Tenant identifier.
            source_version_id: ID of the source budget version to copy from.
            target_fiscal_year: The fiscal year for the new version (must be > source year).
            version_name: Name for the new budget version.

        Returns:
            Dict with 'success' and 'data' containing version_id, lines_copied,
            and excluded_accounts, or 'error' on failure.

        Validates: Requirements 5.1, 5.2, 5.3, 5.4, 8.5
        """
        # 1. Fetch source version (tenant-isolated)
        results = self.db.execute_query(
            """
            SELECT id, name, fiscal_year, status
            FROM budget_versions
            WHERE id = %s AND administration = %s
            """,
            (source_version_id, administration),
        )

        if not results:
            return {'success': False, 'error': "Budget version not found"}

        source_version = results[0]

        # 3. Get all budget lines for the source version
        source_lines = self.db.execute_query(
            """
            SELECT account_code, period_mode,
                   detail_dimension_type, detail_dimension_value,
                   month_01, month_02, month_03, month_04, month_05, month_06,
                   month_07, month_08, month_09, month_10, month_11, month_12
            FROM budget_lines
            WHERE version_id = %s AND administration = %s
            """,
            (source_version_id, administration),
        )

        source_lines = source_lines if source_lines else []

        # 4. For each line, check if account_code still exists in rekeningschema
        excluded_accounts: List[str] = []
        lines_to_copy: List[Dict[str, Any]] = []

        for line in source_lines:
            account_code = line['account_code']
            account_exists = self.db.execute_query(
                "SELECT Account FROM rekeningschema WHERE administration = %s AND Account = %s",
                (administration, account_code),
            )
            if account_exists:
                lines_to_copy.append(line)
            else:
                if account_code not in excluded_accounts:
                    excluded_accounts.append(account_code)

        # 5. Create new version and copy lines atomically
        try:
            with self.db.transaction() as (cursor, conn):
                # Create new budget version with status Draft
                cursor.execute(
                    """
                    INSERT INTO budget_versions
                        (administration, name, fiscal_year, status, is_active)
                    VALUES (%s, %s, %s, 'Draft', FALSE)
                    """,
                    (administration, version_name, target_fiscal_year),
                )
                new_version_id = cursor.lastrowid

                # 6. Copy lines where account exists
                for line in lines_to_copy:
                    cursor.execute(
                        """
                        INSERT INTO budget_lines
                            (version_id, administration, account_code, period_mode,
                             detail_dimension_type, detail_dimension_value,
                             month_01, month_02, month_03, month_04, month_05, month_06,
                             month_07, month_08, month_09, month_10, month_11, month_12)
                        VALUES (%s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            new_version_id,
                            administration,
                            line['account_code'],
                            line['period_mode'],
                            line['detail_dimension_type'],
                            line['detail_dimension_value'],
                            line['month_01'], line['month_02'], line['month_03'],
                            line['month_04'], line['month_05'], line['month_06'],
                            line['month_07'], line['month_08'], line['month_09'],
                            line['month_10'], line['month_11'], line['month_12'],
                        ),
                    )
        except IntegrityError:
            return {
                'success': False,
                'error': f"Budget version '{version_name}' already exists for fiscal year {target_fiscal_year}",
            }

        # 8. Return result
        return {
            'success': True,
            'data': {
                'version_id': new_version_id,
                'lines_copied': len(lines_to_copy),
                'excluded_accounts': excluded_accounts,
            },
        }

    # -------------------------------------------------------------------------
    # Dashboard & Hierarchy Rollup
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
