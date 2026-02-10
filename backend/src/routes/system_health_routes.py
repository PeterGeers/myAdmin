"""
System Health Routes Blueprint

Handles health check, status, and monitoring endpoints.
Extracted from app.py during refactoring (Phase 1.2)
"""

from flask import Blueprint, jsonify
from auth.cognito_utils import cognito_required
from database import DatabaseManager
import os

system_health_bp = Blueprint('system_health', __name__)

# Access to scalability_manager from app.py
# This will be set by app.py after blueprint registration
scalability_manager = None

def set_scalability_manager(manager):
    """Set the scalability manager reference from app.py"""
    global scalability_manager
    scalability_manager = manager



@system_health_bp.route('/api/test', methods=['GET'])
@cognito_required(required_permissions=[])
def test(user_email, user_roles):
    """Test endpoint"""
    print("Test endpoint called", flush=True)
    return jsonify({'status': 'Server is working'})


@system_health_bp.route('/api/status', methods=['GET'])
def get_status():
    """Get environment status - Public endpoint (no authentication required)"""
    try:
        use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db_name = os.getenv('TEST_DB_NAME', 'testfinance') if use_test else os.getenv('DB_NAME', 'finance')
        folder_name = os.getenv('TEST_FACTUREN_FOLDER_NAME', 'testFacturen') if use_test else os.getenv('FACTUREN_FOLDER_NAME', 'Facturen')
        
        return jsonify({
            'status': 'ok',
            'mode': 'Test' if use_test else 'Production',
            'database': db_name,
            'folder': folder_name
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@system_health_bp.route('/api/str/test', methods=['GET'])
@cognito_required(required_permissions=[])
def str_test(user_email, user_roles):
    """STR test endpoint"""
    print("STR test endpoint called", flush=True)
    return jsonify({'status': 'STR endpoints working', 'openpyxl_available': True})


@system_health_bp.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint with scalability information - No authentication required"""
    health_info = {
        'status': 'healthy', 
        'endpoints': ['str/upload', 'str/scan-files', 'str/process-files', 'str/save', 'str/write-future'],
        'scalability': {
            'manager_active': scalability_manager is not None,
            'concurrent_user_capacity': '10x baseline' if scalability_manager else '1x baseline'
        }
    }
    
    if scalability_manager:
        health_status = scalability_manager.get_health_status()
        health_info['scalability'].update({
            'health_score': health_status['health_score'],
            'status': health_status['status'],
            'scalability_ready': health_status['scalability_ready']
        })
    
    return jsonify(health_info)



@system_health_bp.route('/api/google-drive/token-health', methods=['GET'])
@cognito_required(required_roles=['SysAdmin', 'Tenant_Admin'])
def google_drive_token_health(user_email, user_roles):
    """Check Google Drive token health for all tenants"""
    from datetime import datetime
    from services.credential_service import CredentialService
    
    try:
        db = DatabaseManager()
        credential_service = CredentialService(db)
        
        tenants = ['GoodwinSolutions', 'PeterPrive']
        results = {}
        
        for tenant in tenants:
            try:
                token_data = credential_service.get_credential(tenant, 'google_drive_token')
                
                if not token_data or 'expiry' not in token_data:
                    results[tenant] = {
                        'status': 'error',
                        'message': 'Token not found',
                        'action_required': True
                    }
                    continue
                
                # Parse expiry date
                expiry_str = token_data['expiry']
                try:
                    expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                except:
                    try:
                        expiry_date = datetime.strptime(expiry_str, "%d-%m-%Y %H:%M:%S")
                    except:
                        results[tenant] = {
                            'status': 'error',
                            'message': f'Invalid expiry format: {expiry_str}',
                            'action_required': True
                        }
                        continue
                
                now = datetime.now()
                if expiry_date.tzinfo:
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                
                days_until_expiry = (expiry_date - now).days
                
                if days_until_expiry < 0:
                    results[tenant] = {
                        'status': 'expired',
                        'message': f'Token expired {abs(days_until_expiry)} days ago',
                        'expiry_date': expiry_str,
                        'action_required': True,
                        'recovery_steps': [
                            'python backend/refresh_google_token.py',
                            f'python scripts/credentials/migrate_credentials_to_db.py --tenant {tenant}',
                            'docker-compose restart backend'
                        ]
                    }
                elif days_until_expiry <= 7:
                    results[tenant] = {
                        'status': 'warning',
                        'message': f'Token expires in {days_until_expiry} days',
                        'expiry_date': expiry_str,
                        'action_required': False,
                        'recommendation': 'Refresh token soon'
                    }
                else:
                    results[tenant] = {
                        'status': 'healthy',
                        'message': f'Token valid for {days_until_expiry} days',
                        'expiry_date': expiry_str,
                        'action_required': False
                    }
            
            except Exception as e:
                results[tenant] = {
                    'status': 'error',
                    'message': str(e),
                    'action_required': True
                }
        
        # Overall status
        overall_status = 'healthy'
        if any(r['status'] == 'expired' for r in results.values()):
            overall_status = 'critical'
        elif any(r['status'] == 'warning' for r in results.values()):
            overall_status = 'warning'
        elif any(r['status'] == 'error' for r in results.values()):
            overall_status = 'error'
        
        return jsonify({
            'overall_status': overall_status,
            'tenants': results,
            'checked_at': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'overall_status': 'error',
            'message': str(e)
        }), 500
