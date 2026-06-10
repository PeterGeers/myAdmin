"""General reporting endpoints for data retrieval, filtering, and summary views.

Aangifte IB endpoints extracted to: routes/aangifte_ib_routes.py
Balance/trends endpoints extracted to: routes/financial_reporting_routes.py
"""
from flask import Blueprint, request, jsonify
from database import DatabaseManager
from datetime import datetime
from contextlib import contextmanager
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from utils.date_utils import normalize_dates

reporting_bp = Blueprint('reporting', __name__)


class ReportingService:
    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)
        self.table_name = 'mutaties_test' if test_mode else 'mutaties'

    @contextmanager
    def get_cursor(self):
        """Context manager for database operations"""
        connection = self.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            yield cursor
        finally:
            cursor.close()
            connection.close()

    def build_where_clause(self, conditions):
        """Build WHERE clause from conditions dict"""
        where_parts = []
        params = []

        for key, value in conditions.items():
            if value == 'all' or not value:
                continue

            if key == 'date_range':
                if value.get('from') and value.get('to'):
                    where_parts.append("TransactionDate BETWEEN %s AND %s")
                    params.extend([value['from'], value['to']])
                elif value.get('to'):
                    where_parts.append("TransactionDate <= %s")
                    params.append(value['to'])
            elif key == 'years':
                if isinstance(value, list) and value:
                    placeholders = ','.join(['%s'] * len(value))
                    where_parts.append(f"jaar IN ({placeholders})")
                    params.extend(value)
            elif key == 'administration':
                where_parts.append("administration = %s")
                params.append(value)
            elif key == 'profit_loss':
                where_parts.append("VW = %s")
                params.append(value)
            elif key == 'channel':
                where_parts.append("channel = %s")
                params.append(value)
            elif key == 'listing':
                where_parts.append("listing = %s")
                params.append(value)
            elif key == 'reference':
                where_parts.append("ReferenceNumber = %s")
                params.append(value)
            elif key == 'ledger':
                where_parts.append("Reknum = %s")
                params.append(value)

        return " AND ".join(where_parts) if where_parts else "1=1", params

    def get_str_revenue_summary(self, date_from, date_to, user_tenants=None):
        """Get STR revenue summary from bnb table with tenant filtering"""
        try:
            connection = self.db.get_connection()
            cursor = connection.cursor(dictionary=True)

            # Build WHERE clause with tenant filtering
            where_conditions = ["checkinDate BETWEEN %s AND %s"]
            params = [date_from, date_to]

            # Add tenant filtering if user_tenants provided
            if user_tenants:
                placeholders = ','.join(['%s'] * len(user_tenants))
                where_conditions.append(f"administration IN ({placeholders})")
                params.extend(user_tenants)

            where_clause = " AND ".join(where_conditions)

            query = f"""
                SELECT 
                    channel,
                    listing,
                    COUNT(*) as bookings,
                    SUM(amountGross) as gross_revenue,
                    SUM(amountNett) as net_revenue,
                    SUM(nights) as total_nights
                FROM vw_bnb_total
                WHERE {where_clause}
                GROUP BY channel, listing
                ORDER BY gross_revenue DESC
            """

            cursor.execute(query, params)
            results = cursor.fetchall()

            cursor.close()
            connection.close()

            return {
                'success': True,
                'data': results
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


@reporting_bp.route('/str-revenue', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_str_revenue(user_email, user_roles, tenant, user_tenants):
    """Get STR revenue summary with tenant filtering"""
    try:
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        test_mode = request.args.get('testMode', 'false').lower() == 'true'

        service = ReportingService(test_mode=test_mode)
        result = service.get_str_revenue_summary(date_from, date_to, user_tenants)

        return jsonify(result)

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@reporting_bp.route('/account-summary', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_account_summary(user_email, user_roles, tenant, user_tenants):
    """Get account-based summary for chart of accounts analysis with tenant filtering"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        administration = request.args.get('administration', tenant)  # Default to current tenant

        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403

        with service.get_cursor() as cursor:
            cursor.execute("""
                SELECT Debet as account, SUM(TransactionAmount) as debet_total, COUNT(*) as debet_count
                FROM vw_mutaties
                WHERE TransactionDate BETWEEN %s AND %s 
                  AND Debet IS NOT NULL AND Debet != ''
                  AND administration = %s
                GROUP BY Debet
                UNION ALL
                SELECT Credit as account, -SUM(TransactionAmount) as credit_total, COUNT(*) as credit_count
                FROM vw_mutaties
                WHERE TransactionDate BETWEEN %s AND %s 
                  AND Credit IS NOT NULL AND Credit != ''
                  AND administration = %s
                GROUP BY Credit
                ORDER BY ABS(debet_total) DESC
            """, [date_from, date_to, administration, date_from, date_to, administration])
            results = cursor.fetchall()

        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@reporting_bp.route('/mutaties-table', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_mutaties_table(user_email, user_roles, tenant, user_tenants):
    """Get mutaties table data with PowerBI-style filters and tenant filtering"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')

        # Get administration parameter, default to current tenant
        administration = request.args.get('administration', tenant)

        # Validate user has access to requested administration
        if administration != 'all' and administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403

        # If 'all' is requested, filter by user_tenants
        if administration == 'all':
            # Build WHERE clause with tenant filtering
            where_parts = []
            params = []

            # Date range
            date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
            date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
            where_parts.append("TransactionDate BETWEEN %s AND %s")
            params.extend([date_from, date_to])

            # Tenant filtering - only show data from user's accessible tenants
            placeholders = ','.join(['%s'] * len(user_tenants))
            where_parts.append(f"administration IN ({placeholders})")
            params.extend(user_tenants)

            # Profit/Loss filter
            profit_loss = request.args.get('profitLoss', 'all')
            if profit_loss != 'all':
                where_parts.append("VW = %s")
                params.append(profit_loss)

            where_clause = " AND ".join(where_parts)
        else:
            # Single administration requested
            conditions = {
                'date_range': {
                    'from': request.args.get('dateFrom', datetime.now().strftime('%Y-01-01')),
                    'to': request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
                },
                'administration': administration,
                'profit_loss': request.args.get('profitLoss', 'all')
            }

            where_clause, params = service.build_where_clause(conditions)

        with service.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT TransactionDate, TransactionDescription, Amount, Reknum,
                       AccountName, Administration, ReferenceNumber, VW
                FROM vw_mutaties
                WHERE {where_clause}
                ORDER BY TransactionDate DESC
                LIMIT 1000
            """, params)
            results = cursor.fetchall()

        normalize_dates(results, ['TransactionDate'])
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@reporting_bp.route('/filter-options', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_filter_options(user_email, user_roles, tenant, user_tenants):
    """Get distinct values for each filter dropdown with cascading support"""
    try:
        service = ReportingService()
        administration = request.args.get('administration', tenant)  # Default to current tenant
        ledger = request.args.get('ledger', 'all')

        # If user requests 'all' administrations, only show their accessible tenants
        if administration == 'all':
            admin_filter = f"administration IN ({','.join(['%s'] * len(user_tenants))})"
            admin_params = user_tenants
        else:
            # Validate user has access to requested administration
            if administration not in user_tenants:
                return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
            admin_filter = "administration = %s"
            admin_params = [administration]

        with service.get_cursor() as cursor:
            # Get administrations — query base mutaties table directly (avoids full view materialization)
            cursor.execute(f"""
                SELECT DISTINCT administration FROM mutaties
                WHERE administration IS NOT NULL AND administration != ''
                AND {admin_filter}
                ORDER BY administration
            """, admin_params)
            administrations = [row['administration'] for row in cursor.fetchall()]

            # Get ledgers (account numbers) — join mutaties with rekeningschema directly
            # The OR join pattern is needed because a mutation can reference an account via either Debet or Credit
            ledger_params = admin_params.copy() + admin_params.copy()

            cursor.execute(f"""
                SELECT DISTINCT r.Account as Reknum
                FROM mutaties m
                JOIN rekeningschema r ON m.Debet = r.Account AND m.administration = r.administration
                WHERE {admin_filter.replace('administration', 'm.administration')}
                UNION
                SELECT DISTINCT r.Account as Reknum
                FROM mutaties m
                JOIN rekeningschema r ON m.Credit = r.Account AND m.administration = r.administration
                WHERE {admin_filter.replace('administration', 'm.administration')}
                ORDER BY Reknum
            """, ledger_params)
            ledgers = [row['Reknum'] for row in cursor.fetchall()]

            # Get references — query base mutaties table directly
            ref_conditions = ["ReferenceNumber IS NOT NULL AND ReferenceNumber != ''", admin_filter]
            ref_params = admin_params.copy()
            if ledger != 'all':
                # Since mutaties doesn't have Reknum, join with rekeningschema to filter by account
                ref_conditions.append("(m.Debet = %s OR m.Credit = %s)")
                ref_params.extend([ledger, ledger])
                cursor.execute(f"""
                    SELECT DISTINCT m.ReferenceNumber FROM mutaties m
                    WHERE {' AND '.join(ref_conditions)}
                    ORDER BY m.ReferenceNumber
                """, ref_params)
            else:
                cursor.execute(f"""
                    SELECT DISTINCT ReferenceNumber FROM mutaties
                    WHERE {' AND '.join(ref_conditions)}
                    ORDER BY ReferenceNumber
                """, ref_params)
            references = [row['ReferenceNumber'] for row in cursor.fetchall()]

        return jsonify({
            'success': True,
            'administrations': administrations,
            'ledgers': ledgers,
            'references': references
        })
    except Exception as e:
        print(f"Error in get_filter_options: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@reporting_bp.route('/available-<data_type>', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_available_data(data_type, user_email, user_roles, tenant, user_tenants):
    """Get available years or references from mutaties table - filtered by user tenants"""
    # Base queries on mutaties table directly (avoids full view materialization)
    queries = {
        'years': "SELECT DISTINCT YEAR(TransactionDate) as value FROM mutaties WHERE TransactionDate IS NOT NULL AND administration IN ({}) ORDER BY value DESC",
        'references': "SELECT DISTINCT ReferenceNumber as value FROM mutaties WHERE ReferenceNumber IS NOT NULL AND ReferenceNumber != '' AND administration IN ({}) ORDER BY ReferenceNumber"
    }

    if data_type not in queries:
        return jsonify({'success': False, 'error': 'Invalid data type'}), 400

    try:
        service = ReportingService()

        # Build IN clause for user_tenants
        placeholders = ','.join(['%s'] * len(user_tenants))
        query = queries[data_type].format(placeholders)

        with service.get_cursor() as cursor:
            cursor.execute(query, user_tenants)
            values = [str(row['value']) for row in cursor.fetchall()]

        return jsonify({'success': True, data_type: values})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@reporting_bp.route('/check-reference', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_check_reference(user_email, user_roles, tenant, user_tenants):
    """Get check reference data with transactions and summary - DIRECT DATABASE QUERY (NO CACHE)"""
    try:
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        reference_number = request.args.get('referenceNumber', 'all')
        administration = request.args.get('administration', tenant)  # Default to current tenant
        ledger = request.args.get('ledger', 'all')

        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403

        db = DatabaseManager(test_mode=test_mode)

        # Build WHERE clause for tenant filtering
        where_conditions = [
            "ReferenceNumber IS NOT NULL",
            "ReferenceNumber != ''",
            "administration = %s"
        ]
        params = [administration]

        if ledger != 'all':
            # Extract just the account number (first part before space)
            account_num = ledger.split(' ')[0] if ' ' in ledger else ledger
            where_conditions.append("Reknum = %s")
            params.append(account_num)

        where_clause = " AND ".join(where_conditions)

        # Get reference summary
        summary_query = f"""
            SELECT 
                ReferenceNumber,
                COUNT(*) as transaction_count,
                SUM(Amount) as total_amount
            FROM vw_mutaties
            WHERE {where_clause}
            GROUP BY ReferenceNumber
            HAVING ABS(SUM(Amount)) > 0.01
            ORDER BY ABS(SUM(Amount)) DESC
        """

        summary = db.execute_query(summary_query, tuple(params))

        # Get detailed transactions if specific reference selected
        transactions = []
        if reference_number != 'all':
            detail_conditions = where_conditions + ["ReferenceNumber = %s"]
            detail_params = params + [reference_number]
            detail_where = " AND ".join(detail_conditions)

            transactions_query = f"""
                SELECT 
                    TransactionDate,
                    TransactionNumber,
                    TransactionDescription,
                    Amount,
                    Reknum,
                    AccountName,
                    administration as Administration
                FROM vw_mutaties
                WHERE {detail_where}
                ORDER BY TransactionDate DESC
            """

            transactions = db.execute_query(transactions_query, tuple(detail_params))

        normalize_dates(transactions, ['TransactionDate'])
        return jsonify({'success': True, 'transactions': transactions, 'summary': summary})
    except Exception as e:
        print(f"Error in get_check_reference: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@reporting_bp.route('/available-years', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_available_years(user_email, user_roles, tenant, user_tenants):
    """
    Get available years from mutaties table - filtered by user tenants.
    
    IMPORTANT: Queries the base table directly, not the cache/view,
    so all years are available even if not loaded in cache.
    """
    try:
        service = ReportingService()

        # Determine table name based on test mode
        table_name = 'mutaties_test' if flag else 'mutaties'

        # Build IN clause for user_tenants
        # Use YEAR() on base table — acceptable since administration index
        # filters rows first, and composite index will cover this after task 6
        placeholders = ','.join(['%s'] * len(user_tenants))
        query = f"""
            SELECT DISTINCT YEAR(TransactionDate) as value 
            FROM {table_name} 
            WHERE TransactionDate IS NOT NULL 
            AND administration IN ({placeholders}) 
            ORDER BY value DESC
        """

        with service.get_cursor() as cursor:
            cursor.execute(query, user_tenants)
            years = [str(row['value']) for row in cursor.fetchall()]

        return jsonify({'success': True, 'years': years})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Global variables set by app.py
flag = False
logger = None


def set_test_mode(test_mode):
    """Set test mode flag"""
    global flag
    flag = test_mode


def set_logger(log_instance):
    """Set logger instance"""
    global logger
    logger = log_instance
