from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from config import Config
from flasgger import Swagger
import yaml
import os
from dotenv import load_dotenv
from pdf_processor import PDFProcessor
from transaction_logic import TransactionLogic
from google_drive_service import GoogleDriveService
from banking_processor import BankingProcessor
from str_processor import STRProcessor
from str_database import STRDatabase
from database import DatabaseManager
from btw_processor import BTWProcessor
from toeristenbelasting_processor import ToeristenbelastingProcessor
from pdf_validation import PDFValidator
from reporting_routes import reporting_bp
from actuals_routes import actuals_bp
from bnb_routes import bnb_bp
from str_channel_routes import str_channel_bp
from str_invoice_routes import str_invoice_bp
from routes.missing_invoices_routes import missing_invoices_bp
from audit_routes import audit_bp
from admin_routes import admin_bp
from pattern_storage_routes import pattern_storage_bp
from scalability_routes import scalability_bp
from tenant_admin_routes import tenant_admin_bp
from tenant_module_routes import tenant_module_bp
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required

from xlsx_export import XLSXExportProcessor
from route_validator import check_route_conflicts
from error_handlers import configure_logging, register_error_handlers, error_response
from performance_optimizer import performance_middleware, register_performance_endpoints
from security_audit import SecurityAudit, register_security_endpoints
from mutaties_cache import get_cache, invalidate_cache
from bnb_cache import get_bnb_cache
from report_generators import generate_table_rows
from services.template_service import TemplateService

# Load environment variables from .env file
load_dotenv()
from duplicate_checker import DuplicateChecker
import os
from datetime import datetime
from werkzeug.utils import secure_filename

# Create Flask app without static folder to prevent route conflicts
app = Flask(__name__, static_folder=None)

# Configure timeouts for long-running operations and scalability
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['PERMANENT_SESSION_LIFETIME'] = 300  # 5 minutes

# Scalability configurations
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # Disable pretty printing for performance
app.config['JSON_SORT_KEYS'] = False  # Disable key sorting for performance

# MODE CONFIGURATION
# Set flag = True for TEST mode (uses mutaties_test table, local storage)
# Set flag = False for PRODUCTION mode (uses mutaties table, Google Drive)
flag = False

# Initialize scalability manager early
try:
    # Temporarily disable scalability manager to avoid database pool issues
    scalability_manager = None
    print("⚠️ Scalability Manager disabled to avoid database pool issues", flush=True)
    
    # from scalability_manager import initialize_scalability, ScalabilityConfig
    # from database import DatabaseManager
    
    # # Get database configuration
    # db_manager = DatabaseManager(test_mode=flag)
    # db_config = db_manager.config
    
    # # Initialize with optimized configuration for 10x concurrency
    # scalability_config = ScalabilityConfig(
    #     db_pool_size=20,  # Reduced to avoid pool size errors
    #     db_max_overflow=40,
    #     max_worker_threads=50,  # Reduced to avoid resource issues
    #     io_thread_pool_size=25,
    #     cpu_thread_pool_size=10,
    #     async_queue_size=500,
    #     batch_processing_size=50
    # )
    
    # scalability_manager = initialize_scalability(db_config, scalability_config)
    # print("🚀 Scalability Manager initialized for 10x concurrent user support", flush=True)
    
except Exception as e:
    print(f"⚠️ Scalability Manager initialization failed: {e}", flush=True)
    scalability_manager = None

build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')

# Register API blueprints IMMEDIATELY after app creation
app.register_blueprint(reporting_bp, url_prefix='/api/reports')
app.register_blueprint(actuals_bp, url_prefix='/api/reports')
app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
app.register_blueprint(str_channel_bp, url_prefix='/api/str-channel')
app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
app.register_blueprint(missing_invoices_bp)
app.register_blueprint(audit_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(pattern_storage_bp)
app.register_blueprint(scalability_bp)
app.register_blueprint(tenant_admin_bp)
app.register_blueprint(tenant_module_bp)


# Configure Swagger UI
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec_1',
            "route": '/apispec_1.json',
            "rule_filter": lambda rule: True,  # all in
            "model_filter": lambda tag: True,  # all in
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/"
}

# Load OpenAPI spec from YAML file
try:
    with open('openapi_spec.yaml', 'r') as f:
        template = yaml.safe_load(f)
    app.config['SWAGGER'] = {
        'title': 'myAdmin API',
        'uiversion': 3,
        'specs_route': '/apidocs/',
        'openapi': '3.0.2'
    }
    swagger = Swagger(app, template=template)
except Exception as e:
    print(f"Warning: Could not load OpenAPI spec: {e}")
    swagger = Swagger(app, config=swagger_config)

CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:5000", "null"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Configure logging
logger = configure_logging(app)

# Register error handlers
register_error_handlers(app)

# Add performance middleware
performance_middleware(app)

# Register performance endpoints
register_performance_endpoints(app)

# Add security middleware and endpoints
security_audit = SecurityAudit()
security_audit.create_security_middleware(app)
register_security_endpoints(app)

# In-memory cache for uploaded files to prevent duplicates during session
upload_cache = {}

config = Config(test_mode=flag)
processor = PDFProcessor(test_mode=flag)
transaction_logic = TransactionLogic(test_mode=flag)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'csv', 'mhtml', 'eml'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def check_for_early_duplicates(filename, folder_name, drive_result):
    """
    Check for duplicate files before processing to prevent unnecessary work.
    This is an early check based on filename and folder.
    """
    try:
        # Initialize database connection
        db = DatabaseManager(test_mode=flag)
        
        # Check if this exact file already exists in the database
        # Look for transactions with the same filename in Ref4 and same folder in ReferenceNumber
        query = """
            SELECT ID, TransactionDate, TransactionAmount, TransactionDescription, Ref3, Ref4
            FROM mutaties 
            WHERE Ref4 = %s 
            AND ReferenceNumber = %s
            AND TransactionDate > (CURDATE() - INTERVAL 6 MONTH)
            ORDER BY ID DESC
            LIMIT 5
        """
        
        results = db.execute_query(query, (filename, folder_name), fetch=True)
        
        if results and len(results) > 0:
            # Found potential duplicates
            duplicate_info = {
                'has_duplicates': True,
                'duplicate_count': len(results),
                'existing_transactions': []
            }
            
            for result in results:
                duplicate_info['existing_transactions'].append({
                    'id': result.get('ID'),
                    'date': str(result.get('TransactionDate', '')),
                    'amount': float(result.get('TransactionAmount', 0)),
                    'description': result.get('TransactionDescription', ''),
                    'file_url': result.get('Ref3', ''),
                    'filename': result.get('Ref4', '')
                })
            
            return {
                'has_duplicates': True,
                'message': f'File "{filename}" already exists in folder "{folder_name}". Found {len(results)} matching transactions.',
                'duplicate_info': duplicate_info
            }
        
        return {
            'has_duplicates': False,
            'message': 'No duplicates found',
            'duplicate_info': None
        }
        
    except Exception as e:
        print(f"Error in early duplicate check: {e}", flush=True)
        # On error, allow processing to continue (graceful degradation)
        return {
            'has_duplicates': False,
            'message': f'Duplicate check failed: {e}',
            'duplicate_info': None
        }

# Serve static files
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files from React build"""
    static_folder = '/app/frontend/build/static'
    return send_from_directory(static_folder, filename)

@app.route('/backend-static/<path:filename>')
def serve_backend_static(filename):
    """Serve backend static files"""
    backend_static_folder = '/app/static'
    return send_from_directory(backend_static_folder, filename)

@app.route('/manifest.json')
def serve_manifest():
    """Serve React manifest.json"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'manifest.json')

@app.route('/favicon.ico')
def serve_favicon():
    """Serve React favicon"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'favicon.ico')

@app.route('/logo192.png')
def serve_logo192():
    """Serve React logo192.png"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'logo192.png')

@app.route('/logo512.png')
def serve_logo512():
    """Serve React logo512.png"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'logo512.png')

@app.route('/jabaki-logo.png')
def serve_jabaki_logo():
    """Serve Jabaki logo"""
    build_folder = '/app/frontend/build'
    return send_from_directory(build_folder, 'jabaki-logo.png')

@app.route('/config.js')
def serve_config():
    """Serve React config.js"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'config.js')



# Serve React build files
@app.route('/')
def serve_index():
    """Serve React index.html"""
    build_folder = '/app/frontend/build'
    try:
        return send_from_directory(build_folder, 'index.html')
    except Exception as e:
        return jsonify({'error': 'Frontend not built', 'details': str(e)}), 404

@app.errorhandler(404)
def handle_404(e):
    """Handle 404 errors by serving React app for non-API routes"""
    # For API routes, return JSON error - DO NOT serve HTML
    if request.path.startswith('/api/'):
        print(f"404 API route: {request.path}", flush=True)
        return jsonify({'error': 'API endpoint not found', 'path': request.path}), 404
    
    # Only serve React app for non-API routes
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'build')
    try:
        return send_from_directory(build_folder, 'index.html')
    except:
        return jsonify({'error': 'Frontend not built'}), 404

