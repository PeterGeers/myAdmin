"""
Internationalization (i18n) utilities for Flask backend.

This module provides Flask-Babel configuration and locale detection
based on the X-Language header sent by the frontend.
"""

from flask import request
from flask_babel import Babel


def get_locale():
    """
    Determine locale from X-Language header or default to 'nl'.
    
    The frontend sends the user's language preference via the X-Language header.
    If no header is present, defaults to Dutch (nl).
    
    Returns:
        str: Language code ('nl' or 'en')
    """
    language = request.headers.get('X-Language', 'nl')
    
    # Validate language code (only allow nl or en)
    if language not in ['nl', 'en']:
        language = 'nl'
    
    return language


def init_babel(app):
    """
    Initialize Flask-Babel with the Flask application.
    
    Args:
        app: Flask application instance
        
    Returns:
        Babel: Configured Babel instance
    """
    babel = Babel(app, locale_selector=get_locale)
    print("✅ Flask-Babel initialized with locale selector", flush=True)
    return babel
