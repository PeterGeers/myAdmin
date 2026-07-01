"""
Banking Mutatie Service

Query and update operations for banking transaction records (mutaties table).
Split from banking_service.py for file size management.

Provides:
- get_mutaties(): Paginated, filtered transaction query
- update_mutatie(): Single record update with tenant validation
"""

from typing import Dict, Any, List

from database import DatabaseManager


class BankingMutatieService:
    """Service for querying and updating banking transaction records."""

    def __init__(self, test_mode: bool = False) -> None:
        self.test_mode = test_mode

    def get_mutaties(
        self, filters: Dict[str, Any], tenant: str, user_tenants: List[str]
    ) -> Dict[str, Any]:
        """Get mutaties with filters.

        Args:
            filters: Filter parameters (years, administration, limit, offset)
            tenant: Current tenant
            user_tenants: List of tenants user has access to

        Returns:
            dict with mutaties list, pagination info
        """
        try:
            from datetime import datetime

            db = DatabaseManager(test_mode=self.test_mode)
            table_name = "mutaties_test" if self.test_mode else "mutaties"

            # Get filter parameters
            years = filters.get("years", [str(datetime.now().year)])
            administration = filters.get("administration", "all")
            limit = int(filters.get("limit", 1000))
            offset = int(filters.get("offset", 0))

            # Cap limit at 100000 to prevent abuse
            limit = min(limit, 100000)

            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Build WHERE clause
            where_conditions = []
            params = []

            # Years filter — use sargable date range conditions
            if years and years != [""]:
                from utils.query_helpers import years_to_date_range_conditions

                year_sql, year_params = years_to_date_range_conditions(years)
                where_conditions.append(year_sql)
                params.extend(year_params)

            # Administration filter - MUST respect user's accessible tenants
            if administration == "all":
                if len(user_tenants) == 1:
                    where_conditions.append("administration = %s")
                    params.append(user_tenants[0])
                else:
                    placeholders = ",".join(["%s"] * len(user_tenants))
                    where_conditions.append(f"administration IN ({placeholders})")
                    params.extend(user_tenants)
            else:
                # Validate user has access to requested administration
                if administration not in user_tenants:
                    return {
                        "success": False,
                        "error": "Access denied to administration",
                    }
                where_conditions.append("administration = %s")
                params.append(administration)

            where_clause = (
                "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            )

            # Get total count for pagination
            count_query = f"""
                SELECT COUNT(*) as total
                FROM {table_name}
                {where_clause}
            """
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()["total"]

            # Get paginated results
            query = f"""
                SELECT ID, TransactionNumber, TransactionDate, TransactionDescription,
                       TransactionAmount, Debet, Credit, ReferenceNumber,
                       Ref1, Ref2, Ref3, Ref4, Administration
                FROM {table_name}
                {where_clause}
                ORDER BY TransactionDate DESC, ID DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])
            cursor.execute(query, params)

            results = cursor.fetchall()
            cursor.close()
            conn.close()

            # Convert date objects to ISO strings
            for row in results:
                val = row.get("TransactionDate")
                if val and hasattr(val, "isoformat"):
                    row["TransactionDate"] = val.isoformat()

            return {
                "success": True,
                "mutaties": results,
                "count": len(results),
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + len(results)) < total_count,
                "table": table_name,
            }

        except Exception as e:
            print(f"Get mutaties error: {e}", flush=True)
            return {"success": False, "error": str(e)}

    def update_mutatie(
        self, mutatie_id: int, data: Dict[str, Any], tenant: str
    ) -> Dict[str, Any]:
        """Update a mutatie record.

        Args:
            mutatie_id: ID of record to update
            data: Updated field values
            tenant: Current tenant (for validation)

        Returns:
            dict with success status
        """
        try:
            from datetime import datetime

            db = DatabaseManager(test_mode=self.test_mode)
            table_name = "mutaties_test" if self.test_mode else "mutaties"

            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Verify the record belongs to the current tenant
            cursor.execute(
                f"SELECT administration FROM {table_name} WHERE ID = %s", (mutatie_id,)
            )
            existing_record = cursor.fetchone()

            if not existing_record:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Record not found"}

            if existing_record["administration"] != tenant:
                cursor.close()
                conn.close()
                return {
                    "success": False,
                    "error": "Access denied: Record belongs to different tenant",
                }

            # Update the record - FORCE Administration to current tenant
            update_query = f"""
                UPDATE {table_name} SET
                    TransactionNumber = %s,
                    TransactionDate = %s,
                    TransactionDescription = %s,
                    TransactionAmount = %s,
                    Debet = %s,
                    Credit = %s,
                    ReferenceNumber = %s,
                    Ref1 = %s,
                    Ref2 = %s,
                    Ref3 = %s,
                    Ref4 = %s,
                    administration = %s
                WHERE ID = %s
            """

            # Convert date to proper format
            transaction_date = data.get("TransactionDate")
            if transaction_date and "GMT" in str(transaction_date):
                transaction_date = datetime.strptime(
                    transaction_date, "%a, %d %b %Y %H:%M:%S %Z"
                ).strftime("%Y-%m-%d")

            cursor.execute(
                update_query,
                (
                    data.get("TransactionNumber"),
                    transaction_date,
                    data.get("TransactionDescription"),
                    data.get("TransactionAmount"),
                    data.get("Debet"),
                    data.get("Credit"),
                    data.get("ReferenceNumber"),
                    data.get("Ref1"),
                    data.get("Ref2"),
                    data.get("Ref3"),
                    data.get("Ref4"),
                    tenant,  # FORCE to current tenant
                    mutatie_id,
                ),
            )

            conn.commit()
            cursor.close()
            conn.close()

            print(
                f"Record {mutatie_id} updated successfully with administration={tenant}",
                flush=True,
            )

            return {
                "success": True,
                "message": f"Record {mutatie_id} updated successfully",
            }

        except Exception as e:
            print(f"Update error: {e}", flush=True)
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}
