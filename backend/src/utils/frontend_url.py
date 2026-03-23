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
    1. X-Frontend-URL custom header — includes path prefix for GitHub Pages
       (e.g. https://petergeers.github.io/myAdmin)
    2. Referer header — origin only (CRA proxy preserves this)
    3. FRONTEND_URL environment variable
    4. http://localhost:3000 (hardcoded fallback)
    
    NOTE: Origin is NOT used — CRA proxy sets it to the backend URL.
    
    Returns:
        Frontend base URL (no trailing slash)
    """
    # X-Frontend-URL is set by frontend to window.location.origin + PUBLIC_URL
    # This includes the path prefix for GitHub Pages (e.g. /myAdmin)
    # CRA proxy strips this, but it works for direct CORS requests
    try:
        frontend_header = flask_request.headers.get('X-Frontend-URL')
        if frontend_header:
            url = frontend_header.rstrip('/')
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return url
    except RuntimeError:
        pass

    # Referer header — origin only (path is the current page, not the base)
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
