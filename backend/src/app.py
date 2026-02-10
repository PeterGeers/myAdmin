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
from routes.sysadmin_routes import sysadmin_bp
from routes.tenant_admin_users import tenant_admin_users_bp
from routes.sysadmin_health import sysadmin_health_bp
from routes.tenant_admin_credentials import tenant_admin_credentials_bp
from routes.tenant_admin_storage import tenant_admin_storage_bp
from routes.tenant_admin_settings import tenant_admin_settings_bp
from routes.tenant_admin_config import tenant_admin_config_bp
from routes.tenant_admin_details import tenant_admin_details_bp
from routes.tenant_admin_email import tenant_admin_email_bp
from routes.static_routes import static_bp
from routes.system_health_routes import system_health_bp
from routes.cache_routes import cache_bp
from routes.folder_routes import folder_bp
from routes.invoice_routes import invoice_bp
from routes.banking_routes import banking_bp
from routes.str_routes import str_bp
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
app.register_blueprint(sysadmin_bp)
app.register_blueprint(tenant_admin_users_bp)
app.register_blueprint(tenant_admin_credentials_bp)
app.register_blueprint(tenant_admin_storage_bp)
app.register_blueprint(tenant_admin_settings_bp)
app.register_blueprint(tenant_admin_config_bp)
app.register_blueprint(tenant_admin_details_bp)
app.register_blueprint(tenant_admin_email_bp)
app.register_blueprint(sysadmin_health_bp, url_prefix='/api/sysadmin/health')
app.register_blueprint(system_health_bp)  # System health and status endpoints
app.register_blueprint(cache_bp)  # Cache management endpoints
app.register_blueprint(folder_bp)  # Folder management endpoints
app.register_blueprint(invoice_bp)  # Invoice processing endpoints
app.register_blueprint(banking_bp)  # Banking transaction processing endpoints
app.register_blueprint(str_bp)  # STR and pricing endpoints
app.register_blueprint(static_bp)  # Static file serving (must be registered last)

# Set scalability manager reference for system_health_bp
from routes.system_health_routes import set_scalability_manager
set_scalability_manager(scalability_manager)

# Set test mode flag for cache_bp
from routes.cache_routes import set_test_mode
set_test_mode(flag)

# Set config and flag for folder_bp (after config is instantiated)
# This is done later after config is created

# Set test mode flag for invoice_bp
from routes.invoice_routes import set_test_mode as set_invoice_test_mode
set_invoice_test_mode(flag)

# Set test mode flag for banking_bp
from routes.banking_routes import set_test_mode as set_banking_test_mode
set_banking_test_mode(flag)

# Set config for str_bp - import here, call later after UPLOAD_FOLDER is defined
from routes.str_routes import set_config as set_str_config


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
    # Use the organized OpenAPI spec in openapi/ directory
    spec_path = os.path.join(os.path.dirname(__file__), 'openapi', 'openapi_spec.yaml')
    with open(spec_path, 'r') as f:
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
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Tenant"]
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

# Set config and flag for folder_bp (must be after config is instantiated)
from routes.folder_routes import set_config_and_flag
set_config_and_flag(config, flag)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'csv', 'mhtml', 'eml'}

# Set config for str_bp (must be after UPLOAD_FOLDER is defined)
set_str_config(UPLOAD_FOLDER, flag)

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
# MOVED TO: routes/static_routes.py (static_bp)
# All static file serving routes have been extracted to the static_routes blueprint

# Folder management routes moved to: routes/folder_routes.py (Phase 1.4)
# - /api/folders
# - /api/create-folder

# System health routes moved to: routes/system_health_routes.py (Phase 1.2)
# - /api/test
# - /api/status
# - /api/str/test
# - /api/health
# - /api/google-drive/token-health

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

# Cache management routes moved to: routes/cache_routes.py (Phase 1.3)
# - /api/cache/warmup
# - /api/cache/status
# - /api/cache/refresh
# - /api/cache/invalidate
# - /api/bnb-cache/status
# - /api/bnb-cache/refresh
# - /api/bnb-cache/invalidate

# Folder management routes moved to: routes/folder_routes.py (Phase 1.4)
# - /api/create-folder

# Invoice processing routes moved to: routes/invoice_routes.py (Phase 2.2)
# - /api/upload
# - /api/approve-transactions

@app.errorhandler(500)
def handle_500(e):
    print(f"500 error: {e}")
    return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

# Banking processor routes moved to: routes/banking_routes.py (Phase 3.2)
# - /api/banking/scan-files
# - /api/banking/process-files
# - /api/banking/check-sequences
# - /api/banking/apply-patterns
# - /api/banking/save-transactions
# - /api/banking/lookups
# - /api/banking/mutaties
# - /api/banking/filter-options
# - /api/banking/update-mutatie
# - /api/banking/check-accounts
# - /api/banking/check-sequence
# - /api/banking/check-revolut-balance
# - /api/banking/check-revolut-balance-debug
# - /api/banking/migrate-revolut-ref2

# STR (Short-Term Rental) and Pricing routes moved to: routes/str_routes.py (Phase 4.1)
# - /api/str/upload
# - /api/str/save
# - /api/str/write-future
# - /api/str/import-payout
# - /api/str/summary
# - /api/str/future-trend
# - /api/pricing/generate
# - /api/pricing/recommendations
# - /api/pricing/historical
# - /api/pricing/listings
# - /api/pricing/multipliers

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
