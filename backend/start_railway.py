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

print(f"🔍 Backend dir: {backend_dir}", flush=True)
print(f"🔍 Src dir: {src_dir}", flush=True)
print(f"🔍 Src dir exists: {src_dir.exists()}", flush=True)
print(f"🔍 Services dir exists: {(src_dir / 'services').exists()}", flush=True)
print(f"🔍 credential_service.py exists: {(src_dir / 'services' / 'credential_service.py').exists()}", flush=True)

# Add src directory to Python path so imports work
sys.path.insert(0, str(src_dir))
print(f"🔍 sys.path[0]: {sys.path[0]}", flush=True)

# Change to src directory so relative file operations work
os.chdir(src_dir)
print(f"🔍 Current working directory: {os.getcwd()}", flush=True)

# Now import and run the app
print("🔍 Attempting to import app...", flush=True)
from app import app
print("✅ App imported successfully!", flush=True)

if __name__ == '__main__':
    # Get configuration from environment
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', os.getenv('PORT', '5000')))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    print(f"🚀 Starting Flask on {host}:{port} (debug={debug})", flush=True)
    app.run(debug=debug, port=port, host=host, threaded=True)
