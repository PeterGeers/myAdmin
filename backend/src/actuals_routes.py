from flask import Blueprint, request, jsonify
import os
import logging
from dotenv import load_dotenv
from api_schemas import validate_response_schema
from mutaties_cache import get_cache
from database import DatabaseManager
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
# testnow for the second time
load_dotenv()

actuals_bp = Blueprint('actuals', __name__)

@actuals_bp.route('/actuals-balance', methods=['GET'])
@cognito_required(required_permissions=['actuals_read'])
@tenant_required()
def get_actuals_balance(user_email, user_roles, tenant, user_tenants):
    """Get balance data using in-memory cache.
    
    Query params:
        years: comma-separated year list (default: '2025')
        administration: tenant filter (default: current tenant)
        per_year: when 'true', returns year-bucketed data with closedYears array
        testMode: when 'true', uses test database
    """
    try:
        years = request.args.get('years', '2025').split(',')
        administration = request.args.get('administration', tenant)
        per_year = request.args.get('per_year', 'false').lower() == 'true'
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        # Validate user has access to requested administration
        if administration != 'all' and administration not in user_tenants:
            return jsonify({
                'success': False,
                'error': 'Access denied to administration'
            }), 403
        
        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=test_mode)
        
        # Get cached data — ensure requested years are loaded
        year_list = [int(y) for y in years]
        df = cache.get_data(db, requested_years=year_list)
        
        # SECURITY: Filter by user's accessible tenants first
        df = df[df['administration'].isin(user_tenants)]
        
        # Filter: VW = 'N' (balance accounts)
        filtered = df[df['VW'] == 'N'].copy()
        
        # Filter by administration
        if administration != 'all':
            filtered = filtered[filtered['administration'] == administration]
        
        if per_year:
            # Year-bucketed mode: return one row per (Parent, Reknum, AccountName, jaar)
            # with year-end closure awareness
            
            # Query closed years for this administration
            closed_years = _get_closed_years(db, administration if administration != 'all' else tenant)
            
            results = []
            for year in year_list:
                if year in closed_years:
                    # Closed year: only transactions within that specific year
                    year_df = filtered[filtered['jaar'] == year]
                else:
                    # Open year: cumulative from start through this year
                    year_df = filtered[filtered['jaar'] <= year]
                
                # Group by Parent, Reknum, AccountName for this year
                if len(year_df) > 0:
                    grouped = year_df.groupby(['Parent', 'Reknum', 'AccountName'], as_index=False).agg({
                        'Amount': 'sum'
                    })
                    grouped = grouped[grouped['Amount'] != 0]
                    grouped['jaar'] = year
                    results.extend(grouped.to_dict('records'))
            
            # Sort by Parent, Reknum, jaar
            results.sort(key=lambda r: (r.get('Parent', ''), r.get('Reknum', ''), r.get('jaar', 0)))
            
            return jsonify({
                'success': True,
                'data': results,
                'closedYears': closed_years
            })
        else:
            # Original behavior: sum across all years up to max selected year
            max_year = max(year_list)
            filtered = filtered[filtered['jaar'] <= max_year]
            
            grouped = filtered.groupby(['Parent', 'Reknum', 'AccountName'], as_index=False).agg({
                'Amount': 'sum'
            })
            grouped = grouped[grouped['Amount'] != 0]
            grouped = grouped.sort_values(['Parent', 'Reknum'])
            results = grouped.to_dict('records')
            
            return jsonify({
                'success': True,
                'data': results
            })
        
    except Exception as e:
        logging.error(f"Error in get_actuals_balance: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _get_closed_years(db, administration):
    """Query year_closure_status table to get list of closed year integers for an administration.
    
    Args:
        db: DatabaseManager instance
        administration: tenant identifier
        
    Returns:
        list[int]: closed year numbers, e.g. [2023, 2024]
    """
    try:
        query = """
            SELECT DISTINCT year
            FROM year_closure_status
            WHERE administration = %s
            ORDER BY year
        """
        rows = db.execute_query(query, [administration])
        return [int(row['year']) for row in rows] if rows else []
    except Exception as e:
        logging.warning(f"Could not fetch closed years for {administration}: {e}")
        return []

@actuals_bp.route('/actuals-profitloss', methods=['GET'])
@cognito_required(required_permissions=['actuals_read'])
@tenant_required()
def get_actuals_profitloss(user_email, user_roles, tenant, user_tenants):
    """Get profit/loss data using in-memory cache"""
    try:
        years = request.args.get('years', '2025').split(',')
        administration = request.args.get('administration', tenant)
        group_by = request.args.get('groupBy', 'year')
        include_ref = request.args.get('includeRef', 'false').lower() == 'true'
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        # Validate user has access to requested administration
        if administration != 'all' and administration not in user_tenants:
            return jsonify({
                'success': False,
                'error': 'Access denied to administration'
            }), 403
        
        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=test_mode)
        
        # Get cached data — ensure requested years are loaded
        year_list = [int(y) for y in years]
        df = cache.get_data(db, requested_years=year_list)
        
        # SECURITY: Filter by user's accessible tenants first
        df = df[df['administration'].isin(user_tenants)]
        
        # Filter: VW = 'Y' (profit/loss accounts)
        filtered = df[df['VW'] == 'Y'].copy()
        
        # Filter by administration
        if administration != 'all':
            filtered = filtered[filtered['administration'] == administration]
        
        # Filter by years
        year_list = [int(y) for y in years]
        filtered = filtered[filtered['jaar'].isin(year_list)]
        
        # Group based on groupBy parameter
        if group_by == 'quarter':
            group_cols = ['Parent', 'Reknum', 'AccountName', 'jaar', 'kwartaal']
            sort_cols = ['Parent', 'Reknum', 'jaar', 'kwartaal']
        elif group_by == 'month':
            group_cols = ['Parent', 'Reknum', 'AccountName', 'jaar', 'maand']
            sort_cols = ['Parent', 'Reknum', 'jaar', 'maand']
        else:  # Default to year
            group_cols = ['Parent', 'Reknum', 'AccountName', 'jaar']
            sort_cols = ['Parent', 'Reknum', 'jaar']
        
        # When includeRef=true, add ReferenceNumber to grouping so individual
        # transactions are returned for ledger-level drill-down
        if include_ref:
            group_cols.append('ReferenceNumber')
        
        # Group and aggregate
        grouped = filtered.groupby(group_cols, as_index=False).agg({
            'Amount': 'sum'
        })
        
        # Filter out zero amounts
        grouped = grouped[grouped['Amount'] != 0]
        
        # Sort
        grouped = grouped.sort_values(sort_cols)
        
        # Convert to list of dicts
        results = grouped.to_dict('records')
        
        # Validate response schema
        validate_response_schema('/api/reports/actuals-profitloss', results)
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        logging.error(f"Error in get_actuals_profitloss: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

