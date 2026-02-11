"""WSGI entry point for production deployment."""
from src.app import app

# Expose app at module level for WSGI servers
application = app

if __name__ == "__main__":
    app.run()