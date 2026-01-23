from flask import Blueprint, request, jsonify
import os
from dotenv import load_dotenv
from api_schemas import validate_response_schema
from mutaties_cache import get_cache
from database import DatabaseManager
from auth.cognito_utils import cognito_required

load_dotenv()

actuals_bp = Blueprint('actuals', __name__)

@actuals_bp.route('/actuals-balance', methods=['GET'])
@cognito_required(required_permissions=['actuals_read'])
def get_actuals_balance(user_email, user_roles):
    """Get balance data using in-memory cache"""
    try:
        years = request.args.get('years', '2025').split(',')
        administration = request.args.get('administration', 'all')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=test_mode)
        
        # Get cached data
        df = cache.get_data(db)
        
        # Filter: VW = 'N' (balance accounts)
        filtered = df[df['VW'] == 'N'].copy()
        
        # Filter by administration
        if administration != 'all':
            filtered = filtered[filtered['Administration'] == administration]
        
        # Filter by year: from beginning up to max selected year
        max_year = max([int(y) for y in years])
        filtered = filtered[filtered['jaar'] <= max_year]
        
        # Group by Parent and ledger
        grouped = filtered.groupby(['Parent', 'ledger'], as_index=False).agg({
            'Amount': 'sum'
        })
        
        # Filter out zero amounts
        grouped = grouped[grouped['Amount'] != 0]
        
        # Sort by Parent and ledger
        grouped = grouped.sort_values(['Parent', 'ledger'])
        
        # Convert to list of dicts
        results = grouped.to_dict('records')
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@actuals_bp.route('/actuals-profitloss', methods=['GET'])
@cognito_required(required_permissions=['actuals_read'])
def get_actuals_profitloss(user_email, user_roles):
    """Get profit/loss data using in-memory cache"""
    try:
        years = request.args.get('years', '2025').split(',')
        administration = request.args.get('administration', 'all')
        group_by = request.args.get('groupBy', 'year')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        # Get cache instance
        cache = get_cache()
        db = DatabaseManager(test_mode=test_mode)
        
        # Get cached data
        df = cache.get_data(db)
        
        # Filter: VW = 'Y' (profit/loss accounts)
        filtered = df[df['VW'] == 'Y'].copy()
        
        # Filter by administration
        if administration != 'all':
            filtered = filtered[filtered['Administration'] == administration]
        
        # Filter by years
        year_list = [int(y) for y in years]
        filtered = filtered[filtered['jaar'].isin(year_list)]
        
        # Group based on groupBy parameter
        if group_by == 'quarter':
            group_cols = ['Parent', 'ledger', 'jaar', 'kwartaal']
            sort_cols = ['Parent', 'ledger', 'jaar', 'kwartaal']
        elif group_by == 'month':
            group_cols = ['Parent', 'ledger', 'jaar', 'maand']
            sort_cols = ['Parent', 'ledger', 'jaar', 'maand']
        else:  # Default to year
            group_cols = ['Parent', 'ledger', 'jaar']
            sort_cols = ['Parent', 'ledger', 'jaar']
        
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
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

