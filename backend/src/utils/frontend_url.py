"""
Frontend URL Resolution Utility

Resolves the frontend URL for use in emails and redirects.

Priority:
1. X-Frontend-URL header (sent by frontend, includes path prefix)
   Works on production (direct CORS), stripped by CRA proxy on localhost
2. Referer header origin (works on localhost via CRA proxy)
3. FRONTEND_URL env var (background tasks, scripts, or override)
4. http://localhost:3000 (fallback)
"""

import os
from urllib.parse import urlparse
from flask import request as flask_request


def get_frontend_url() -> str:
    """
    Resolve the frontend URL. No hardcoded host mappings.

    Returns:
        Frontend base URL (no trailing slash)
    """
    # 1. X-Frontend-URL: frontend sends origin + PUBLIC_URL
    #    e.g. https://petergeers.github.io/myAdmin
    #    Works on production CORS, stripped by CRA proxy locally
    try:
        header = flask_request.headers.get('X-Frontend-URL')
        if header:
            url = header.rstrip('/')
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return url
    except RuntimeError:
        pass

    # 2. Referer: origin only (localhost dev via CRA proxy)
    try:
        referer = flask_request.headers.get('Referer')
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
    except RuntimeError:
        pass

    # 3. Env var (background tasks, scripts, or manual override)
    env_url = os.getenv('FRONTEND_URL')
    if env_url:
        return env_url.rstrip('/')

    return 'http://localhost:3000'
