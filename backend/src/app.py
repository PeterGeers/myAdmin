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
from routes.tax_routes import tax_bp
from routes.pdf_validation_routes import pdf_validation_bp
from routes.duplicate_detection_routes import duplicate_detection_bp
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
app.register_blueprint(tax_bp)  # Tax processing endpoints (BTW, tourist tax)
app.register_blueprint(pdf_validation_bp)  # PDF validation endpoints
app.register_blueprint(duplicate_detection_bp)  # Duplicate detection endpoints
app.register_blueprint(static_bp)  # Static file serving (must be registered last)

# Set scalability manager reference for system_health_bp
from routes.system_health_routes import set_scalability_manager
set_scalability_manager(scalability_manager)

# Set scalability manager and test mode for scalability_bp
from scalability_routes import set_scalability_manager as set_scalability_bp_manager, set_test_mode as set_scalability_test_mode
set_scalability_bp_manager(scalability_manager)
set_scalability_test_mode(flag)

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

# Set test mode and logger for tax_bp
from routes.tax_routes import set_test_mode as set_tax_test_mode, set_logger as set_tax_logger
set_tax_test_mode(flag)
set_tax_logger(logger)

# Set test mode for pdf_validation_bp
from routes.pdf_validation_routes import set_test_mode as set_pdf_test_mode
set_pdf_test_mode(flag)

# Set test mode for duplicate_detection_bp
from routes.duplicate_detection_routes import set_test_mode as set_duplicate_test_mode
set_duplicate_test_mode(flag)

# Set test mode and logger for reporting_bp
from reporting_routes import set_test_mode as set_reporting_test_mode, set_logger as set_reporting_logger
set_reporting_test_mode(flag)
set_reporting_logger(logger)

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

# Scalability routes moved to: scalability_routes.py (Phase 5.2)
# - /api/scalability/status
# - /api/scalability/database
# - /api/scalability/performance

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

# Tax processing routes moved to: routes/tax_routes.py (Phase 4.2)
# - /api/btw/generate-report
# - /api/btw/save-transaction
# - /api/btw/upload-report
# - /api/toeristenbelasting/generate-report
# - /api/toeristenbelasting/available-years

# PDF validation routes moved to: routes/pdf_validation_routes.py (Phase 5.1)
# - /api/pdf/validate-urls-stream
# - /api/pdf/validate-urls
# - /api/pdf/update-record
# - /api/pdf/get-administrations
# - /api/pdf/validate-single-url


# Aangifte IB (Income Tax) Report endpoint
# Aangifte IB routes moved to: reporting_routes.py (Phase 5.3)
# - /api/reports/aangifte-ib
# - /api/reports/aangifte-ib-details
# - /api/reports/aangifte-ib-export
# - /api/reports/aangifte-ib-xlsx-export
# - /api/reports/aangifte-ib-xlsx-export-stream

# Duplicate detection routes moved to: routes/duplicate_detection_routes.py (Phase 5.3)
# - /api/check-duplicate
# - /api/log-duplicate-decision
# - /api/handle-duplicate-decision

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
