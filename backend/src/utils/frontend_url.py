"""
Frontend URL Resolution Utility

Auto-detects the frontend URL from request headers.
CRA proxy strips custom headers (X-Frontend-URL) and sets Origin to the
backend URL, but preserves Referer with the real frontend URL.
"""

import os
from urllib.parse import urlparse
from flask import request as flask_request
import logging

logger = logging.getLogger(__name__)


def get_frontend_url() -> str:
    """
    Resolve the frontend URL. Auto-detects from request headers.
    
    Priority:
    1. X-Frontend-URL custom header (works for direct/CORS requests)
    2. Referer header (CRA proxy preserves this with real frontend URL)
    3. FRONTEND_URL environment variable
    4. http://localhost:3000 (hardcoded fallback)
    
    NOTE: Origin is NOT used — CRA proxy sets it to the backend URL.
    
    Returns:
        Frontend base URL (no trailing slash)
    """
    # X-Frontend-URL is set by the frontend to window.location.origin
    # CRA proxy strips this, but it works for direct CORS requests
    try:
        frontend_header = flask_request.headers.get('X-Frontend-URL')
        if frontend_header:
            parsed = urlparse(frontend_header)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
    except RuntimeError:
        pass

    # Referer header — CRA proxy preserves this with the real frontend URL
    try:
        referer = flask_request.headers.get('Referer')
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
    except RuntimeError:
        pass

    # Env var fallback (for scripts, background tasks)
    return os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
