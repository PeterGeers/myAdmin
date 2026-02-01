import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flask import Flask
from error_handlers import (
    configure_logging, 
    error_response, 
    register_error_handlers, 
    user_friendly_error
)

def test_configure_logging():
    """Test logging configuration"""
    app = Flask(__name__)
    logger = configure_logging(app)
    
    assert logger is not None
    assert len(app.logger.handlers) >= 1  # At least file handler

def test_error_response_format():
    """Test error response formatting"""
    app = Flask(__name__)
    
    with app.app_context():
        response, status_code = error_response(
            "Test error message", 500, detail="test detail"
        )
        
        data = response.get_json()
        assert data['success'] == False
        assert data['error'] == "Test error message"
        assert data['status_code'] == 500
        assert data['detail'] == "test detail"
        assert status_code == 500

def test_error_response_without_details():
    """Test error response without details"""
    app = Flask(__name__)
    
    with app.app_context():
        response, status_code = error_response("Bad request", 400)
        
        data = response.get_json()
        assert data['success'] == False
        assert data['error'] == "Bad request"
        assert data['status_code'] == 400
        assert status_code == 400

def test_user_friendly_error():
    """Test user-friendly error messages"""
def test_user_friendly_error_validation():
    """Test user-friendly error for validation errors"""
    app = Flask(__name__)
    
    with app.app_context():
        message = user_friendly_error("VALIDATION_ERROR")
        
        assert message is not None
        assert isinstance(message, str)
        assert len(message) > 0

def test_user_friendly_error_unknown_type():
    """Test user-friendly error with unknown error type"""
    app = Flask(__name__)
    
    with app.app_context():
        message = user_friendly_error("UNKNOWN_ERROR")
        
        assert message is not None
        assert isinstance(message, str)
        assert "error" in message.lower()

def test_register_error_handlers():
    """Test error handler registration"""
    app = Flask(__name__)
    register_error_handlers(app)
    
    # Check that error handlers are registered
    assert 400 in app.error_handler_spec[None]
    assert 404 in app.error_handler_spec[None]
    assert 500 in app.error_handler_spec[None]