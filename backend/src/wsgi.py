"""WSGI entry point for production deployment."""
from app import app

# Expose app at module level for WSGI servers (both names for compatibility)
application = app

if __name__ == "__main__":
    app.run()