"""
Cache Management Routes Blueprint

Handles cache warmup, refresh, invalidate, and status endpoints for both
mutaties cache and BNB cache.
Extracted from app.py during refactoring (Phase 1.3)
"""

from flask import Blueprint, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from mutaties_cache import get_cache, invalidate_cache
from bnb_cache import get_bnb_cache

cache_bp = Blueprint('cache', __name__)

# Access to flag from app.py (test mode)
# This will be set by app.py after blueprint registration
flag = False

def set_test_mode(test_mode):
    """Set the test mode flag from app.py"""
    global flag
    flag = test_mode


# Cache Management Endpoints
@cache_bp.route('/api/cache/warmup', methods=['POST'])
@cognito_required(required_permissions=['actuals_read'])
def cache_warmup(user_email, user_roles):
    """Warmup the cache (load it if not already loaded)"""
    try:
        cache = get_cache()
        
        # Check if cache is already loaded
        if cache.data is not None:
            return jsonify({
                'success': True,
                'message': 'Cache already loaded',
                'record_count': len(cache.data),
                'last_refresh': cache.last_loaded.isoformat() if cache.last_loaded else None
            })
        
        # Load the cache
        db = DatabaseManager(test_mode=flag)
        cache.get_data(db)
        
        return jsonify({
            'success': True,
            'message': 'Cache loaded successfully',
            'record_count': len(cache.data),
            'last_refresh': cache.last_loaded.isoformat() if cache.last_loaded else None
        })
    except Exception as e:
        print(f"Error in cache_warmup: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@cache_bp.route('/api/cache/status', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def cache_status(user_email, user_roles):
    """Get cache status and statistics"""
    try:
        cache = get_cache()
        
        return jsonify({
            'success': True,
            'cache_active': cache.data is not None,
            'last_refresh': cache.last_loaded.isoformat() if cache.last_loaded else None,
            'record_count': len(cache.data) if cache.data is not None else 0,
            'auto_refresh_enabled': True,
            'refresh_threshold_minutes': 30
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@cache_bp.route('/api/cache/refresh', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
@tenant_required(allow_sysadmin=True)
def cache_refresh(user_email, user_roles, tenant, user_tenants):
    """Force refresh the cache"""
    try:
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)
        
        # Force refresh by invalidating and then getting data
        cache.invalidate()
        cache.get_data(db)  # This will trigger a refresh
        
        return jsonify({
            'success': True,
            'message': 'Cache refreshed successfully',
            'record_count': len(cache.data),
            'last_refresh': cache.last_loaded.isoformat() if cache.last_loaded else None
        })
    except Exception as e:
        print(f"Error in cache_refresh: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@cache_bp.route('/api/cache/invalidate', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
@tenant_required(allow_sysadmin=True)
def cache_invalidate_endpoint(user_email, user_roles, tenant, user_tenants):
    """Invalidate the cache (will auto-refresh on next query)"""
    try:
        invalidate_cache()
        
        return jsonify({
            'success': True,
            'message': 'Cache invalidated successfully'
        })
    except Exception as e:
        print(f"Error in cache_invalidate: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# BNB Cache Management Endpoints
@cache_bp.route('/api/bnb-cache/status', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def bnb_cache_status(user_email, user_roles):
    """Get BNB cache status and statistics"""
    try:
        bnb_cache = get_bnb_cache()
        status = bnb_cache.get_status()
        
        return jsonify({
            'success': True,
            **status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@cache_bp.route('/api/bnb-cache/refresh', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def bnb_cache_refresh(user_email, user_roles):
    """Force refresh the BNB cache"""
    try:
        bnb_cache = get_bnb_cache()
        db = DatabaseManager(test_mode=flag)
        
        # Force refresh
        bnb_cache.refresh(db)
        status = bnb_cache.get_status()
        
        return jsonify({
            'success': True,
            'message': 'BNB cache refreshed successfully',
            **status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@cache_bp.route('/api/bnb-cache/invalidate', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def bnb_cache_invalidate(user_email, user_roles):
    """Invalidate the BNB cache (will auto-refresh on next query)"""
    try:
        bnb_cache = get_bnb_cache()
        bnb_cache.invalidate()
        
        return jsonify({
            'success': True,
            'message': 'BNB cache invalidated successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