@app.route('/api/folders', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def get_folders(user_email, user_roles):
    """Return available vendor folders with optional regex filtering"""
    try:
        # Get tenant from request header
        from auth.tenant_context import get_current_tenant
        tenant = get_current_tenant(request)
        
        if not tenant:
            return jsonify({'error': 'No tenant specified. Please select a tenant.'}), 400
        
        regex_pattern = request.args.get('regex')
        print(f"get_folders called for tenant={tenant}, flag={flag}, regex={regex_pattern}", flush=True)
        
        if flag:  # Test mode - use local folders
            folders = list(config.vendor_folders.values())
            print(f"Test mode: returning {len(folders)} local folders", flush=True)
        else:  # Production mode - use Google Drive folders
            try:
                print(f"Production mode: fetching Google Drive folders for tenant={tenant}", flush=True)
                drive_service = GoogleDriveService(administration=tenant)
                drive_folders = drive_service.list_subfolders()
                print(f"Raw drive_folders result: {type(drive_folders)}, length: {len(drive_folders) if drive_folders else 0}", flush=True)
                
                # Extract folder names and deduplicate (Google Drive allows duplicate folder names)
                folder_names = [folder['name'] for folder in drive_folders]
                # Use dict.fromkeys() to preserve order while removing duplicates
                folders = list(dict.fromkeys(folder_names))
                
                if len(folder_names) != len(folders):
                    print(f"Warning: Deduplicated {len(folder_names)} folders to {len(folders)} unique names", flush=True)
                    # Log which folders were duplicated
                    from collections import Counter
                    duplicates = [name for name, count in Counter(folder_names).items() if count > 1]
                    print(f"Duplicate folder names found: {duplicates}", flush=True)
                
                print(f"Google Drive: found {len(folders)} unique folders for tenant={tenant}", flush=True)
            except Exception as e:
                print(f"Google Drive error for tenant={tenant}: {type(e).__name__}: {e}", flush=True)
                import traceback
                traceback.print_exc()
                # Fallback to local folders if Google Drive fails
                folders = list(config.vendor_folders.values())
                print(f"Fallback: returning {len(folders)} local folders", flush=True)
        
        # Apply regex filter if provided
        if regex_pattern:
            import re
            try:
                compiled_regex = re.compile(regex_pattern, re.IGNORECASE)
                filtered_folders = [folder for folder in folders if compiled_regex.search(folder)]
                print(f"Regex '{regex_pattern}' filtered {len(folders)} folders to {len(filtered_folders)}", flush=True)
                folders = filtered_folders
            except re.error as e:
                print(f"Invalid regex pattern '{regex_pattern}': {e}", flush=True)
                return jsonify({'error': f'Invalid regex pattern: {e}'}), 400
        
        return jsonify(folders)
    except Exception as e:
        print(f"Error in get_folders: {e}", flush=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/test', methods=['GET'])
@cognito_required(required_permissions=[])
def test(user_email, user_roles):
    """Test endpoint"""
    print("Test endpoint called", flush=True)
    return jsonify({'status': 'Server is working'})

@app.route('/api/status', methods=['GET'])
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

@app.route('/api/str/test', methods=['GET'])
@cognito_required(required_permissions=[])
def str_test(user_email, user_roles):
    """STR test endpoint"""
    print("STR test endpoint called", flush=True)
    return jsonify({'status': 'STR endpoints working', 'openpyxl_available': True})

@app.route('/api/health', methods=['GET'])
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

@app.route('/api/google-drive/token-health', methods=['GET'])
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

@app.route('/api/scalability/status', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def scalability_status(user_email, user_roles):
    """Get comprehensive scalability status"""
    if not scalability_manager:
        return jsonify({
            'scalability_active': False,
            'message': 'Scalability manager not initialized',
            'concurrent_capacity': '1x baseline'
        }), 503
    
    try:
        stats = scalability_manager.get_comprehensive_statistics()
        health = scalability_manager.get_health_status()
        
        return jsonify({
            'scalability_active': True,
            'health': health,
            'statistics': stats,
            'concurrent_capacity': '10x baseline',
            'performance_ready': health['scalability_ready']
        })
        
    except Exception as e:
        return jsonify({
            'scalability_active': False,
            'error': str(e),
            'concurrent_capacity': 'Unknown'
        }), 500

@app.route('/api/scalability/database', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def scalability_database_status(user_email, user_roles):
    """Get database scalability status"""
    try:
        db = DatabaseManager(test_mode=flag)
        
        scalability_stats = db.get_scalability_statistics()
        health_status = db.get_scalability_health()
        pool_status = db.get_connection_pool_status()
        optimization_info = db.optimize_for_concurrency()
        
        return jsonify({
            'database_scalability': {
                'statistics': scalability_stats,
                'health': health_status,
                'connection_pools': pool_status,
                'optimization_recommendations': optimization_info
            }
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'database_scalability': 'unavailable'
        }), 500

@app.route('/api/scalability/performance', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def scalability_performance(user_email, user_roles):
    """Get real-time performance metrics"""
    if not scalability_manager:
        return jsonify({
            'performance_monitoring': False,
            'message': 'Scalability manager not initialized'
        }), 503
    
    try:
        current_metrics = scalability_manager.resource_monitor.get_current_metrics()
        metrics_summary = scalability_manager.resource_monitor.get_metrics_summary()
        
        return jsonify({
            'performance_monitoring': True,
            'current_metrics': current_metrics,
            'metrics_summary': metrics_summary,
            'monitoring_interval': scalability_manager.config.monitoring_interval_seconds
        })
        
    except Exception as e:
        return jsonify({
            'performance_monitoring': False,
            'error': str(e)
        }), 500

# Cache Management Endpoints
@app.route('/api/cache/warmup', methods=['POST'])
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

@app.route('/api/cache/status', methods=['GET'])
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

@app.route('/api/cache/refresh', methods=['POST'])
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

@app.route('/api/cache/invalidate', methods=['POST'])
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
@app.route('/api/bnb-cache/status', methods=['GET'])
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

@app.route('/api/bnb-cache/refresh', methods=['POST'])
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

@app.route('/api/bnb-cache/invalidate', methods=['POST'])
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



@app.route('/api/create-folder', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
@tenant_required()
def create_folder(user_email, user_roles, tenant, user_tenants):
    """Create a new folder in Google Drive"""
    try:
        data = request.get_json()
        folder_name = data.get('folderName')
        if folder_name:
            # Create local folder
            folder_path = config.get_storage_folder(folder_name)
            config.ensure_folder_exists(folder_path)
            
            # Create Google Drive folder in correct parent
            try:
                print(f"Creating Google Drive folder for tenant: {tenant}", flush=True)
                drive_service = GoogleDriveService(administration=tenant)
                use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
                parent_folder_id = os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test else os.getenv('FACTUREN_FOLDER_ID')
                
                if parent_folder_id:
                    drive_result = drive_service.create_folder(folder_name, parent_folder_id)
                    print(f"Created Google Drive folder: {folder_name} in {'test' if use_test else 'production'} parent for tenant {tenant}", flush=True)
                    return jsonify({'success': True, 'path': folder_path, 'drive_folder': drive_result})
            except Exception as drive_error:
                print(f"Google Drive folder creation failed for tenant {tenant}: {drive_error}", flush=True)
            
            return jsonify({'success': True, 'path': folder_path})
        return jsonify({'success': False, 'error': 'No folder name provided'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload', methods=['POST', 'OPTIONS'])
@cognito_required(required_permissions=['invoices_create'])
@tenant_required()
def upload_file(user_email, user_roles, tenant, user_tenants):
    """Upload and process PDF file"""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response
        
    print("\n*** UPLOAD ENDPOINT CALLED ***", flush=True)
    print(f"Tenant: {tenant}", flush=True)
    try:
        print("=== UPLOAD REQUEST START ===", flush=True)
        print(f"Request method: {request.method}", flush=True)
        print(f"Request files: {list(request.files.keys())}", flush=True)
        print(f"Request form field count: {len(request.form)}", flush=True)
        
        if 'file' not in request.files:
            print("ERROR: No file in request", flush=True)
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        folder_name = request.form.get('folderName', 'General')
        print(f"File: {file.filename}, Folder: {folder_name}", flush=True)
        
        if file.filename == '':
            print("ERROR: No file selected", flush=True)
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            temp_path = os.path.join(UPLOAD_FOLDER, filename)
            print(f"Saving file to: {temp_path}", flush=True)
            file.save(temp_path)
            print("File saved successfully", flush=True)
            
            # Upload to Google Drive in production mode
            if flag:  # Test mode - local storage
                drive_result = {
                    'id': filename,
                    'url': f'http://localhost:5000/uploads/{filename}'
                }
            else:  # Production mode - Google Drive upload
                try:
                    # Check cache first
                    cache_key = f"{folder_name}_{filename}"
                    if cache_key in upload_cache:
                        print(f"Using cached file info for {filename}", flush=True)
                        drive_result = upload_cache[cache_key]
                    else:
                        print(f"Initializing Google Drive service for tenant: {tenant}", flush=True)
                        drive_service = GoogleDriveService(administration=tenant)
                        drive_folders = drive_service.list_subfolders()
                        
                        # Find the folder ID for the selected folder
                        folder_id = None
                        for folder in drive_folders:
                            if folder['name'] == folder_name:
                                folder_id = folder['id']
                                print(f"Found folder: {folder_name} (ID: {folder_id})", flush=True)
                                break
                        
                        if folder_id:
                            # Check if file already exists
                            existing_file = drive_service.check_file_exists(filename, folder_id)
                            
                            if existing_file['exists']:
                                print(f"File {filename} already exists in Google Drive", flush=True)
                                drive_result = existing_file['file']
                            else:
                                print(f"Uploading new file to Google Drive folder: {folder_name} (ID: {folder_id})", flush=True)
                                drive_result = drive_service.upload_file(temp_path, filename, folder_id)
                            
                            # Cache the result
                            upload_cache[cache_key] = drive_result
                            print(f"Cached file info for {cache_key}", flush=True)
                        
                            print(f"File result: {drive_result['url']}", flush=True)
                        else:
                            print(f"Folder '{folder_name}' not found in Google Drive folders: {[f['name'] for f in drive_folders]}", flush=True)
                            print("Using local storage as fallback", flush=True)
                            drive_result = {
                                'id': filename,
                                'url': f'http://localhost:5000/uploads/{filename}'
                            }
                except Exception as e:
                    print(f"Google Drive upload failed for tenant {tenant}: {type(e).__name__}: {str(e)}", flush=True)
                    import traceback
                    traceback.print_exc()
                    # Fallback to local storage
                    drive_result = {
                        'id': filename,
                        'url': f'http://localhost:5000/uploads/{filename}'
                    }
            
            # Check if user wants to force upload (bypass duplicate check)
            force_upload = request.form.get('forceUpload', 'false').lower() == 'true'
            
            if not force_upload:
                # Early duplicate detection - check before processing
                print("Checking for duplicates before processing...", flush=True)
                duplicate_check_result = check_for_early_duplicates(filename, folder_name, drive_result)
                if duplicate_check_result['has_duplicates']:
                    print(f"Duplicate detected - stopping upload: {duplicate_check_result['message']}", flush=True)
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    return jsonify({
                        'success': False,
                        'error': 'duplicate_detected',
                        'message': duplicate_check_result['message'],
                        'duplicate_info': duplicate_check_result['duplicate_info']
                    }), 409
            else:
                print("Force upload enabled - bypassing duplicate check...", flush=True)
            
            print("No duplicates found - proceeding with processing...", flush=True)
            print("Starting file processing...", flush=True)
            result = processor.process_file(temp_path, drive_result, folder_name)
            print("File processed, extracting transactions...", flush=True)
            transactions = processor.extract_transactions(result)
            print(f"Extracted {len(transactions)} transactions", flush=True)
            
            # Get last transactions for smart defaults
            last_transactions = transaction_logic.get_last_transactions(folder_name, tenant)
            if last_transactions:
                print(f"Found {len(last_transactions)} previous transactions for reference", flush=True)
                
                # Get vendor-specific parsed data
                lines = result['txt'].split('\n')
                vendor_data = processor._parse_vendor_specific(lines, folder_name.lower())
                
                # Create new transaction records
                new_data = {
                    'folder_name': folder_name,
                    'description': f"PDF processed from {filename}",
                    'amount': 0,  # Will be updated from PDF parsing
                    'drive_url': drive_result['url'],
                    'filename': filename,
                    'vendor_data': vendor_data,  # Pass parsed vendor data
                    'administration': tenant  # Pass tenant from request context
                }
                
                prepared_transactions = transaction_logic.prepare_new_transactions(last_transactions, new_data)
                print(f"Prepared {len(prepared_transactions)} new transaction records for approval", flush=True)
            
            # Move file to the correct vendor folder
            import shutil
            final_folder = result['folder']
            if not os.path.exists(final_folder):
                os.makedirs(final_folder, exist_ok=True)
            final_path = os.path.join(final_folder, filename)
            try:
                shutil.move(temp_path, final_path)
                print(f"File moved to: {final_path}", flush=True)
            except Exception as move_error:
                print(f"Error moving file: {move_error}", flush=True)
                # Clean up temp file if move fails
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
            # vendor_data already extracted above
            
            # Determine which parser was used based on extracted text
            parser_used = "pdfplumber" if "pdfplumber" in result['txt'] else "PyPDF2"
            
            return jsonify({
                'success': True,
                'filename': filename,
                'folder': result['folder'],
                'extractedText': result['txt'],
                'vendorData': vendor_data,
                'transactions': transactions,
                'preparedTransactions': prepared_transactions if 'prepared_transactions' in locals() else [],
                'templateTransactions': last_transactions,
                'parserUsed': parser_used
            })
        
        return jsonify({'success': False, 'error': 'Invalid file type'}), 400
    except Exception as e:
        print(f"\n=== UPLOAD ERROR ===", flush=True)
        print(f"Error type: {type(e).__name__}", flush=True)
        print(f"Error message: {str(e)}", flush=True)
        import traceback
        print("Full traceback:", flush=True)
        traceback.print_exc()
        print("=== END ERROR ===", flush=True)
        return jsonify({'success': False, 'error': f"{type(e).__name__}: {str(e)}"}), 500

@app.errorhandler(500)
def handle_500(e):
    print(f"500 error: {e}")
    return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

@app.route('/api/approve-transactions', methods=['POST'])
@cognito_required(required_permissions=['transactions_create'])
def approve_transactions(user_email, user_roles):
    """Save approved transactions to database"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        
        saved_transactions = transaction_logic.save_approved_transactions(transactions)
        
        return jsonify({
            'success': True,
            'savedTransactions': saved_transactions,
            'message': f'Successfully saved {len(saved_transactions)} transactions'
        })
    except Exception as e:
        print(f"Approval error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# Banking processor routes
@app.route('/api/banking/scan-files', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_scan_files(user_email, user_roles, tenant, user_tenants):
    """Scan download folder for CSV files"""
    try:
        processor = BankingProcessor(test_mode=flag)
        folder_path = request.args.get('folder', processor.download_folder)
        
        files = processor.get_csv_files(folder_path)
        return jsonify({
            'success': True,
            'files': files,
            'folder': folder_path
        })
    except Exception as e:
        print(f"Banking scan files error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/process-files', methods=['POST'])
@cognito_required(required_permissions=['banking_process'])
@tenant_required()
def banking_process_files(user_email, user_roles, tenant, user_tenants):
    """Process selected CSV files"""
    try:
        data = request.get_json()
        file_paths = data.get('files', [])
        test_mode = data.get('test_mode', True)
        
        processor = BankingProcessor(test_mode=test_mode)
        df = processor.process_csv_files(file_paths)
        
        if df.empty:
            return jsonify({'success': False, 'error': 'No data found in files'}), 400
        
        # Validate that the IBAN(s) in the file belong to the current tenant
        if 'Ref1' in df.columns:
            ibans = df['Ref1'].dropna().unique().tolist()
            print(f"[TENANT VALIDATION] Current tenant: {tenant}", flush=True)
            print(f"[TENANT VALIDATION] Found IBANs in file: {ibans}", flush=True)
            
            # Check each IBAN against vw_lookup_accounts
            db = DatabaseManager(test_mode=test_mode)
            conn = db.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            for iban in ibans:
                print(f"[TENANT VALIDATION] Checking IBAN: {iban}", flush=True)
                cursor.execute("""
                    SELECT administration FROM vw_lookup_accounts 
                    WHERE rekeningNummer = %s
                """, (iban,))
                result = cursor.fetchone()
                
                if result:
                    iban_tenant = result['administration']
                    print(f"[TENANT VALIDATION] IBAN {iban} belongs to: {iban_tenant}", flush=True)
                    # Strict validation: IBAN must belong to the CURRENT tenant
                    if iban_tenant != tenant:
                        print(f"[TENANT VALIDATION] BLOCKED: IBAN tenant ({iban_tenant}) != current tenant ({tenant})", flush=True)
                        cursor.close()
                        conn.close()
                        return jsonify({
                            'success': False, 
                            'error': f'Access denied: Bank account {iban} belongs to {iban_tenant}. You are currently working in {tenant}. Please switch to {iban_tenant} to upload this file.'
                        }), 403
                    else:
                        print(f"[TENANT VALIDATION] ALLOWED: IBAN matches current tenant", flush=True)
                else:
                    # IBAN not found in lookup - this might be okay for new accounts
                    print(f"Warning: IBAN {iban} not found in vw_lookup_accounts", flush=True)
            
            cursor.close()
            conn.close()
        
        records = processor.prepare_for_review(df)
        
        return jsonify({
            'success': True,
            'transactions': records,
            'count': len(records),
            'test_mode': test_mode
        })
        
    except Exception as e:
        print(f"Banking process files error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-sequences', methods=['POST'])
@cognito_required(required_permissions=['banking_read'])
def banking_check_sequences(user_email, user_roles):
    """Check sequence numbers against database"""
    try:
        data = request.get_json()
        iban = data.get('iban')
        sequences = data.get('sequences', [])
        test_mode = data.get('test_mode', True)
        
        db = DatabaseManager(test_mode=test_mode)
        table_name = 'mutaties'  # Always use 'mutaties' table
        existing_sequences = db.get_existing_sequences(iban, table_name)
        
        # Check for duplicates
        duplicates = [seq for seq in sequences if seq in existing_sequences]
        
        return jsonify({
            'success': True,
            'existing_sequences': existing_sequences,
            'duplicates': duplicates
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/apply-patterns', methods=['POST'])
@cognito_required(required_permissions=['banking_process'])
@tenant_required()
def banking_apply_patterns(user_email, user_roles, tenant, user_tenants):
    """Apply enhanced pattern matching to predict debet/credit accounts"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        use_enhanced = data.get('use_enhanced', True)  # Default to enhanced patterns
        
        if not transactions:
            return jsonify({'success': False, 'error': 'No transactions provided'}), 400
        
        # Use current tenant instead of getting from transaction
        administration = tenant
        
        # Add administration to each transaction if not present
        for tx in transactions:
            if 'administration' not in tx or not tx['administration']:
                tx['administration'] = administration
        
        if use_enhanced:
            # Use enhanced pattern analysis system
            processor = BankingProcessor(test_mode=test_mode)
            updated_transactions, results = processor.apply_enhanced_patterns(transactions, administration)
            
            return jsonify({
                'success': True,
                'transactions': updated_transactions,
                'enhanced_results': results,
                'method': 'enhanced'
            })
        else:
            # Fall back to legacy pattern matching
            db = DatabaseManager(test_mode=test_mode)
            
            # Get patterns for this administration
            patterns_data = db.get_patterns(administration)
            
            # Build pattern groups
            debet_patterns = {}
            credit_patterns = {}
            
            for pattern in patterns_data:
                ref_num = pattern.get('referenceNumber')
                if not ref_num:
                    continue
                    
                # Escape special regex characters
                escaped_ref = str(ref_num).replace('/', '\\/')
                
                debet_val = pattern.get('debet')
                credit_val = pattern.get('credit')
                
                if debet_val and str(debet_val) < '1300':
                    key = f"{pattern.get('administration')}_{debet_val}_{credit_val}"
                    if key not in debet_patterns:
                        debet_patterns[key] = {
                            'debet': debet_val,
                            'credit': credit_val,
                            'patterns': []
                        }
                    debet_patterns[key]['patterns'].append(escaped_ref)
                    
                if credit_val and str(credit_val) < '1300':
                    key = f"{pattern.get('administration')}_{debet_val}_{credit_val}"
                    if key not in credit_patterns:
                        credit_patterns[key] = {
                            'debet': debet_val,
                            'credit': credit_val,
                            'patterns': []
                        }
                    credit_patterns[key]['patterns'].append(escaped_ref)
            
            # Apply patterns to transactions
            import re
            
            for transaction in transactions:
                description = str(transaction.get('TransactionDescription', ''))
                
                # If Credit is empty, try debet patterns
                if not transaction.get('Credit'):
                    for pattern_group in debet_patterns.values():
                        if pattern_group['patterns']:
                            pattern_regex = '|'.join(pattern_group['patterns'])
                            try:
                                match = re.search(pattern_regex, description, re.IGNORECASE)
                                if match:
                                    transaction['ReferenceNumber'] = match.group(0)
                                    transaction['Credit'] = pattern_group['credit']
                                    break
                            except re.error:
                                continue
                
                # If Debet is empty, try credit patterns  
                elif not transaction.get('Debet'):
                    for pattern_group in credit_patterns.values():
                        if pattern_group['patterns']:
                            pattern_regex = '|'.join(pattern_group['patterns'])
                            try:
                                match = re.search(pattern_regex, description, re.IGNORECASE)
                                if match:
                                    transaction['ReferenceNumber'] = match.group(0)
                                    transaction['Debet'] = pattern_group['debet']
                                    break
                            except re.error:
                                continue
            
            return jsonify({
                'success': True,
                'transactions': transactions,
                'patterns_found': len(patterns_data),
                'method': 'legacy'
            })
        
    except Exception as e:
        print(f"Pattern matching error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/save-transactions', methods=['POST'])
@cognito_required(required_permissions=['transactions_create'])
@tenant_required()
def banking_save_transactions(user_email, user_roles, tenant, user_tenants):
    """Save approved transactions to database with duplicate filtering"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        
        # Add administration field to all transactions
        for transaction in transactions:
            transaction['administration'] = tenant
        
        db = DatabaseManager(test_mode=test_mode)
        table_name = 'mutaties'  # Always use 'mutaties' table
        
        # Group transactions by IBAN (Ref1)
        ibans = list(set([t.get('Ref1') for t in transactions if t.get('Ref1')]))
        transactions_to_save = []
        
        for iban in ibans:
            # Get existing sequences for this IBAN (filtered by tenant)
            existing_sequences = db.get_existing_sequences(iban, table_name, administration=tenant)
            
            # Filter transactions for this IBAN that don't exist
            iban_transactions = [t for t in transactions if t.get('Ref1') == iban]
            new_transactions = [t for t in iban_transactions if t.get('Ref2') not in existing_sequences]
            
            transactions_to_save.extend(new_transactions)
        
        # Save only new transactions
        processor = BankingProcessor(test_mode=test_mode)
        saved_count = processor.save_approved_transactions(transactions_to_save)
        
        # Invalidate cache after saving transactions
        if saved_count > 0:
            invalidate_cache()
            print(f"[CACHE] Invalidated cache after saving {saved_count} transactions", flush=True)
        
        total_count = len(transactions)
        duplicate_count = total_count - len(transactions_to_save)
        
        return jsonify({
            'success': True,
            'saved_count': saved_count,
            'total_count': total_count,
            'duplicate_count': duplicate_count,
            'table': table_name,
            'tenant': tenant,
            'message': f'Saved {saved_count} new transactions for {tenant}, skipped {duplicate_count} duplicates'
        })
        
    except Exception as e:
        print(f"Banking save transactions error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/lookups', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_lookups(user_email, user_roles, tenant, user_tenants):
    """Get mapping data for account codes and descriptions"""
    try:
        db = DatabaseManager(test_mode=flag)
        
        # Get bank account lookups - FILTERED BY CURRENT TENANT
        all_bank_accounts = db.get_bank_account_lookups()
        bank_accounts = [acc for acc in all_bank_accounts if acc.get('administration') == tenant]
        
        # Get recent transactions for account mapping - FILTERED BY CURRENT TENANT
        all_recent_transactions = db.get_recent_transactions(limit=100)
        recent_transactions = [tx for tx in all_recent_transactions if tx.get('administration') == tenant]
        
        # Extract unique account codes and descriptions
        accounts = set()
        descriptions = set()
        
        for tx in recent_transactions:
            if tx.get('Debet'):
                accounts.add(tx['Debet'])
            if tx.get('Credit'):
                accounts.add(tx['Credit'])
            if tx.get('TransactionDescription'):
                descriptions.add(tx['TransactionDescription'])
        
        return jsonify({
            'success': True,
            'accounts': sorted(list(accounts)),
            'descriptions': sorted(list(descriptions)),
            'bank_accounts': bank_accounts
        })
        
    except Exception as e:
        print(f"Banking lookups error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/mutaties', methods=['GET'])
@cognito_required(required_permissions=['transactions_read'])
@tenant_required()
def banking_mutaties(user_email, user_roles, tenant, user_tenants):
    """Get mutaties with filters"""
    try:
        db = DatabaseManager(test_mode=flag)
        table_name = 'mutaties_test' if flag else 'mutaties'
        
        # Get filter parameters
        years = request.args.get('years', str(datetime.now().year)).split(',')
        administration = request.args.get('administration', 'all')
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        # Years filter
        if years and years != ['']:
            year_placeholders = ','.join(['%s'] * len(years))
            where_conditions.append(f"YEAR(TransactionDate) IN ({year_placeholders})")
            params.extend(years)
        
        # Administration filter - MUST respect user's accessible tenants
        if administration == 'all':
            # Show all tenants user has access to
            if len(user_tenants) == 1:
                where_conditions.append("administration = %s")
                params.append(user_tenants[0])
            else:
                placeholders = ','.join(['%s'] * len(user_tenants))
                where_conditions.append(f"administration IN ({placeholders})")
                params.extend(user_tenants)
        else:
            # Validate user has access to requested administration
            if administration not in user_tenants:
                return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
            where_conditions.append("administration = %s")
            params.append(administration)
        
        where_clause = 'WHERE ' + ' AND '.join(where_conditions) if where_conditions else ''
        
        query = f"""
            SELECT ID, TransactionNumber, TransactionDate, TransactionDescription, 
                   TransactionAmount, Debet, Credit, ReferenceNumber, 
                   Ref1, Ref2, Ref3, Ref4, Administration
            FROM {table_name} 
            {where_clause}
            ORDER BY TransactionDate DESC, ID DESC
        """
        cursor.execute(query, params)
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'mutaties': results,
            'count': len(results),
            'table': table_name
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/filter-options', methods=['GET'])
@cognito_required(required_permissions=['transactions_read'])
@tenant_required()
def banking_filter_options(user_email, user_roles, tenant, user_tenants):
    """Get filter options for mutaties"""
    try:
        db = DatabaseManager(test_mode=flag)
        table_name = 'mutaties_test' if flag else 'mutaties'
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build administration filter based on user's accessible tenants
        if len(user_tenants) == 1:
            admin_filter = "AND administration = %s"
            admin_params = [user_tenants[0]]
        else:
            placeholders = ','.join(['%s'] * len(user_tenants))
            admin_filter = f"AND administration IN ({placeholders})"
            admin_params = user_tenants
        
        # Get distinct years (filtered by tenant)
        cursor.execute(f"SELECT DISTINCT YEAR(TransactionDate) as year FROM {table_name} WHERE TransactionDate IS NOT NULL {admin_filter} ORDER BY year DESC", admin_params)
        years = [str(row['year']) for row in cursor.fetchall()]
        
        # Get distinct administrations (only those user has access to)
        cursor.execute(f"SELECT DISTINCT administration FROM {table_name} WHERE administration IS NOT NULL {admin_filter} ORDER BY administration", admin_params)
        administrations = [row['administration'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'years': years,
            'administrations': administrations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/update-mutatie', methods=['POST'])
@cognito_required(required_permissions=['transactions_update'])
@tenant_required()
def banking_update_mutatie(user_email, user_roles, tenant, user_tenants):
    """Update a mutatie record"""
    try:
        data = request.get_json()
        record_id = data.get('ID')
        
        print(f"Update request for ID: {record_id}", flush=True)
        print(f"Data received: {data}", flush=True)
        print(f"Current tenant: {tenant}", flush=True)
        
        if not record_id:
            return jsonify({'success': False, 'error': 'No ID provided'}), 400
        
        db = DatabaseManager(test_mode=flag)
        table_name = 'mutaties_test' if flag else 'mutaties'
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # First, verify the record belongs to the current tenant
        cursor.execute(f"SELECT administration FROM {table_name} WHERE ID = %s", (record_id,))
        existing_record = cursor.fetchone()
        
        if not existing_record:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Record not found'}), 404
        
        if existing_record['administration'] != tenant:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Access denied: Record belongs to different tenant'}), 403
        
        # Update the record - FORCE Administration to current tenant (ignore any changes from frontend)
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
        transaction_date = data.get('TransactionDate')
        if transaction_date and 'GMT' in str(transaction_date):
            from datetime import datetime
            transaction_date = datetime.strptime(transaction_date, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d')
        
        cursor.execute(update_query, (
            data.get('TransactionNumber'),
            transaction_date,
            data.get('TransactionDescription'),
            data.get('TransactionAmount'),
            data.get('Debet'),
            data.get('Credit'),
            data.get('ReferenceNumber'),
            data.get('Ref1'),
            data.get('Ref2'),
            data.get('Ref3'),
            data.get('Ref4'),
            tenant,  # FORCE to current tenant - ignore any changes from frontend
            record_id
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"Record {record_id} updated successfully with administration={tenant}", flush=True)
        
        return jsonify({
            'success': True,
            'message': f'Record {record_id} updated successfully'
        })
        
    except Exception as e:
        print(f"Update error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-accounts', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_check_accounts(user_email, user_roles, tenant, user_tenants):
    """Check banking account balances"""
    try:
        processor = BankingProcessor(test_mode=flag)
        end_date = request.args.get('end_date')
        
        # Pass tenant to filter accounts
        balances = processor.check_banking_accounts(end_date=end_date, administration=tenant)
        
        return jsonify({
            'success': True,
            'balances': balances
        })
        
    except Exception as e:
        print(f"Banking check accounts error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-sequence', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
def banking_check_sequence(user_email, user_roles):
    """Check sequence numbers for account"""
    try:
        processor = BankingProcessor(test_mode=flag)
        account_code = request.args.get('account_code')
        administration = request.args.get('administration')
        start_date = request.args.get('start_date', '2025-01-01')
        
        result = processor.check_sequence_numbers(account_code, administration, start_date)
        return jsonify(result)
        
    except Exception as e:
        print(f"Check sequence error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-revolut-balance', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_check_revolut_balance(user_email, user_roles, tenant, user_tenants):
    """Check Revolut balance gaps by comparing calculated vs Ref3 balance"""
    try:
        processor = BankingProcessor(test_mode=flag)
        iban = request.args.get('iban', 'NL08REVO7549383472')
        account_code = request.args.get('account_code', '1022')
        start_date = request.args.get('start_date', '2025-05-01')
        expected_balance = float(request.args.get('expected_balance', '262.54'))
        
        result = processor.check_revolut_balance_gaps(
            iban=iban,
            account_code=account_code,
            start_date=start_date,
            expected_final_balance=expected_balance
        )
        
        # Return only transactions with gaps (non-zero discrepancies)
        if result.get('success'):
            return jsonify({
                'success': True,
                'iban': result.get('iban'),
                'account_code': result.get('account_code'),
                'start_date': result.get('start_date'),
                'total_transactions': result.get('total_transactions'),
                'calculated_final_balance': result.get('calculated_final_balance'),
                'expected_final_balance': result.get('expected_final_balance'),
                'final_discrepancy': result.get('final_discrepancy'),
                'balance_gaps_found': result.get('balance_gaps_found'),
                'transactions_with_gaps': result.get('transactions_with_gaps', []),
                'summary': result.get('summary')
            })
        else:
            return jsonify(result)
        
    except Exception as e:
        print(f"Check Revolut balance error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/check-revolut-balance-debug', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
def banking_check_revolut_balance_debug(user_email, user_roles):
    """Debug endpoint - returns only first 10 transactions with full details"""
    try:
        processor = BankingProcessor(test_mode=flag)
        iban = request.args.get('iban', 'NL08REVO7549383472')
        account_code = request.args.get('account_code', '1022')
        start_date = request.args.get('start_date', '2025-05-01')
        expected_balance = float(request.args.get('expected_balance', '262.54'))
        
        result = processor.check_revolut_balance_gaps(
            iban=iban,
            account_code=account_code,
            start_date=start_date,
            expected_final_balance=expected_balance
        )
        
        # Return only first 10 transactions for debugging
        if result.get('success'):
            return jsonify({
                'success': True,
                'iban': result.get('iban'),
                'start_date': result.get('start_date'),
                'starting_balance_debug': result.get('starting_balance_debug'),
                'first_10_transactions': result.get('first_10_transactions', []),
                'total_transactions': result.get('total_transactions', 0),
                'note': 'Debug endpoint - showing first 10 transactions only'
            })
        else:
            return jsonify(result)
        
    except Exception as e:
        print(f"Check Revolut balance debug error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/banking/migrate-revolut-ref2', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def banking_migrate_revolut_ref2(user_email, user_roles):
    """Migrate Revolut Ref2 to new format"""
    try:
        from migrate_revolut_ref2 import migrate_revolut_ref2
        result = migrate_revolut_ref2(test_mode=flag)
        return jsonify(result)
    except Exception as e:
        print(f"Migration error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# STR (Short Term Rental) routes
@app.route('/api/str/upload', methods=['POST', 'OPTIONS'])
@cognito_required(required_permissions=['str_create'])
@tenant_required()
def str_upload(user_email, user_roles, tenant, user_tenants):
    """Upload and process single STR file"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})
        
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        platform = request.form.get('platform', 'airbnb')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        str_processor = STRProcessor(test_mode=flag)
        
        bookings = str_processor.process_str_files([temp_path], platform)
        
        # Add administration (tenant) to all bookings
        if bookings:
            for booking in bookings:
                booking['administration'] = tenant
        
        if bookings:
            separated = str_processor.separate_by_status(bookings)
            summary = str_processor.generate_summary(bookings)
        else:
            separated = {'realised': [], 'planned': []}
            summary = {}
        
        os.remove(temp_path)  # Clean up
        
        # Convert numpy types to native Python types for JSON serialization
        def convert_types(obj):
            if hasattr(obj, 'item'):
                return obj.item()
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(v) for v in obj]
            return obj
        
        response_data = {
            'success': True,
            'realised': convert_types(separated['realised']),
            'planned': convert_types(separated['planned']),
            'already_loaded': convert_types(separated.get('already_loaded', [])),
            'summary': convert_types(summary),
            'platform': platform,
            'administration': tenant
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Removed /api/str/scan-files and /api/str/process-files endpoints
# Using single file upload via /api/str/upload instead

@app.route('/api/str/save', methods=['POST'])
@cognito_required(required_permissions=['bookings_create'])
@tenant_required()
def str_save(user_email, user_roles, tenant, user_tenants):
    """Save STR bookings to database like R script"""

    try:
        data = request.get_json()
        realised_bookings = data.get('realised', [])
        planned_bookings = data.get('planned', [])
        
        # Add administration (tenant) to all bookings
        for booking in realised_bookings:
            booking['administration'] = tenant
        for booking in planned_bookings:
            booking['administration'] = tenant
        
        str_db = STRDatabase(test_mode=flag)
        str_processor = STRProcessor(test_mode=flag)
        
        results = {}
        
        # Save realised bookings to bnb table
        if realised_bookings:
            realised_count = str_db.insert_realised_bookings(realised_bookings)
            results['realised_saved'] = realised_count
        
        # Save planned bookings to bnbplanned table (clears table first)
        planned_count = str_db.insert_planned_bookings(planned_bookings)
        results['planned_saved'] = planned_count
        
        # Generate and save future summary to bnbfuture table
        if planned_bookings:
            future_summary = str_processor.generate_future_summary(planned_bookings)
            future_count = str_db.insert_future_summary(future_summary)
            results['future_summary_saved'] = future_count
        
        return jsonify({
            'success': True,
            'results': results,
            'message': f'Processed {len(realised_bookings)} realised, {len(planned_bookings)} planned bookings for {tenant}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Pricing routes
@app.route('/api/pricing/generate', methods=['POST'])
@cognito_required(required_permissions=['str_update'])
def pricing_generate(user_email, user_roles):
    """Generate pricing recommendations using hybrid optimizer"""
    try:
        from hybrid_pricing_optimizer import HybridPricingOptimizer
        
        data = request.get_json()
        months = data.get('months', 14)
        listing = data.get('listing')
        
        optimizer = HybridPricingOptimizer(test_mode=flag)
        result = optimizer.generate_pricing_strategy(months, listing)
        
        return jsonify({
            'success': True,
            'result': result,
            'listing': listing,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pricing/recommendations', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_recommendations(user_email, user_roles):
    """Get pricing recommendations with historical comparison"""
    try:
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all recommendations with historical data and multipliers
        query = """
        SELECT listing_name, price_date, recommended_price, ai_recommended_adr, 
               ai_historical_adr, ai_variance, ai_reasoning, is_weekend, 
               event_uplift, event_name, last_year_adr, generated_at,
               base_rate, historical_mult, occupancy_mult, pace_mult, 
               event_mult, ai_correction, btw_adjustment
        FROM pricing_recommendations 
        WHERE price_date >= CURDATE()
        ORDER BY listing_name, price_date
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Convert dates to strings and Decimals to floats
        for result in results:
            result['price_date'] = str(result['price_date'])
            if result['generated_at']:
                result['generated_at'] = str(result['generated_at'])
            # Convert Decimal fields to float
            if result['recommended_price']:
                result['recommended_price'] = float(result['recommended_price'])
            if result['ai_recommended_adr']:
                result['ai_recommended_adr'] = float(result['ai_recommended_adr'])
            if result['ai_historical_adr']:
                result['ai_historical_adr'] = float(result['ai_historical_adr'])
            if result['ai_variance']:
                result['ai_variance'] = float(result['ai_variance'])
            if result['last_year_adr']:
                result['last_year_adr'] = float(result['last_year_adr'])
            # Convert multiplier fields to float
            if result['base_rate']:
                result['base_rate'] = float(result['base_rate'])
            if result['historical_mult']:
                result['historical_mult'] = float(result['historical_mult'])
            if result['occupancy_mult']:
                result['occupancy_mult'] = float(result['occupancy_mult'])
            if result['pace_mult']:
                result['pace_mult'] = float(result['pace_mult'])
            if result['event_mult']:
                result['event_mult'] = float(result['event_mult'])
            if result['ai_correction']:
                result['ai_correction'] = float(result['ai_correction'])
            if result['btw_adjustment']:
                result['btw_adjustment'] = float(result['btw_adjustment'])
        
        return jsonify({
            'success': True,
            'recommendations': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/pricing/historical', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_historical(user_email, user_roles):
    """Get historical ADR data for trend analysis"""
    try:
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get monthly historical ADR data with guest fee adjustment for Child Friendly
        query = """
        SELECT 
            listing,
            YEAR(checkinDate) as year,
            MONTH(checkinDate) as month,
            COUNT(*) as bookings,
            AVG(
                CASE 
                    WHEN listing = 'Child Friendly' AND guests > 2 
                    THEN (amountGross - (guests - 2) * 30) / nights
                    ELSE amountGross / nights
                END
            ) as historical_adr
        FROM bnb 
        WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
        AND nights > 0
        GROUP BY listing, YEAR(checkinDate), MONTH(checkinDate)
        ORDER BY listing, year, month
        """
        
        cursor.execute(query)
        historical_data = cursor.fetchall()
        
        # Convert Decimal to float for historical data
        for row in historical_data:
            if row['historical_adr']:
                row['historical_adr'] = float(row['historical_adr'])
        
        # Get recommended ADR data by month
        rec_query = """
        SELECT 
            listing_name,
            YEAR(price_date) as year,
            MONTH(price_date) as month,
            AVG(recommended_price) as recommended_adr
        FROM pricing_recommendations 
        GROUP BY listing_name, YEAR(price_date), MONTH(price_date)
        ORDER BY listing_name, year, month
        """
        
        cursor.execute(rec_query)
        recommended_data = cursor.fetchall()
        
        # Convert Decimal to float for recommended data
        for row in recommended_data:
            if row['recommended_adr']:
                row['recommended_adr'] = float(row['recommended_adr'])
        
        return jsonify({
            'success': True,
            'historical': historical_data,
            'recommended': recommended_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/pricing/listings', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_listings(user_email, user_roles):
    """Get available listings for pricing"""
    try:
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT listing_name, active FROM listings WHERE active = TRUE ORDER BY listing_name"
        cursor.execute(query)
        listings = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'listings': [listing['listing_name'] for listing in listings]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/pricing/multipliers', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_multipliers(user_email, user_roles):
    """Get average multipliers by listing"""
    try:
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT 
            listing_name,
            AVG(base_rate) as avg_base_rate,
            AVG(historical_mult) as avg_historical_mult,
            AVG(occupancy_mult) as avg_occupancy_mult,
            AVG(pace_mult) as avg_pace_mult,
            AVG(event_mult) as avg_event_mult,
            AVG(ai_correction) as avg_ai_correction,
            AVG(btw_adjustment) as avg_btw_adjustment,
            COUNT(*) as record_count
        FROM pricing_recommendations 
        WHERE base_rate IS NOT NULL
        GROUP BY listing_name
        ORDER BY listing_name
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Convert Decimal to float
        for result in results:
            for key, value in result.items():
                if key != 'listing_name' and key != 'record_count' and value is not None:
                    result[key] = float(value)
        
        return jsonify({
            'success': True,
            'multipliers': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/str/write-future', methods=['POST'])
@cognito_required(required_permissions=['bookings_create'])
def str_write_future(user_email, user_roles):
    """Write current BNB planned data to bnbfuture table"""

    try:
        str_db = STRDatabase(test_mode=flag)
        result = str_db.write_bnb_future_summary()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Written {result['inserted']} future records for {result['date']}",
                'summary': result['summary']
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', result.get('message', 'Unknown error'))
            }), 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/import-payout', methods=['POST', 'OPTIONS'])
@cognito_required(required_permissions=['str_create'])
def str_import_payout(user_email, user_roles):
    """
    Import Booking.com Payout CSV to update financial figures
    
    This endpoint processes monthly Payout CSV files from Booking.com
    and updates existing bookings with actual settlement data.
    """
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})
    
    try:
        print("=== PAYOUT CSV IMPORT START ===", flush=True)
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Validate filename pattern (Payout_from_*.csv)
        if not file.filename.lower().startswith('payout_from') or not file.filename.lower().endswith('.csv'):
            return jsonify({
                'success': False, 
                'error': 'Invalid file format. Expected: Payout_from_YYYY-MM-DD_until_YYYY-MM-DD.csv'
            }), 400
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        print(f"Processing Payout CSV: {filename}", flush=True)
        
        # Process the Payout CSV file
        str_processor = STRProcessor(test_mode=flag)
        payout_result = str_processor._process_booking_payout(temp_path)
        
        if payout_result.get('errors'):
            print(f"Payout processing errors: {payout_result['errors']}", flush=True)
        
        # Update database with payout data
        str_db = STRDatabase(test_mode=flag)
        update_result = str_db.update_from_payout(payout_result.get('updates', []))
        
        # Clean up temp file
        os.remove(temp_path)
        
        # Combine results
        response = {
            'success': True,
            'message': f"Payout CSV processed successfully",
            'processing': {
                'total_rows': payout_result['summary']['total_rows'],
                'reservation_rows': payout_result['summary']['reservation_rows'],
                'updates_prepared': payout_result['summary']['updated_count'],
                'processing_errors': payout_result['summary']['error_count']
            },
            'database': {
                'updated': update_result['updated'],
                'not_found': update_result['not_found'],
                'errors': update_result.get('errors', [])
            },
            'summary': {
                'total_updated': update_result['updated'],
                'total_not_found': len(update_result['not_found']),
                'total_errors': len(update_result.get('errors', []))
            }
        }
        
        print(f"Payout import completed: {update_result['updated']} bookings updated", flush=True)
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in Payout import: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/summary', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def str_summary(user_email, user_roles):
    """Get STR performance summary"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        str_db = STRDatabase(test_mode=flag)
        summary = str_db.get_str_summary(start_date, end_date)
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/str/future-trend', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def str_future_trend(user_email, user_roles):
    """Get BNB future revenue trend data"""
    try:
        db = DatabaseManager(test_mode=flag)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT date, channel, listing, amount, items
        FROM bnbfuture
        ORDER BY date, listing, channel
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Convert dates and decimals
        for row in results:
            if row['date']:
                row['date'] = str(row['date'])
            if row['amount']:
                row['amount'] = float(row['amount'])
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# BTW (VAT) Declaration routes
@app.route('/api/btw/generate-report', methods=['POST'])
@cognito_required(required_permissions=['btw_read', 'btw_process'])
def btw_generate_report(user_email, user_roles):
    """Generate BTW declaration report using TemplateService with field mappings
    
    Supports multiple output destinations:
    - download: Return content to frontend for download (default)
    - gdrive: Upload to tenant's Google Drive
    - s3: Upload to AWS S3 (future implementation)
    """
    try:
        data = request.get_json()
        administration = data.get('administration')
        year = data.get('year')
        quarter = data.get('quarter')
        output_destination = data.get('output_destination', 'download')  # Default to download
        folder_id = data.get('folder_id')  # Optional Google Drive folder ID
        
        if not all([administration, year, quarter]):
            return jsonify({
                'success': False, 
                'error': 'Administration, year, and quarter are required'
            }), 400
        
        # Get cache and database instances
        cache = get_cache()
        db = DatabaseManager(test_mode=flag)
        cache.get_data(db)
        
        # Generate structured report data using new generator
        from report_generators import btw_aangifte_generator
        
        report_data = btw_aangifte_generator.generate_btw_report(
            cache=cache,
            db=db,
            administration=administration,
            year=int(year),
            quarter=int(quarter)
        )
        
        if not report_data.get('success'):
            return jsonify(report_data), 500
        
        # Initialize TemplateService
        template_service = TemplateService(db)
        
        # Prepare template data
        template_data = btw_aangifte_generator.prepare_template_data(report_data)
        
        # Try to get template metadata from database
        template_type = 'btw_aangifte_html'
        metadata = None
        
        try:
            metadata = template_service.get_template_metadata(administration, template_type)
        except Exception as e:
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
                logger.error(f"Failed to fetch template from Google Drive: {e}")
                # Fallback to filesystem
                metadata = None
        
        if not metadata:
            # Fallback: Load from filesystem
            template_path = os.path.join('backend', 'templates', 'html', 'btw_aangifte_template.html')
            
            if not os.path.exists(template_path):
                logger.error(f"Template not found: {template_path}")
                return jsonify({'success': False, 'error': 'Template not found'}), 500
            
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            # Use default field mappings (simple placeholder replacement)
            field_mappings = {
                'fields': {key: {'path': key, 'format': 'text'} for key in template_data.keys()},
                'formatting': {
                    'locale': 'nl_NL',
                    'currency': 'EUR',
                    'date_format': 'YYYY-MM-DD',
                    'number_decimals': 2
                }
            }
        
        # Apply field mappings using TemplateService
        html_report = template_service.apply_field_mappings(
            template_content,
            template_data,
            field_mappings
        )
        
        # Generate filename
        filename = f'BTW_Aangifte_{administration}_{year}_Q{quarter}.html'
        
        # Handle output destination
        from services.output_service import OutputService
        output_service = OutputService(db)
        
        output_result = output_service.handle_output(
            content=html_report,
            filename=filename,
            destination=output_destination,
            administration=administration,
            content_type='text/html',
            folder_id=folder_id
        )
        
        # Prepare transaction for saving (using existing logic)
        btw_processor = BTWProcessor(test_mode=flag)
        transaction = btw_processor._prepare_btw_transaction(
            administration, 
            year, 
            quarter, 
            report_data['calculations']
        )
        
        # Return result based on destination
        if output_destination == 'download':
            return jsonify({
                'success': True,
                'html_report': output_result['content'],
                'transaction': transaction,
                'calculations': report_data['calculations'],
                'quarter_end_date': report_data['metadata']['end_date'],
                'filename': output_result['filename']
            })
        else:
            # For gdrive or s3, return URL and metadata
            return jsonify({
                'success': True,
                'destination': output_result['destination'],
                'url': output_result.get('url'),
                'transaction': transaction,
                'calculations': report_data['calculations'],
                'quarter_end_date': report_data['metadata']['end_date'],
                'filename': output_result['filename'],
                'message': output_result['message']
            })
        
    except Exception as e:
        # Check if it's a Google Drive authentication error
        from google_drive_service import GoogleDriveAuthenticationError
        
        if isinstance(e, GoogleDriveAuthenticationError):
            logger.error(f"Google Drive authentication error: {e.to_dict()}")
            return jsonify({
                'success': False,
                **e.to_dict()
            }), 401  # 401 Unauthorized for auth errors
        
        logger.error(f"Failed to generate BTW report: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/btw/save-transaction', methods=['POST'])
@cognito_required(required_permissions=['transactions_create'])
def btw_save_transaction(user_email, user_roles):
    """Save BTW transaction to database"""
    try:
        data = request.get_json()
        transaction = data.get('transaction')
        
        if not transaction:
            return jsonify({'success': False, 'error': 'Transaction data required'}), 400
        
        btw_processor = BTWProcessor(test_mode=flag)
        result = btw_processor.save_btw_transaction(transaction)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/btw/upload-report', methods=['POST'])
@cognito_required(required_permissions=['btw_process'])
def btw_upload_report(user_email, user_roles):
    """Upload BTW report to Google Drive"""
    try:
        data = request.get_json()
        html_content = data.get('html_content')
        filename = data.get('filename')
        
        if not all([html_content, filename]):
            return jsonify({
                'success': False, 
                'error': 'HTML content and filename are required'
            }), 400
        
        btw_processor = BTWProcessor(test_mode=flag)
        result = btw_processor.upload_report_to_drive(html_content, filename)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Toeristenbelasting (Tourist Tax) Declaration routes
@app.route('/api/toeristenbelasting/generate-report', methods=['POST'])
@cognito_required(required_permissions=['str_read', 'reports_read'])
def toeristenbelasting_generate_report(user_email, user_roles):
    """Generate Toeristenbelasting declaration report
    
    Supports multiple output destinations:
    - download: Return content to frontend for download (default)
    - gdrive: Upload to tenant's Google Drive
    - s3: Upload to AWS S3 (future implementation)
    """
    try:
        data = request.get_json()
        year = data.get('year')
        output_destination = data.get('output_destination', 'download')  # Default to download
        folder_id = data.get('folder_id')  # Optional Google Drive folder ID
        
        if not year:
            return jsonify({
                'success': False, 
                'error': 'Year is required'
            }), 400
        
        processor = ToeristenbelastingProcessor(test_mode=flag)
        result = processor.generate_toeristenbelasting_report(year)
        
        # If report generation failed, return error
        if not result.get('success'):
            return jsonify(result), 500
        
        # Handle output destination if report was successful
        if output_destination != 'download':
            # Get administration from result (should be in the report data)
            # For now, we'll use a default or extract from the report
            # This may need to be passed as a parameter in the future
            administration = result.get('administration', 'default')
            
            db = DatabaseManager(test_mode=flag)
            from services.output_service import OutputService
            output_service = OutputService(db)
            
            # Generate filename
            filename = f'Toeristenbelasting_{administration}_{year}.html'
            
            output_result = output_service.handle_output(
                content=result.get('html_report', ''),
                filename=filename,
                destination=output_destination,
                administration=administration,
                content_type='text/html',
                folder_id=folder_id
            )
            
            # Update result with output information
            result['destination'] = output_result['destination']
            result['url'] = output_result.get('url')
            result['filename'] = output_result['filename']
            result['message'] = output_result['message']
            
            # Remove html_report from response for gdrive/s3 destinations
            if 'html_report' in result:
                del result['html_report']
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/toeristenbelasting/available-years', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def toeristenbelasting_available_years(user_email, user_roles):
    """Get available years for Toeristenbelasting (current year and 3 years back)"""
    try:
        from datetime import datetime
        current_year = datetime.now().year
        
        # Generate years: current year and 3 years back
        years = [str(current_year - i) for i in range(4)]
        
        return jsonify({
            'success': True,
            'years': years
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/reports/aangifte-ib', methods=['GET'])
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

@app.route('/api/reports/aangifte-ib-details', methods=['GET'])
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

@app.route('/api/reports/aangifte-ib-export', methods=['POST'])
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
                logger.error(f"Failed to fetch template from Google Drive: {e}")
                # Fallback to filesystem
                metadata = None
        
        if not metadata:
            # Fallback: Load from filesystem
            template_path = os.path.join(
                os.path.dirname(__file__),
                '..',
                'templates',
                'html',
                'aangifte_ib_template.html'
            )
            
            if not os.path.exists(template_path):
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

@app.route('/api/reports/aangifte-ib-xlsx-export', methods=['POST'])
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

@app.route('/api/reports/aangifte-ib-xlsx-export-stream', methods=['POST'])
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

# PDF Validation routes
@app.route('/api/pdf/validate-urls-stream', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_validate_urls_stream(user_email, user_roles):
    """Stream PDF validation progress with Server-Sent Events"""
    from flask import Response
    import json
    
    validator = PDFValidator(test_mode=flag)
    year = request.args.get('year', '2025')
    administration = request.args.get('administration', 'all')
    
    def generate_progress():
        try:
            for progress_data in validator.validate_pdf_urls_with_progress(year, administration):
                if progress_data.get('validation_results') is not None:
                    validation_results = progress_data['validation_results']
                    for result in validation_results:
                        if 'record' in result and 'TransactionDate' in result['record']:
                            if result['record']['TransactionDate']:
                                date_obj = result['record']['TransactionDate']
                                if hasattr(date_obj, 'strftime'):
                                    result['record']['TransactionDate'] = date_obj.strftime('%Y-%m-%d')
                                else:
                                    result['record']['TransactionDate'] = str(date_obj)[:10]
                    
                    yield f"data: {json.dumps({'type': 'complete', 'validation_results': validation_results, 'total_records': progress_data['total'], 'ok_count': progress_data['ok_count'], 'failed_count': progress_data['failed_count']}, default=str)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'progress', **progress_data}, default=str)}\n\n"
                    
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(generate_progress(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    })

@app.route('/api/pdf/validate-urls', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_validate_urls(user_email, user_roles):
    """Validate all Google Drive URLs in mutaties table"""
    import json
    
    def generate_progress():
        with app.app_context():
            try:
                validator = PDFValidator(test_mode=flag)
                
                # Parse range parameter
                range_param = request.args.get('range', '1-100')
                start_record, end_record = map(int, range_param.split('-'))
                print(f"Starting validation for range: {range_param}")
                
                # Send initial message
                yield f"data: {json.dumps({'type': 'progress', 'current': 0, 'total': 0, 'ok_count': 0, 'failed_count': 0}, default=str)}\n\n"
                
                # Use the generator method for progress updates
                for progress_data in validator.validate_pdf_urls_with_progress(start_record, end_record):
                    if progress_data.get('validation_results') is not None:
                        # Convert dates to strings for JSON serialization
                        validation_results = progress_data['validation_results']
                        for result in validation_results:
                            if 'record' in result and 'TransactionDate' in result['record']:
                                if result['record']['TransactionDate']:
                                    result['record']['TransactionDate'] = str(result['record']['TransactionDate'])
                        
                        # Final result
                        yield f"data: {json.dumps({'type': 'complete', 'validation_results': validation_results, 'total_records': progress_data['total'], 'ok_count': progress_data['ok_count'], 'failed_count': progress_data['failed_count']}, default=str)}\n\n"
                    else:
                        # Progress update
                        yield f"data: {json.dumps({'type': 'progress', **progress_data}, default=str)}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    # Regular non-streaming response with range support
    try:
        validator = PDFValidator(test_mode=flag)
        
        # Parse year and administration parameters
        year = request.args.get('year', '2025')
        administration = request.args.get('administration', 'all')
        print(f"Validating year: {year}, administration: {administration}")
        
        # Get results from the year-specific method
        results = []
        for progress_data in validator.validate_pdf_urls_with_progress(year, administration):
            if progress_data.get('validation_results') is not None:
                results = progress_data
                break
        
        # Format dates in validation results
        validation_results = results.get('validation_results', [])
        for result in validation_results:
            if 'record' in result and 'TransactionDate' in result['record']:
                if result['record']['TransactionDate']:
                    # Convert datetime to YYYY-MM-DD format
                    date_obj = result['record']['TransactionDate']
                    if hasattr(date_obj, 'strftime'):
                        result['record']['TransactionDate'] = date_obj.strftime('%Y-%m-%d')
                    else:
                        result['record']['TransactionDate'] = str(date_obj)[:10]
        
        return jsonify({
            'success': True,
            'validation_results': validation_results,
            'total_records': results.get('total', 0),
            'ok_count': results.get('ok_count', 0),
            'failed_count': results.get('failed_count', 0)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pdf/update-record', methods=['POST'])
@cognito_required(required_permissions=['invoices_update'])
def pdf_update_record(user_email, user_roles):
    """Update all records with matching Ref3/Ref4"""
    try:
        data = request.get_json()
        old_ref3 = data.get('old_ref3')
        old_ref4 = data.get('old_ref4')
        reference_number = data.get('reference_number')
        ref3 = data.get('ref3')
        ref4 = data.get('ref4')
        
        print(f"Update request: old_ref3={old_ref3}, ref3={ref3}, ref_num={reference_number}")
        
        if not old_ref3:
            return jsonify({'success': False, 'error': 'Original Ref3 is required'}), 400
        
        validator = PDFValidator(test_mode=flag)
        success = validator.update_record(old_ref3, reference_number, ref3, ref4)
        
        if success:
            return jsonify({'success': True, 'message': 'Records updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'No records found to update or no changes made'}), 400
        
    except Exception as e:
        print(f"Update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pdf/get-administrations', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_get_administrations(user_email, user_roles):
    """Get available administrations for a specific year"""
    try:
        year = request.args.get('year', '2025')
        validator = PDFValidator(test_mode=flag)
        administrations = validator.get_administrations_for_year(year)
        
        return jsonify({
            'success': True,
            'administrations': administrations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pdf/validate-single-url', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def pdf_validate_single_url(user_email, user_roles):
    """Validate a single Google Drive URL"""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({'success': False, 'error': 'URL parameter is required'}), 400
        
        validator = PDFValidator(test_mode=flag)
        
        # Create a mock record for validation
        mock_record = {
            'ID': 0,
            'TransactionNumber': '',
            'TransactionDate': '',
            'TransactionDescription': '',
            'TransactionAmount': 0,
            'ReferenceNumber': '',
            'Ref3': url,
            'Ref4': '',
            'Administration': ''
        }
        
        result = validator._validate_single_record(mock_record)
        
        return jsonify({
            'success': True,
            'status': result['status']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Duplicate Detection API endpoints
@app.route('/api/check-duplicate', methods=['POST'])
@cognito_required(required_permissions=['invoices_read'])
def check_duplicate(user_email, user_roles):
    """Check for duplicate transactions during import process"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['referenceNumber', 'transactionDate', 'transactionAmount']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False, 
                    'error': f'Missing required field: {field}'
                }), 400
        
        reference_number = data.get('referenceNumber')
        transaction_date = data.get('transactionDate')
        transaction_amount = float(data.get('transactionAmount'))
        table_name = data.get('tableName', 'mutaties')
        new_file_url = data.get('newFileUrl', '')
        new_file_id = data.get('newFileId', '')
        
        # Initialize duplicate checker with database manager
        db_manager = DatabaseManager(test_mode=flag)
        duplicate_checker = DuplicateChecker(db_manager)
        
        # Check for duplicates
        duplicates = duplicate_checker.check_for_duplicates(
            reference_number, transaction_date, transaction_amount, table_name
        )
        
        # Format duplicate information for frontend
        duplicate_info = duplicate_checker.format_duplicate_info(duplicates)
        
        # Add additional metadata for frontend
        duplicate_info.update({
            'newFileUrl': new_file_url,
            'newFileId': new_file_id,
            'tableName': table_name,
            'checkTimestamp': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True,
            'duplicateInfo': duplicate_info
        })
        
    except ValueError as e:
        return jsonify({
            'success': False, 
            'error': f'Invalid data format: {str(e)}'
        }), 400
    except Exception as e:
        print(f"Duplicate check error: {e}", flush=True)
        # Return graceful degradation - allow import to continue with warning
        return jsonify({
            'success': True,
            'duplicateInfo': {
                'has_duplicates': False,
                'duplicate_count': 0,
                'existing_transactions': [],
                'requires_user_decision': False,
                'error_message': f'Duplicate check failed: {str(e)}',
                'checkTimestamp': datetime.now().isoformat()
            }
        }), 200

@app.route('/api/log-duplicate-decision', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
def log_duplicate_decision(user_email, user_roles):
    """Log user decision regarding duplicate transaction for audit trail"""
    try:
        data = request.get_json()
        print(f"Received duplicate decision data: {data}", flush=True)
        
        # Validate required fields
        decision = data.get('decision')
        if not decision:
            return jsonify({
                'success': False, 
                'error': 'Missing required field: decision'
            }), 400
        
        # Get duplicate info and new transaction data
        # Support both camelCase (from frontend) and snake_case
        duplicate_info = data.get('duplicateInfo') or data.get('duplicate_info')
        new_transaction_data = data.get('newTransactionData') or data.get('new_transaction_data')
        
        # Validate that we have the required data
        if not new_transaction_data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: newTransactionData'
            }), 400
        
        # Ensure duplicate_info is at least an empty dict
        if duplicate_info is None:
            duplicate_info = {}
        
        # Fix existing_transaction_id - convert empty string to None for NULL in database
        existing_id = duplicate_info.get('existing_transaction_id', '')
        if existing_id == '' or existing_id is None:
            existing_id = None
        else:
            try:
                existing_id = int(existing_id)
            except (ValueError, TypeError):
                existing_id = None
        user_id = data.get('userId')
        session_id = data.get('sessionId')
        
        # Validate decision value
        if decision not in ['continue', 'cancel']:
            return jsonify({
                'success': False, 
                'error': 'Decision must be either "continue" or "cancel"'
            }), 400
        
        # Initialize duplicate checker with database manager
        db_manager = DatabaseManager(test_mode=flag)
        duplicate_checker = DuplicateChecker(db_manager)
        
        # Log the decision
        log_success = duplicate_checker.log_duplicate_decision(
            decision=decision,
            duplicate_info=duplicate_info,
            new_transaction_data=new_transaction_data,
            user_id=user_id,
            session_id=session_id
        )
        
        if log_success:
            return jsonify({
                'success': True,
                'message': f'Decision "{decision}" logged successfully',
                'logTimestamp': datetime.now().isoformat()
            })
        else:
            # Even if logging fails, don't block the user's workflow
            return jsonify({
                'success': True,
                'message': f'Decision "{decision}" processed (logging may have failed)',
                'warning': 'Audit logging encountered an issue',
                'logTimestamp': datetime.now().isoformat()
            })
        
    except Exception as e:
        print(f"Decision logging error: {e}", flush=True)
        # Don't fail the user's workflow even if logging fails
        return jsonify({
            'success': True,
            'message': 'Decision processed (logging failed)',
            'error': str(e),
            'logTimestamp': datetime.now().isoformat()
        }), 200

@app.route('/api/handle-duplicate-decision', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
def handle_duplicate_decision(user_email, user_roles):
    """Handle user decision for duplicate transactions with full workflow processing"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['decision', 'duplicateInfo', 'transactions', 'fileData']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False, 
                    'error': f'Missing required field: {field}'
                }), 400
        
        decision = data.get('decision')
        duplicate_info = data.get('duplicateInfo')
        transactions = data.get('transactions')
        file_data = data.get('fileData')
        user_id = data.get('userId')
        session_id = data.get('sessionId')
        
        # Validate decision value
        if decision not in ['continue', 'cancel']:
            return jsonify({
                'success': False, 
                'error': 'Decision must be either "continue" or "cancel"'
            }), 400
        
        # Initialize PDF processor for decision handling
        from pdf_processor import PDFProcessor
        pdf_processor = PDFProcessor(test_mode=flag)
        
        # Handle the user decision
        result = pdf_processor.handle_duplicate_decision(
            decision, duplicate_info, transactions, file_data, user_id, session_id
        )
        
        # If decision was to continue, we need to process the transactions
        if result['success'] and decision == 'continue' and result['transactions']:
            try:
                # Initialize database manager for transaction insertion
                db_manager = DatabaseManager(test_mode=flag)
                
                # Insert transactions into database
                inserted_count = 0
                for transaction in result['transactions']:
                    # Format transaction for database insertion
                    db_transaction = {
                        'TransactionDate': transaction['date'],
                        'TransactionDescription': transaction['description'],
                        'TransactionAmount': transaction['amount'],
                        'Debet': transaction['debet'],
                        'Credit': transaction['credit'],
                        'ReferenceNumber': transaction['ref'],
                        'Ref1': transaction.get('ref1'),
                        'Ref2': transaction.get('ref2'),
                        'Ref3': transaction.get('ref3'),
                        'Ref4': transaction.get('ref4'),
                        'Administration': 'GoodwinSolutions2024'  # Default administration
                    }
                    
                    # Insert transaction
                    success = db_manager.insert_transaction(db_transaction)
                    if success:
                        inserted_count += 1
                
                # Update result with database insertion information
                result['transactions_inserted'] = inserted_count
                result['message'] += f' {inserted_count} transaction(s) inserted into database.'
                
            except Exception as db_error:
                print(f"Database insertion error: {db_error}")
                result['success'] = False
                result['message'] = f"Decision processed but database insertion failed: {str(db_error)}"
        
        return jsonify({
            'success': result['success'],
            'actionTaken': result['action_taken'],
            'message': result['message'],
            'cleanupPerformed': result.get('cleanup_performed', False),
            'transactionsProcessed': len(result.get('transactions', [])),
            'transactionsInserted': result.get('transactions_inserted', 0),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Duplicate decision handling error: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': f'Error handling duplicate decision: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    print("Starting Flask development server...")
    print("For production, use: waitress-serve --host=127.0.0.1 --port=5000 wsgi:app")
    
    # Validate routes before starting
    if not check_route_conflicts(app):
        print("ERROR: Route conflicts detected. Fix before starting.")
        exit(1)
    
    # Add request logging
    @app.before_request
    def log_request():
        if request.path.startswith('/api/'):
            try:
                print(f"API Request: {request.method} {request.path}", flush=True)
            except (OSError, UnicodeError):
                print("API Request: [logging error]", flush=True)
    
    # Get host from environment variable, default to 0.0.0.0 for Docker
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    
    print(f"Starting Flask on {host}:{port} (debug={debug})")
    app.run(debug=debug, port=port, host=host, threaded=True)
