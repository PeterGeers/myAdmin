"""
Migration Routes

Web endpoints for running database migrations.
These are temporary endpoints that can be removed after migration is complete.

SECURITY NOTE: The /migrate endpoint has NO authentication for one-time use.
Remove this file after migration is complete!
"""

from flask import Blueprint, jsonify, request
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.year_end_service import YearEndClosureService
from database import DatabaseManager
import os

migration_bp = Blueprint('migration', __name__)

# Get test mode from environment
flag = os.getenv('TEST_MODE', 'false').lower() == 'true'

# SECURITY: Set to True to enable unauthenticated migration endpoint
# IMPORTANT: Set back to False and redeploy after migration is complete!
ALLOW_UNAUTHENTICATED_MIGRATION = os.getenv('ALLOW_MIGRATION', 'false').lower() == 'true'


def get_years_needing_migration(db, administration=None):
    """Find years that have transactions but no opening balance records."""
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all years with transactions
    query = """
        SELECT DISTINCT 
            administration,
            YEAR(TransactionDate) as year
        FROM mutaties
        WHERE 1=1
    """
    
    if administration:
        query += " AND administration = %s"
        cursor.execute(query, (administration,))
    else:
        cursor.execute(query)
    
    all_years = cursor.fetchall()
    
    # Filter out years that already have opening balances
    years_needing_migration = []
    
    for row in all_years:
        admin = row['administration']
        year = row['year']
        
        # Check if opening balance exists
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM mutaties
            WHERE TransactionNumber = %s
            AND administration = %s
        """, (f'OpeningBalance {year}', admin))
        
        result = cursor.fetchone()
        if result['count'] == 0:
            years_needing_migration.append({'administration': admin, 'year': year})
    
    cursor.close()
    conn.close()
    
    return sorted(years_needing_migration, key=lambda x: (x['administration'], x['year']))


def get_first_year_with_transactions(db, administration):
    """Get the first year with transactions for an administration."""
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT MIN(YEAR(TransactionDate)) as first_year
        FROM mutaties
        WHERE administration = %s
    """, (administration,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return result['first_year'] if result else None


@migration_bp.route('/api/migration/opening-balances/preview', methods=['GET'])
@cognito_required(required_permissions=['admin'])
@tenant_required()
def preview_opening_balance_migration(user_email, user_roles, tenant, user_tenants):
    """
    Preview which years need opening balance migration.
    
    Query params:
        tenant: Optional - filter by specific tenant
    """
    try:
        db = DatabaseManager(test_mode=flag)
        
        # Get tenant filter from query params
        filter_tenant = request.args.get('tenant')
        
        # Validate user has access to requested tenant
        if filter_tenant and filter_tenant not in user_tenants:
            return jsonify({
                'success': False,
                'error': 'Access denied to specified tenant'
            }), 403
        
        years_to_migrate = get_years_needing_migration(db, filter_tenant)
        
        # Group by administration
        by_admin = {}
        for item in years_to_migrate:
            admin = item['administration']
            year = item['year']
            
            # Only include tenants user has access to
            if admin not in user_tenants:
                continue
            
            if admin not in by_admin:
                by_admin[admin] = []
            by_admin[admin].append(year)
        
        summary = []
        for admin, years in by_admin.items():
            first_year = get_first_year_with_transactions(db, admin)
            # Filter out first year (can't create opening balance for first year)
            years_to_process = [y for y in years if y != first_year]
            
            summary.append({
                'administration': admin,
                'years_needing_migration': years_to_process,
                'count': len(years_to_process),
                'first_year': first_year,
                'year_range': f"{min(years_to_process)}-{max(years_to_process)}" if years_to_process else "None"
            })
        
        return jsonify({
            'success': True,
            'summary': summary,
            'total_years': sum(s['count'] for s in summary)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@migration_bp.route('/api/migration/opening-balances/execute', methods=['POST'])
@cognito_required(required_permissions=['admin'])
@tenant_required()
def execute_opening_balance_migration(user_email, user_roles, tenant, user_tenants):
    """
    Execute opening balance migration for historical years.
    
    Body:
        {
            "tenant": "optional - specific tenant to migrate",
            "confirm": true - must be true to execute
        }
    """
    try:
        data = request.get_json()
        
        if not data.get('confirm'):
            return jsonify({
                'success': False,
                'error': 'Must set confirm=true to execute migration'
            }), 400
        
        filter_tenant = data.get('tenant')
        
        # Validate user has access to requested tenant
        if filter_tenant and filter_tenant not in user_tenants:
            return jsonify({
                'success': False,
                'error': 'Access denied to specified tenant'
            }), 403
        
        db = DatabaseManager(test_mode=flag)
        service = YearEndClosureService()
        
        years_to_migrate = get_years_needing_migration(db, filter_tenant)
        
        # Filter by user access
        years_to_migrate = [
            item for item in years_to_migrate 
            if item['administration'] in user_tenants
        ]
        
        results = []
        success_count = 0
        error_count = 0
        
        for item in years_to_migrate:
            admin = item['administration']
            year = item['year']
            
            # Skip first year
            first_year = get_first_year_with_transactions(db, admin)
            if year == first_year:
                results.append({
                    'administration': admin,
                    'year': year,
                    'status': 'skipped',
                    'reason': 'First year with transactions'
                })
                continue
            
            try:
                # Create opening balance
                result = service._create_opening_balances(admin, year)
                
                if result['success']:
                    results.append({
                        'administration': admin,
                        'year': year,
                        'status': 'success',
                        'transaction_number': result['transaction_number'],
                        'account_count': result['account_count']
                    })
                    success_count += 1
                else:
                    results.append({
                        'administration': admin,
                        'year': year,
                        'status': 'success',
                        'reason': 'No opening balance needed (all balances zero)'
                    })
                    success_count += 1
                    
            except Exception as e:
                results.append({
                    'administration': admin,
                    'year': year,
                    'status': 'error',
                    'error': str(e)
                })
                error_count += 1
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_processed': len(results),
                'successful': success_count,
                'errors': error_count,
                'skipped': len([r for r in results if r['status'] == 'skipped'])
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@migration_bp.route('/api/migration/opening-balances/migrate', methods=['POST'])
def migrate_opening_balances_unauthenticated():
    """
    ONE-TIME MIGRATION ENDPOINT - NO AUTHENTICATION
    
    This endpoint is for one-time use to migrate historical opening balances.
    It requires ALLOW_MIGRATION=true environment variable to be set.
    
    SECURITY: Remove this endpoint after migration is complete!
    
    Body:
        {
            "secret": "migrate-opening-balances-2026",
            "tenant": "optional - specific tenant",
            "dry_run": false
        }
    """
    if not ALLOW_UNAUTHENTICATED_MIGRATION:
        return jsonify({
            'success': False,
            'error': 'Migration endpoint is disabled. Set ALLOW_MIGRATION=true in Railway environment variables.'
        }), 403
    
    try:
        data = request.get_json() or {}
        
        # Simple secret check
        if data.get('secret') != 'migrate-opening-balances-2026':
            return jsonify({
                'success': False,
                'error': 'Invalid secret'
            }), 403
        
        dry_run = data.get('dry_run', False)
        filter_tenant = data.get('tenant')
        
        db = DatabaseManager(test_mode=flag)
        service = YearEndClosureService()
        
        years_to_migrate = get_years_needing_migration(db, filter_tenant)
        
        if not years_to_migrate:
            return jsonify({
                'success': True,
                'message': 'No years need migration - all years already have opening balances',
                'results': []
            })
        
        # Group by administration for preview
        by_admin = {}
        for item in years_to_migrate:
            admin = item['administration']
            year = item['year']
            if admin not in by_admin:
                by_admin[admin] = []
            by_admin[admin].append(year)
        
        preview = []
        for admin, years in by_admin.items():
            first_year = get_first_year_with_transactions(db, admin)
            years_to_process = [y for y in years if y != first_year]
            preview.append({
                'administration': admin,
                'years': years_to_process,
                'count': len(years_to_process)
            })
        
        if dry_run:
            return jsonify({
                'success': True,
                'dry_run': True,
                'message': 'Dry run - no changes made',
                'preview': preview,
                'total_years': sum(p['count'] for p in preview)
            })
        
        # Execute migration
        results = []
        success_count = 0
        error_count = 0
        
        for item in years_to_migrate:
            admin = item['administration']
            year = item['year']
            
            # Skip first year
            first_year = get_first_year_with_transactions(db, admin)
            if year == first_year:
                results.append({
                    'administration': admin,
                    'year': year,
                    'status': 'skipped',
                    'reason': 'First year with transactions'
                })
                continue
            
            try:
                # Create opening balance
                result = service._create_opening_balances(admin, year)
                
                if result['success']:
                    results.append({
                        'administration': admin,
                        'year': year,
                        'status': 'success',
                        'transaction_number': result['transaction_number'],
                        'account_count': result['account_count']
                    })
                    success_count += 1
                else:
                    results.append({
                        'administration': admin,
                        'year': year,
                        'status': 'success',
                        'reason': 'No opening balance needed (all balances zero)'
                    })
                    success_count += 1
                    
            except Exception as e:
                results.append({
                    'administration': admin,
                    'year': year,
                    'status': 'error',
                    'error': str(e)
                })
                error_count += 1
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_processed': len(results),
                'successful': success_count,
                'errors': error_count,
                'skipped': len([r for r in results if r['status'] == 'skipped'])
            },
            'message': f'Migration complete: {success_count} successful, {error_count} errors'
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
