from flask import jsonify, request
import logging
import traceback
from datetime import datetime
import os

class ErrorHandler:
    """Centralized error handling for Flask application"""
    
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize error handlers for Flask app"""
        self.setup_logging()
        self.register_error_handlers(app)
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(log_dir, 'error.log')),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def register_error_handlers(self, app):
        """Register all error handlers"""
        
        @app.errorhandler(400)
        def handle_bad_request(error):
            return self.format_error_response(400, "Bad Request", str(error))
        
        @app.errorhandler(404)
        def handle_not_found(error):
            return self.format_error_response(404, "Not Found", "Resource not found")
        
        @app.errorhandler(500)
        def handle_internal_error(error):
            self.log_error(error, "Internal Server Error")
            return self.format_error_response(500, "Internal Server Error", "An unexpected error occurred")
        
        @app.errorhandler(Exception)
        def handle_exception(error):
            self.log_error(error, "Unhandled Exception")
            return self.format_error_response(500, "Server Error", str(error))
    
    def format_error_response(self, status_code, error_type, message):
        """Format standardized error response"""
        response = {
            'success': False,
            'error': {
                'type': error_type,
                'message': message,
                'status_code': status_code,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # Add request info in development
        if self.app and self.app.debug:
            response['error']['request'] = {
                'method': request.method,
                'url': request.url,
                'endpoint': request.endpoint
            }
        
        return jsonify(response), status_code
    
    def log_error(self, error, context=""):
        """Log error with context"""
        error_info = {
            'context': context,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'request_method': request.method if request else 'N/A',
            'request_url': request.url if request else 'N/A',
            'traceback': traceback.format_exc()
        }
        
        self.logger.error(f"Error occurred: {error_info}")
    
    @staticmethod
    def handle_api_error(func):
        """Decorator for API route error handling"""
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ValueError as e:
                return jsonify({
                    'success': False,
                    'error': {
                        'type': 'ValidationError',
                        'message': str(e)
                    }
                }), 400
            except FileNotFoundError as e:
                return jsonify({
                    'success': False,
                    'error': {
                        'type': 'FileNotFound',
                        'message': str(e)
                    }
                }), 404
            except Exception as e:
                logging.error(f"API Error in {func.__name__}: {str(e)}")
                logging.error(traceback.format_exc())
                return jsonify({
                    'success': False,
                    'error': {
                        'type': 'ServerError',
                        'message': 'An unexpected error occurred'
                    }
                }), 500
        
        wrapper.__name__ = func.__name__
        return wrapper