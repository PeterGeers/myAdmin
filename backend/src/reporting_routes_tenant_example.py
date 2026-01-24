"""
Example: Tenant-Aware Reporting Routes

This file demonstrates how to update reporting routes with tenant filtering.
This is an EXAMPLE file showing the pattern - not meant to replace reporting_routes.py yet.

Based on the migration guide at backend/docs/tenant_filtering_migration_guide.md
"""

from flask import Blueprint, request, jsonify
from database import DatabaseManager
from datetime import datetime
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required, add_tenant_filter

reporting_tenant_example_bp = Blueprint('reporting_tenant_example', __name__)


@reporting_tenant_example_bp.route('/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
@tenant_required()
def get_invoices_tenant_aware(user_email, user_roles, tenant, user_tenants):
    """
    Get invoices for current tenant
    
    Example of simple tenant filtering
    """
    try:
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        date_from = request.args.get('dateFrom', '2024-01-01')
        
        # Build query with tenant filter
        query = """
            SELECT 
                ID,
                TransactionDate,
                TransactionAmount,
                TransactionDescription,
                ReferenceNumber,
                Debet,
                Credit
            FROM mutaties
            WHERE TransactionDate >= %s
            AND administration = %s
            ORDER BY TransactionDate DESC
            LIMIT 100
        """
        
        params = [date_from, tenant]
        results = db.execute_query(query, params, fetch=True)
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'count': len(results) if results else 0,
            'data': results or []
        })
        
    except Exception as e:
        print(f"Error getting invoices: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@reporting_tenant_example_bp.route('/transactions', methods=['GET'])
@cognito_required(required_permissions=['transactions_read'])
@tenant_required()
def get_transactions_tenant_aware(user_email, user_roles, tenant, user_tenants):
    """
    Get transactions for current tenant
    
    Example using add_tenant_filter() helper
    """
    try:
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        date_from = request.args.get('dateFrom', '2024-01-01')
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        
        # Build base query
        query = """
            SELECT 
                ID,
                TransactionDate,
                TransactionAmount,
                TransactionDescription
            FROM mutaties
            WHERE TransactionDate BETWEEN %s AND %s
        """
        params = [date_from, date_to]
        
        # Add tenant filter using helper
        query, params = add_tenant_filter(query, params, tenant)
        
        # Add ordering
        query += " ORDER BY TransactionDate DESC"
        
        results = db.execute_query(query, params, fetch=True)
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'date_range': {'from': date_from, 'to': date_to},
            'count': len(results) if results else 0,
            'data': results or []
        })
        
    except Exception as e:
        print(f"Error getting transactions: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@reporting_tenant_example_bp.route('/financial-summary', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_financial_summary_tenant_aware(user_email, user_roles, tenant, user_tenants):
    """
    Get financial summary for current tenant
    
    Example with complex aggregation query
    """
    try:
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        
        # Query with tenant filter
        query = """
            SELECT 
                CASE 
                    WHEN Debet BETWEEN '4000' AND '4999' OR Credit BETWEEN '4000' AND '4999' THEN 'Revenue'
                    WHEN Debet BETWEEN '6000' AND '6999' OR Credit BETWEEN '6000' AND '6999' THEN 'Operating Expenses'
                    WHEN Debet BETWEEN '7000' AND '7999' OR Credit BETWEEN '7000' AND '7999' THEN 'Other Expenses'
                    WHEN Debet = '2010' OR Credit = '2010' THEN 'VAT'
                    ELSE 'Other'
                END as category,
                SUM(CASE 
                    WHEN Debet BETWEEN '4000' AND '8999' THEN -TransactionAmount
                    WHEN Credit BETWEEN '4000' AND '8999' THEN TransactionAmount
                    ELSE TransactionAmount
                END) as amount
            FROM mutaties
            WHERE TransactionDate BETWEEN %s AND %s
            AND administration = %s
            GROUP BY category
            HAVING ABS(amount) > 0.01
            ORDER BY ABS(amount) DESC
        """
        
        params = [date_from, date_to, tenant]
        results = db.execute_query(query, params, fetch=True)
        
        # Format data
        labels = [row['category'] for row in results] if results else []
        values = [float(row['amount']) for row in results] if results else []
        total = sum(abs(value) for value in values)
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'date_range': {'from': date_from, 'to': date_to},
            'data': {
                'labels': labels,
                'values': values,
                'total': total
            }
        })
        
    except Exception as e:
        print(f"Error getting financial summary: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@reporting_tenant_example_bp.route('/revenue-by-month', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_revenue_by_month_tenant_aware(user_email, user_roles, tenant, user_tenants):
    """
    Get monthly revenue for current tenant
    
    Example with date aggregation
    """
    try:
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        year = request.args.get('year', datetime.now().year)
        
        query = """
            SELECT 
                DATE_FORMAT(TransactionDate, '%Y-%m') as month,
                SUM(TransactionAmount) as total_revenue,
                COUNT(*) as transaction_count
            FROM mutaties
            WHERE YEAR(TransactionDate) = %s
            AND Credit BETWEEN '4000' AND '4999'
            AND administration = %s
            GROUP BY month
            ORDER BY month ASC
        """
        
        params = [year, tenant]
        results = db.execute_query(query, params, fetch=True)
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'year': year,
            'data': results or []
        })
        
    except Exception as e:
        print(f"Error getting revenue by month: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@reporting_tenant_example_bp.route('/account-balances', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_account_balances_tenant_aware(user_email, user_roles, tenant, user_tenants):
    """
    Get account balances for current tenant
    
    Example with JOIN and tenant filtering on multiple tables
    """
    try:
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        
        # Query with tenant filter on both tables
        query = """
            SELECT 
                r.AccountNumber,
                r.AccountName,
                SUM(CASE WHEN m.Debet = r.AccountNumber THEN m.TransactionAmount ELSE 0 END) as debet_total,
                SUM(CASE WHEN m.Credit = r.AccountNumber THEN m.TransactionAmount ELSE 0 END) as credit_total,
                SUM(CASE WHEN m.Debet = r.AccountNumber THEN m.TransactionAmount 
                         WHEN m.Credit = r.AccountNumber THEN -m.TransactionAmount 
                         ELSE 0 END) as balance
            FROM rekeningschema r
            LEFT JOIN mutaties m ON (m.Debet = r.AccountNumber OR m.Credit = r.AccountNumber)
                AND m.TransactionDate <= %s
                AND m.administration = %s
            WHERE r.administration = %s
            GROUP BY r.AccountNumber, r.AccountName
            HAVING ABS(balance) > 0.01
            ORDER BY r.AccountNumber
        """
        
        params = [date_to, tenant, tenant]
        results = db.execute_query(query, params, fetch=True)
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'as_of_date': date_to,
            'count': len(results) if results else 0,
            'data': results or []
        })
        
    except Exception as e:
        print(f"Error getting account balances: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@reporting_tenant_example_bp.route('/admin/all-tenants-summary', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
@tenant_required(allow_sysadmin=True)
def get_all_tenants_summary(user_email, user_roles, tenant, user_tenants):
    """
    Get summary across all tenants (SysAdmin only)
    
    Example with SysAdmin bypass
    """
    try:
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # SysAdmin can see all tenants
        if 'SysAdmin' in user_roles:
            query = """
                SELECT 
                    administration as tenant,
                    COUNT(*) as transaction_count,
                    SUM(TransactionAmount) as total_amount,
                    MIN(TransactionDate) as earliest_date,
                    MAX(TransactionDate) as latest_date
                FROM mutaties
                WHERE TransactionDate >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
                GROUP BY administration
                ORDER BY administration
            """
            params = []
        else:
            # Regular users only see their tenant
            query = """
                SELECT 
                    administration as tenant,
                    COUNT(*) as transaction_count,
                    SUM(TransactionAmount) as total_amount,
                    MIN(TransactionDate) as earliest_date,
                    MAX(TransactionDate) as latest_date
                FROM mutaties
                WHERE TransactionDate >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
                AND administration = %s
                GROUP BY administration
            """
            params = [tenant]
        
        results = db.execute_query(query, params, fetch=True)
        
        return jsonify({
            'success': True,
            'is_sysadmin': 'SysAdmin' in user_roles,
            'data': results or []
        })
        
    except Exception as e:
        print(f"Error getting all tenants summary: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
