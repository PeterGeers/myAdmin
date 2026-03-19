"""
Shared Rate Limiter

Provides a Flask-Limiter instance that can be imported by routes
without circular import issues.

Usage in routes:
    from shared_limiter import limiter
    
    @bp.route('/api/endpoint')
    @limiter.limit("5 per hour")
    def endpoint():
        ...

Must be initialized in app.py:
    from shared_limiter import init_limiter
    init_limiter(app)
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Global limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://"
)


def init_limiter(app):
    """Initialize the limiter with the Flask app"""
    limiter.init_app(app)
