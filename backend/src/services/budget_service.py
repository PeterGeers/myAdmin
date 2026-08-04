"""
Budget Service (Facade)

Composes BudgetQueryService and BudgetMutationService to provide a unified
interface for budget management. Maintains backward compatibility with all
existing consumers.

Responsibilities delegated to:
- budget_query_service.py: Listing, rollup, dashboard
- budget_mutation_service.py: CRUD, status transitions, copy
"""

from decimal import Decimal
from typing import Any

from database import DatabaseManager
from services.budget_mutation_service import BudgetMutationService
from services.budget_query_service import BudgetQueryService


class BudgetService:
    """Facade for budget management operations.

    Delegates to BudgetQueryService (reads) and BudgetMutationService (writes).
    All public methods preserve the same signature and return format as before.

    Tenant Isolation:
        Every public method requires an `administration` parameter as its first
        argument. This value originates from the @tenant_required() decorator in
        budget_routes.py and represents the authenticated user's current tenant.
    """

    def __init__(self, test_mode: bool = False) -> None:
        """
        Initialize BudgetService.

        Args:
            test_mode: Whether to run in test mode (uses test database).
        """
        self.test_mode = test_mode
        self._db = DatabaseManager(test_mode=test_mode)
        self._query = BudgetQueryService(db=self._db)
        self._mutation = BudgetMutationService(db=self._db)

    @property
    def db(self) -> DatabaseManager:
        """Shared database manager instance."""
        return self._db

    @db.setter
    def db(self, value: DatabaseManager) -> None:
        """Propagate db replacement to sub-services (supports test mocking)."""
        self._db = value
        self._query.db = value
        self._mutation.db = value

    # -------------------------------------------------------------------------
    # Monetary Utilities (kept here for backward compatibility)
    # -------------------------------------------------------------------------

    @staticmethod
    def round_monetary(amount: Decimal) -> Decimal:
        """
        Round a monetary amount to 2 decimal places using banker's rounding.

        Args:
            amount: The decimal amount to round.

        Returns:
            The amount rounded to 2 decimal places.

        Validates: Requirements 3.5, 6.9
        """
        return BudgetMutationService.round_monetary(amount)

    @staticmethod
    def divide_annual(annual_amount: Decimal, months: int = 12) -> list[Decimal]:
        """
        Divide an annual amount into equal monthly amounts with banker's rounding.

        Args:
            annual_amount: The total annual amount to divide.
            months: Number of months to divide into (default 12).

        Returns:
            List of monthly Decimal amounts whose sum equals annual_amount.

        Validates: Requirements 2.3, 3.2
        """
        return BudgetMutationService.divide_annual(annual_amount, months)

    # -------------------------------------------------------------------------
    # Query Operations (delegated to BudgetQueryService)
    # -------------------------------------------------------------------------

    def list_versions(
        self, administration: str, year: int | None = None
    ) -> dict[str, Any]:
        """List budget versions for a tenant, optionally filtered by fiscal year."""
        return self._query.list_versions(administration, year)

    def list_lines(self, administration: str, version_id: int) -> dict[str, Any]:
        """List all budget lines for a version."""
        return self._query.list_lines(administration, version_id)

    def get_rollup(
        self,
        administration: str,
        version_id: int,
        level: str,
        parent_code: str | None = None,
        subparent_code: str | None = None,
        months: list[int] | None = None,
    ) -> dict[str, Any]:
        """Compute hierarchy rollup for budget lines at the requested level."""
        return self._query.get_rollup(
            administration, version_id, level, parent_code, subparent_code, months
        )

    def get_dashboard(
        self,
        administration: str,
        level: str,
        period: str,
        version_id: int | None = None,
        year: int | None = None,
        parent_code: str | None = None,
        subparent_code: str | None = None,
        reference_number: str | None = None,
    ) -> dict[str, Any]:
        """Dashboard budget vs actuals comparison."""
        return self._query.get_dashboard(
            administration,
            level,
            period,
            version_id,
            year,
            parent_code,
            subparent_code,
            reference_number,
        )

    # -------------------------------------------------------------------------
    # Mutation Operations (delegated to BudgetMutationService)
    # -------------------------------------------------------------------------

    def create_version(
        self, administration: str, name: str, fiscal_year: int
    ) -> dict[str, Any]:
        """Create a new budget version with status Draft."""
        return self._mutation.create_version(administration, name, fiscal_year)

    def delete_version(self, administration: str, version_id: int) -> dict[str, Any]:
        """Delete a budget version. Only Draft versions can be deleted."""
        return self._mutation.delete_version(administration, version_id)

    def transition_status(
        self, administration: str, version_id: int, action: str
    ) -> dict[str, Any]:
        """Transition a budget version's status (approve/revise)."""
        return self._mutation.transition_status(administration, version_id, action)

    def activate_version(
        self, administration: str, version_id: int, active: bool = True
    ) -> dict[str, Any]:
        """Toggle the active flag on a budget version."""
        return self._mutation.activate_version(administration, version_id, active)

    def create_line(
        self,
        administration: str,
        version_id: int,
        account_code: str,
        period_mode: str,
        amounts: list[float] | None = None,
        annual_amount: float | None = None,
        detail_dimension_type: str | None = None,
        detail_dimension_value: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Create a new budget line for a version."""
        return self._mutation.create_line(
            administration,
            version_id,
            account_code,
            period_mode,
            amounts,
            annual_amount,
            detail_dimension_type,
            detail_dimension_value,
            notes,
        )

    def update_line(
        self,
        administration: str,
        line_id: int,
        amounts: list[float] | None = None,
        annual_amount: float | None = None,
    ) -> dict[str, Any]:
        """Update a budget line's monthly amounts."""
        return self._mutation.update_line(
            administration, line_id, amounts, annual_amount
        )

    def delete_line(self, administration: str, line_id: int) -> dict[str, Any]:
        """Delete a budget line."""
        return self._mutation.delete_line(administration, line_id)

    def copy_budget(
        self,
        administration: str,
        source_version_id: int,
        target_fiscal_year: int,
        version_name: str,
    ) -> dict[str, Any]:
        """Copy a budget version to a new fiscal year."""
        return self._mutation.copy_budget(
            administration, source_version_id, target_fiscal_year, version_name
        )

    # -------------------------------------------------------------------------
    # Internal Utilities (kept for backward compatibility with tests)
    # -------------------------------------------------------------------------

    @staticmethod
    def _sum_months(row: dict[str, Any], months: list[int] | None = None) -> Decimal:
        """Sum the specified months from a row dict containing m01..m12 keys."""
        return BudgetQueryService._sum_months(row, months)

    def _compute_monthly_amounts(
        self, monthly_actuals: dict[int, Decimal]
    ) -> list[Decimal]:
        """Compute 12 monthly budget amounts from prior-year actuals."""
        return self._mutation._compute_monthly_amounts(monthly_actuals)

    def _parse_period(self, period: str) -> list[int]:
        """Convert a period string to a list of month numbers (1-12)."""
        return self._query._parse_period(period)
