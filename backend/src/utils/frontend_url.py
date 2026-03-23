"""
Frontend URL Resolution Utility

Resolves the frontend URL for use in emails and redirects.

Priority:
1. FRONTEND_URL env var (production — set in Railway)
2. Referer header (localhost dev — CRA proxy preserves origin)
3. http://localhost:3000 (fallback)

Why env var for production:
- CRA proxy strips custom headers on localhost
- Cross-origin Referrer-Policy strips path from Referer
- Browser may silently drop custom headers on CORS preflight
- A single env var is reliable and portable across any hosting
"""

import os
from urllib.parse import urlparse
from flask import request as flask_request


def get_frontend_url() -> str:
    """
    Resolve the frontend URL.

    Returns:
        Frontend base URL (no trailing slash)
    """
    # Production: env var is the source of truth
    env_url = os.getenv('FRONTEND_URL')
    if env_url:
        return env_url.rstrip('/')

    # Local dev: Referer has the real frontend origin
    try:
        referer = flask_request.headers.get('Referer')
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
    except RuntimeError:
        pass

    return 'http://localhost:3000'
