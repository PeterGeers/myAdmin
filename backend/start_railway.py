#!/usr/bin/env python3
"""
Railway startup script that properly configures Python path before importing the app.
This ensures all imports work correctly regardless of the working directory.
"""
import sys
import os
from pathlib import Path

# Get the absolute path to the backend directory
backend_dir = Path(__file__).parent.absolute()
src_dir = backend_dir / 'src'

# Add src directory to Python path so imports work
sys.path.insert(0, str(src_dir))

# Change to src directory so relative file operations work
os.chdir(src_dir)

# Now import and run the app
from app import app

if __name__ == '__main__':
    # Get configuration from environment
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', os.getenv('PORT', '5000')))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    print(f"🚀 Starting Flask on {host}:{port} (debug={debug})", flush=True)
    app.run(debug=debug, port=port, host=host, threaded=True)
