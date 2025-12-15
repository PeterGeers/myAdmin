import logging
from logging.handlers import RotatingFileHandler
from flask import jsonify, request
from functools import wraps
import traceback
import os
from datetime import datetime

# Configure logging
def configure_logging(app):
    """Configure comprehensive logging for the application"""
    logs_dir = os.path.join(app.root_path, '..', 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Create rotating file handler
    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, 'api_errors.log'),
        maxBytes=1024 * 1024 * 5,  # 5 MB
        backupCount=5
    )

    # Set log format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s - [in %(pathname)s:%(lineno)d]'
    )
    file_handler.setFormatter(formatter)

    # Set log level
    file_handler.setLevel(logging.ERROR)

    # Add handler to app logger
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.ERROR)

    # Console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    app.logger.addHandler(console_handler)

    return app.logger

# Standard error response format
def error_response(error_code, error_message, details=None, status='error'):
    """Create standardized error response"""
    response = {
        'success': False,
        'error': error_message,
        'code': error_code,
        'status': status,
        'timestamp': datetime.now().isoformat()
    }

    if details:
        response['details'] = details

    return jsonify(response), error_code

# Database transaction decorator with rollback
def with_transaction(db_manager):
    """Decorator for database operations with automatic rollback on error"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            conn = None
            cursor = None
            try:
                conn = db_manager.get_connection()
                cursor = conn.cursor(dictionary=True)
                conn.begin()  # Start transaction

                # Add connection and cursor to kwargs for the function to use
                kwargs['_db_conn'] = conn
                kwargs['_db_cursor'] = cursor

                result = f(*args, **kwargs)

                conn.commit()
                return result

            except Exception as e:
                if conn:
                    conn.rollback()
                error_details = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'traceback': traceback.format_exc()
                }
                app.logger.error(f"Database transaction failed: {error_details}")
                return error_response(500, "Database operation failed", error_details)

            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        return wrapper
    return decorator

# API error handlers
def register_error_handlers(app):
    """Register global error handlers for the Flask app"""

    @app.errorhandler(400)
    def bad_request(error):
        app.logger.warning(f"Bad request: {error}")
        return error_response(400, "Bad request", str(error))

    @app.errorhandler(401)
    def unauthorized(error):
        app.logger.warning(f"Unauthorized access: {error}")
        return error_response(401, "Unauthorized access", str(error))

    @app.errorhandler(403)
    def forbidden(error):
        app.logger.warning(f"Forbidden: {error}")
        return error_response(403, "Access forbidden", str(error))

    @app.errorhandler(404)
    def not_found(error):
        app.logger.warning(f"Not found: {error}")
        return error_response(404, "Resource not found", str(error))

    @app.errorhandler(405)
    def method_not_allowed(error):
        app.logger.warning(f"Method not allowed: {error}")
        return error_response(405, "Method not allowed", str(error))

    @app.errorhandler(413)
    def request_entity_too_large(error):
        app.logger.warning(f"Request too large: {error}")
        return error_response(413, "Request entity too large", "File size exceeds limit")

    @app.errorhandler(500)
    def internal_server_error(error):
        error_id = datetime.now().strftime('%Y%m%d%H%M%S%f')
        app.logger.error(f"Internal server error [{error_id}]: {error}")
        return error_response(500, "Internal server error", f"Error ID: {error_id}")

    @app.errorhandler(Exception)
    def handle_exception(error):
        error_id = datetime.now().strftime('%Y%m%d%H%M%S%f')
        error_details = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'error_id': error_id
        }
        app.logger.error(f"Unhandled exception [{error_id}]: {error_details}")
        return error_response(500, "An unexpected error occurred", error_details)

# Request validation decorator
def validate_request(schema=None, data_source='json'):
    """Decorator to validate request data against a schema"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                if data_source == 'json':
                    data = request.get_json()
                elif data_source == 'form':
                    data = request.form.to_dict()
                elif data_source == 'args':
                    data = request.args.to_dict()
                else:
                    return error_response(400, "Invalid data source specified")

                if schema and data:
                    from jsonschema import validate, ValidationError
                    try:
                        validate(instance=data, schema=schema)
                    except ValidationError as ve:
                        app.logger.warning(f"Validation error: {ve}")
                        return error_response(400, "Validation failed", str(ve))

                return f(*args, **kwargs)

            except Exception as e:
                app.logger.warning(f"Request validation error: {e}")
                return error_response(400, "Invalid request format", str(e))
        return wrapper
    return decorator

# User-friendly error messages
USER_FRIENDLY_ERRORS = {
    "database_connection": "We're having trouble connecting to the database. Please try again later.",
    "file_upload": "There was a problem uploading your file. Please check the file format and try again.",
    "validation": "The data you provided doesn't meet our requirements. Please check your input.",
    "authentication": "Your session has expired. Please log in again.",
    "resource_not_found": "The requested resource could not be found.",
    "permission_denied": "You don't have permission to perform this action.",
    "rate_limit": "You've made too many requests. Please wait a few minutes and try again."
}

def user_friendly_error(error_type, technical_details=None):
    """Convert technical errors to user-friendly messages"""
    friendly_message = USER_FRIENDLY_ERRORS.get(error_type, "An error occurred. Please try again.")

    response = {
        'success': False,
        'message': friendly_message,
        'status': 'error'
    }

    # Only include technical details in development mode
    if os.getenv('FLASK_ENV') == 'development' and technical_details:
        response['technical_details'] = technical_details

    return jsonify(response), 400 if error_type == 'validation' else 500
