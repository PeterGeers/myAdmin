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

# Known GitHub Pages deployments that need a path prefix
GITHUB_PAGES_PATHS = {
    'petergeers.github.io': '/myAdmin',
}


def get_frontend_url() -> str:
    """
    Resolve the frontend URL. Auto-detects from request headers.

    Priority:
    1. X-Frontend-URL custom header (includes path prefix)
    2. Referer header (with GitHub Pages path lookup)
    3. FRONTEND_URL environment variable
    4. http://localhost:3000 (fallback)

    Returns:
        Frontend base URL (no trailing slash)
    """
    # X-Frontend-URL: set by frontend to origin + PUBLIC_URL
    try:
        header = flask_request.headers.get('X-Frontend-URL')
        if header:
            url = header.rstrip('/')
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return url
    except RuntimeError:
        pass

    # Referer: add known path prefix for GitHub Pages hosts
    try:
        referer = flask_request.headers.get('Referer')
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                base = f"{parsed.scheme}://{parsed.netloc}"
                path_prefix = GITHUB_PAGES_PATHS.get(parsed.netloc, '')
                return (base + path_prefix).rstrip('/')
    except RuntimeError:
        pass

    # Env var fallback (for scripts, background tasks)
    return os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
