from flask import Blueprint, request, jsonify
from database import DatabaseManager
from mutaties_cache import get_cache
from datetime import datetime
from contextlib import contextmanager
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required

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
    
    def get_financial_summary(self, date_from, date_to, category='all', administration='all'):
        """Get financial summary data for reporting"""
        try:
            connection = self.db.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # Base query
            where_conditions = ["TransactionDate BETWEEN %s AND %s"]
            params = [date_from, date_to]
            
            # Add administration filter
            if administration != 'all':
                where_conditions.append("administration = %s")
                params.append(administration)
            
            # Category-based account filtering
            if category == 'income':
                where_conditions.append("(Credit BETWEEN '4000' AND '4999' OR Credit BETWEEN '8000' AND '8999')")
            elif category == 'expense':
                where_conditions.append("(Debet BETWEEN '6000' AND '6999' OR Debet BETWEEN '7000' AND '7999')")
            elif category == 'vat':
                where_conditions.append("(Debet = '2010' OR Credit = '2010')")
            
            where_clause = " AND ".join(where_conditions)
            
            # Query for account-based summary
            # amazonq-ignore-next-line
            query = f"""
                SELECT 
                    CASE 
                        WHEN Debet BETWEEN '4000' AND '4999' OR Credit BETWEEN '4000' AND '4999' THEN 'Revenue'
                        WHEN Debet BETWEEN '6000' AND '6999' OR Credit BETWEEN '6000' AND '6999' THEN 'Operating Expenses'
                        WHEN Debet BETWEEN '7000' AND '7999' OR Credit BETWEEN '7000' AND '7999' THEN 'Other Expenses'
                        WHEN Debet = '2010' OR Credit = '2010' THEN 'VAT'
                        WHEN Debet BETWEEN '1000' AND '1999' OR Credit BETWEEN '1000' AND '1999' THEN 'Bank/Cash'
                        ELSE 'Other'
                    END as category,
                    SUM(CASE 
                        WHEN Debet BETWEEN '4000' AND '8999' THEN -TransactionAmount
                        WHEN Credit BETWEEN '4000' AND '8999' THEN TransactionAmount
                        ELSE TransactionAmount
                    END) as amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY category
                HAVING ABS(amount) > 0.01
                ORDER BY ABS(amount) DESC
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Format data for frontend
            labels = [row['category'] for row in results]
            values = [float(row['amount']) for row in results]
            total = sum(abs(value) for value in values)
            
            cursor.close()
            connection.close()
            
            return {
                'success': True,
                'data': {
                    'labels': labels,
                    'values': values,
                    'total': total
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
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

@reporting_bp.route('/financial-summary', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
def get_financial_summary(user_email, user_roles):
    """Get financial summary report"""
    try:
        # Get query parameters
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        category = request.args.get('category', 'all')
        administration = request.args.get('administration', 'all')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        # Validate dates
        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }), 400
        
        # Get report data
        service = ReportingService(test_mode=test_mode)
        result = service.get_financial_summary(date_from, date_to, category, administration)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/balance-data', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_balance_data(user_email, user_roles, tenant, user_tenants):
    """Get balance data grouped by Parent and ledger with tenant filtering"""
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
            date_from = request.args.get('dateFrom')
            date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
            if date_from:
                where_parts.append("TransactionDate BETWEEN %s AND %s")
                params.extend([date_from, date_to])
            else:
                where_parts.append("TransactionDate <= %s")
                params.append(date_to)
            
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
                    'from': request.args.get('dateFrom'),
                    'to': request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
                },
                'administration': administration,
                'profit_loss': request.args.get('profitLoss', 'all')
            }
            
            where_clause, params = service.build_where_clause(conditions)
        
        with service.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT Parent, ledger, SUM(Amount) as total_amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY Parent, ledger
                ORDER BY Parent, ledger
            """, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/trends-data', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_trends_data(user_email, user_roles, tenant, user_tenants):
    """Get P&L trends data by year"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        
        years = [int(y) for y in request.args.get('years', str(datetime.now().year)).split(',') if y]
        
        # Get administration parameter, default to current tenant
        administration = request.args.get('administration', tenant)
        
        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
        
        conditions = {
            'years': years,
            'administration': administration,
            'profit_loss': request.args.get('profitLoss', 'Y')
        }
        
        where_clause, params = service.build_where_clause(conditions)
        
        with service.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT Parent, ledger, YEAR(TransactionDate) as year, SUM(Amount) as total_amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY Parent, ledger, YEAR(TransactionDate)
                ORDER BY Parent, ledger, year
            """, params)
            results = cursor.fetchall()
        
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
            # Get administrations (only those user has access to)
            cursor.execute(f"""
                SELECT DISTINCT administration FROM vw_mutaties
                WHERE administration IS NOT NULL AND administration != ''
                AND {admin_filter}
                ORDER BY administration
            """, admin_params)
            administrations = [row['administration'] for row in cursor.fetchall()]
            
            # Get ledgers with administration filter
            # Get ledgers (account numbers) with administration filter
            ledger_conditions = ["Reknum IS NOT NULL AND Reknum != ''", admin_filter]
            ledger_params = admin_params.copy()
            
            cursor.execute(f"""
                SELECT DISTINCT Reknum FROM vw_mutaties
                WHERE {' AND '.join(ledger_conditions)}
                ORDER BY Reknum
            """, ledger_params)
            ledgers = [row['Reknum'] for row in cursor.fetchall()]
            
            # Get references with optional filters
            ref_conditions = ["ReferenceNumber IS NOT NULL AND ReferenceNumber != ''", admin_filter]
            ref_params = admin_params.copy()
            if ledger != 'all':
                ref_conditions.append("Reknum = %s")
                ref_params.append(ledger)
            
            cursor.execute(f"""
                SELECT DISTINCT ReferenceNumber FROM vw_mutaties
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
    """Get available years or references from vw_mutaties - filtered by user tenants"""
    # Base queries with tenant filtering placeholder
    queries = {
        'years': "SELECT DISTINCT jaar as value FROM vw_mutaties WHERE jaar IS NOT NULL AND administration IN ({}) ORDER BY jaar DESC",
        'references': "SELECT DISTINCT ReferenceNumber as value FROM vw_mutaties WHERE ReferenceNumber IS NOT NULL AND ReferenceNumber != '' AND administration IN ({}) ORDER BY ReferenceNumber"
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
        
        return jsonify({'success': True, 'transactions': transactions, 'summary': summary})
    except Exception as e:
        print(f"Error in get_check_reference: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/reference-analysis', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_reference_analysis(user_email, user_roles, tenant, user_tenants):
    """Get reference analysis data with trend and available accounts - filtered by user tenants"""
    try:
        service = ReportingService()
        years = [y for y in request.args.get('years', str(datetime.now().year)).split(',') if y]
        reference_number = request.args.get('reference_number', '')
        accounts = [a for a in request.args.get('accounts', '').split(',') if a]
        
        # Get administration parameter, default to current tenant
        administration = request.args.get('administration', tenant)
        
        # Validate user has access to requested administration
        if administration != 'all' and administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
        
        with service.get_cursor() as cursor:
            # Get available accounts with tenant filtering
            account_conditions = {
                'years': years,
                'administration': administration if administration != 'all' else None
            }
            account_where, account_params = service.build_where_clause(account_conditions)
            
            # Add tenant filtering for 'all' case
            if administration == 'all':
                placeholders = ','.join(['%s'] * len(user_tenants))
                if account_where == "1=1":
                    account_where = f"administration IN ({placeholders})"
                else:
                    account_where += f" AND administration IN ({placeholders})"
                account_params.extend(user_tenants)
            
            cursor.execute(f"""
                SELECT DISTINCT Reknum, AccountName FROM vw_mutaties
                WHERE {account_where} AND Reknum IS NOT NULL AND Reknum != ''
                      AND AccountName IS NOT NULL AND AccountName != ''
                ORDER BY Reknum
            """, account_params)
            available_accounts = cursor.fetchall()
            
            transactions = []
            trend_data = []
            
            if reference_number:
                conditions = {
                    'years': years,
                    'administration': administration if administration != 'all' else None
                }
                where_clause, params = service.build_where_clause(conditions)
                
                # Add tenant filtering for 'all' case
                if administration == 'all':
                    placeholders = ','.join(['%s'] * len(user_tenants))
                    if where_clause == "1=1":
                        where_clause = f"administration IN ({placeholders})"
                    else:
                        where_clause += f" AND administration IN ({placeholders})"
                    params.extend(user_tenants)
                
                # Add reference pattern and accounts
                where_clause += " AND ReferenceNumber REGEXP %s"
                params.append(reference_number)
                
                if accounts:
                    placeholders = ','.join(['%s'] * len(accounts))
                    where_clause += f" AND Reknum IN ({placeholders})"
                    params.extend(accounts)
                
                # Get transactions
                cursor.execute(f"""
                    SELECT TransactionDate, TransactionDescription, Amount, Reknum,
                           AccountName, ReferenceNumber, Administration
                    FROM vw_mutaties
                    WHERE {where_clause}
                    ORDER BY TransactionDate DESC
                """, params)
                transactions = cursor.fetchall()
                
                # Get trend data
                cursor.execute(f"""
                    SELECT jaar, kwartaal, SUM(Amount) as total_amount
                    FROM vw_mutaties
                    WHERE {where_clause}
                    GROUP BY jaar, kwartaal
                    ORDER BY jaar, kwartaal
                """, params)
                trend_data = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'trend_data': trend_data,
            'available_accounts': available_accounts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/available-years', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_available_years(user_email, user_roles, tenant, user_tenants):
    """Get available years from vw_mutaties - filtered by user tenants"""
    try:
        service = ReportingService()
        
        # Build IN clause for user_tenants
        placeholders = ','.join(['%s'] * len(user_tenants))
        query = f"SELECT DISTINCT jaar as value FROM vw_mutaties WHERE jaar IS NOT NULL AND administration IN ({placeholders}) ORDER BY jaar DESC"
        
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


@reporting_bp.route('/aangifte-ib', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def aangifte_ib(user_email, user_roles, tenant, user_tenants):
    """Get Aangifte IB data grouped by Parent and Aangifte (using in-memory cache)"""
    try:
        # Get parameters
        year = request.args.get('year')
        administration = request.args.get('administration', tenant)  # Default to current tenant
        
        if not year:
            return jsonify({'success': False, 'error': 'Year is required'}), 400
        
        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
        
        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)
        
        # Ensure cache is loaded (will auto-refresh if needed)
        df = cache.get_data(db)
        
        # SECURITY: Filter by user's accessible tenants
        df = df[df['administration'].isin(user_tenants)]
        
        # Query from cache (much faster than SQL)
        summary_data = cache.query_aangifte_ib(year, administration)
        available_years = cache.get_available_years()
        # Only show administrations user has access to
        available_administrations = [admin for admin in cache.get_available_administrations(year) if admin in user_tenants]
        
        return jsonify({
            'success': True,
            'data': summary_data,
            'available_years': available_years,
            'available_administrations': available_administrations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@reporting_bp.route('/aangifte-ib-details', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def aangifte_ib_details(user_email, user_roles, tenant, user_tenants):
    """Get underlying accounts for a specific Parent and Aangifte (using in-memory cache)"""
    try:
        # Get parameters
        year = request.args.get('year')
        administration = request.args.get('administration', tenant)  # Default to current tenant
        parent = request.args.get('parent')
        aangifte = request.args.get('aangifte')
        
        if not all([year, parent, aangifte]):
            return jsonify({'success': False, 'error': 'Year, parent, and aangifte are required'}), 400
        
        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
        
        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)
        
        # Ensure cache is loaded (will auto-refresh if needed)
        df = cache.get_data(db)
        
        # SECURITY: Filter by user's accessible tenants
        # Note: Column name is 'administration' (lowercase) from vw_mutaties view
        df = df[df['administration'].isin(user_tenants)]
        
        # Query from cache (much faster than SQL) with tenant filtering
        details_data = cache.query_aangifte_ib_details(year, administration, parent, aangifte, user_tenants)
        
        return jsonify({
            'success': True,
            'data': details_data,
            'parent': parent,
            'aangifte': aangifte
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in aangifte_ib_details: {error_details}", flush=True)
        return jsonify({'success': False, 'error': str(e), 'details': error_details if flag else None}), 500



@reporting_bp.route('/aangifte-ib-export', methods=['POST'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()
def aangifte_ib_export(user_email, user_roles, tenant, user_tenants):
    """Generate HTML export for Aangifte IB report using TemplateService with field mappings
    
    Supports multiple output destinations:
    - download: Return content to frontend for download (default)
    - gdrive: Upload to tenant's Google Drive
    - s3: Upload to AWS S3 (future implementation)
    """
    try:
        data = request.get_json()
        year = data.get('year')
        administration = data.get('administration', tenant)  # Default to current tenant
        report_data = data.get('data', [])
        output_destination = data.get('output_destination', 'download')  # Default to download
        folder_id = data.get('folder_id')  # Optional Google Drive folder ID
        
        if not year:
            return jsonify({'success': False, 'error': 'Year is required'}), 400
        
        # Validate user has access to requested administration
        if administration != 'all' and administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
        
        # Get cache instance for account details
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)
        
        # Ensure cache is loaded
        cache.get_data(db)
        
        # Use report_generators to generate table rows
        from report_generators import generate_table_rows
        table_rows_data = generate_table_rows(
            report_data=report_data,
            cache=cache,
            year=year,
            administration=administration,
            user_tenants=user_tenants
        )
        
        # Convert row data to HTML
        table_rows_html = _render_table_rows(table_rows_data)
        
        # Initialize TemplateService
        from services.template_service import TemplateService
        template_service = TemplateService(db)
        
        # Prepare template data
        template_data = {
            'year': str(year),
            'administration': administration if administration != 'all' else 'All',
            'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'table_rows': table_rows_html
        }
        
        # Try to get template metadata from database
        template_type = 'aangifte_ib_html'
        metadata = None
        
        try:
            metadata = template_service.get_template_metadata(administration, template_type)
        except Exception as e:
            if logger:
                logger.warning(f"Could not get template metadata from database: {e}")
        
        # Load template
        if metadata and metadata.get('template_file_id'):
            # Load from Google Drive
            try:
                template_content = template_service.fetch_template_from_drive(
                    metadata['template_file_id'],
                    administration
                )
                field_mappings = metadata.get('field_mappings', {})
            except Exception as e:
                if logger:
                    logger.error(f"Failed to fetch template from Google Drive: {e}")
                # Fallback to filesystem
                metadata = None
        
        if not metadata:
            # Fallback: Load from filesystem
            import os
            template_path = os.path.join(
                os.path.dirname(__file__),
                '..',
                'templates',
                'html',
                'aangifte_ib_template.html'
            )
            
            if not os.path.exists(template_path):
                if logger:
                    logger.error(f"Template not found: {template_path}")
                return jsonify({'success': False, 'error': 'Template not found'}), 500
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            # Use default field mappings (simple placeholder replacement)
            field_mappings = {
                'fields': {key: {'path': key, 'format': 'text'} for key in template_data.keys()},
                'formatting': {
                    'locale': 'nl_NL',
                    'date_format': '%Y-%m-%d %H:%M:%S',
                    'number_decimals': 2
                }
            }
        
        # Apply field mappings using TemplateService
        html_content = template_service.apply_field_mappings(
            template_content,
            template_data,
            field_mappings
        )
        
        # Generate filename
        filename = f'Aangifte_IB_{administration}_{year}.html'
        
        # Handle output destination
        from services.output_service import OutputService
        output_service = OutputService(db)
        
        output_result = output_service.handle_output(
            content=html_content,
            filename=filename,
            destination=output_destination,
            administration=administration,
            content_type='text/html',
            folder_id=folder_id
        )
        
        # Return result based on destination
        if output_destination == 'download':
            return jsonify({
                'success': True,
                'html': output_result['content'],
                'filename': output_result['filename']
            })
        else:
            # For gdrive or s3, return URL and metadata
            return jsonify({
                'success': True,
                'destination': output_result['destination'],
                'url': output_result.get('url'),
                'filename': output_result['filename'],
                'message': output_result['message']
            })
        
    except Exception as e:
        print(f"Error in aangifte_ib_export: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def _render_table_rows(rows_data):
    """
    Convert row data dictionaries to HTML table rows.
    
    Args:
        rows_data: List of row dictionaries from generate_table_rows()
    
    Returns:
        HTML string of table rows
    """
    html_rows = []
    
    for row in rows_data:
        row_type = row.get('row_type', '')
        css_class = row.get('css_class', '')
        parent = row.get('parent', '')
        aangifte = row.get('aangifte', '')
        description = row.get('description', '')
        amount = row.get('amount', '')
        indent_level = row.get('indent_level', 0)
        
        # Apply indentation class
        parent_td_class = ''
        if indent_level == 1:
            parent_td_class = ' class="indent-1"'
        elif indent_level == 2:
            parent_td_class = ' class="indent-2"'
        
        # Build table row
        html_row = f'<tr class="{css_class}">'
        html_row += f'<td{parent_td_class}>{parent}</td>'
        html_row += f'<td>{aangifte}</td>'
        html_row += f'<td>{description}</td>'
        html_row += f'<td class="amount">{amount}</td>'
        html_row += '</tr>'
        
        html_rows.append(html_row)
    
    return '\n'.join(html_rows)



@reporting_bp.route('/aangifte-ib-xlsx-export', methods=['POST'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()
def aangifte_ib_xlsx_export(user_email, user_roles, tenant, user_tenants):
    """Generate XLSX export for Aangifte IB with tenant filtering"""
    try:
        data = request.get_json()
        administrations = data.get('administrations', [])
        years = data.get('years', [])
        
        if not administrations or not years:
            return jsonify({'success': False, 'error': 'Administrations and years are required'}), 400
        
        # Validate all requested administrations against user_tenants
        unauthorized_admins = [admin for admin in administrations if admin not in user_tenants]
        if unauthorized_admins:
            return jsonify({
                'success': False, 
                'error': f'Access denied to administrations: {", ".join(unauthorized_admins)}'
            }), 403
        
        # Debug: Check available administrations (filtered by user_tenants)
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build query with tenant filtering
        placeholders = ', '.join(['%s'] * len(user_tenants))
        query = f"SELECT DISTINCT Administration FROM vw_mutaties WHERE Administration IN ({placeholders}) ORDER BY Administration"
        cursor.execute(query, user_tenants)
        available_admins = [row['Administration'] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        from xlsx_export import XLSXExportProcessor
        xlsx_processor = XLSXExportProcessor(test_mode=flag)
        results = xlsx_processor.generate_xlsx_export(administrations, years)
        
        successful_results = [r for r in results if r['success']]
        
        return jsonify({
            'success': True,
            'results': results,
            'available_administrations': available_admins,
            'message': f'Generated {len(successful_results)} XLSX files out of {len(results)} requested'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@reporting_bp.route('/aangifte-ib-xlsx-export-stream', methods=['POST'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()
def aangifte_ib_xlsx_export_stream(user_email, user_roles, tenant, user_tenants):
    """Generate XLSX export for Aangifte IB with streaming progress and tenant filtering"""
    from flask import Response
    import json
    
    print("STREAMING ENDPOINT CALLED!")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
            
        administrations = data.get('administrations', [])
        years = data.get('years', [])
        
        if not administrations or not years:
            return jsonify({'success': False, 'error': 'Administrations and years are required'}), 400
        
        # Validate all requested administrations against user_tenants
        unauthorized_admins = [admin for admin in administrations if admin not in user_tenants]
        if unauthorized_admins:
            return jsonify({
                'success': False, 
                'error': f'Access denied to administrations: {", ".join(unauthorized_admins)}'
            }), 403
        
        def generate_progress():
            try:
                from xlsx_export import XLSXExportProcessor
                xlsx_processor = XLSXExportProcessor(test_mode=flag)
                
                # Send initial progress
                yield f"data: {json.dumps({'type': 'start', 'administrations': administrations, 'years': years}, default=str)}\n\n"
                
                # Process with progress updates
                for progress_data in xlsx_processor.generate_xlsx_export_with_progress(administrations, years):
                    yield f"data: {json.dumps(progress_data, default=str)}\n\n"
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        return Response(generate_progress(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
