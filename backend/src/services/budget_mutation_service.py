"""
Budget Mutation Service

Handles write operations for budget management:
- Budget version CRUD and status transitions
- Budget line creation, update, and deletion
- Budget copy between fiscal years
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Optional

from database import DatabaseManager
from db_exceptions import IntegrityError


class BudgetMutationService:
    """Write-only service for budget mutations (create, update, delete).

    Tenant Isolation:
        Every public method requires an `administration` parameter as its first
        argument. All database queries include an `administration` filter,
        ensuring data is scoped to the requesting tenant.
    """

    def __init__(self, db: DatabaseManager) -> None:
        """
        Initialize BudgetMutationService.

        Args:
            db: Shared DatabaseManager instance.
        """
        self.db = db

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

        # 2. Validate target year is later than source year
        if target_fiscal_year <= source_version['fiscal_year']:
            return {
                'success': False,
                'error': f"Target year must be later than source year {source_version['fiscal_year']}",
            }

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
