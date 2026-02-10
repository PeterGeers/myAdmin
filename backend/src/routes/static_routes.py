"""
Static file serving routes for myAdmin application.

This blueprint handles serving static files from the React build,
including the main index.html, assets, and various resource files.
"""

from flask import Blueprint, send_from_directory, jsonify, request
import os

# Create blueprint
static_bp = Blueprint('static', __name__)


@static_bp.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files from React build"""
    static_folder = '/app/frontend/build/static'
    return send_from_directory(static_folder, filename)


@static_bp.route('/backend-static/<path:filename>')
def serve_backend_static(filename):
    """Serve backend static files"""
    backend_static_folder = '/app/static'
    return send_from_directory(backend_static_folder, filename)


@static_bp.route('/manifest.json')
def serve_manifest():
    """Serve React manifest.json"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'manifest.json')


@static_bp.route('/favicon.ico')
def serve_favicon():
    """Serve React favicon"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'favicon.ico')


@static_bp.route('/logo192.png')
def serve_logo192():
    """Serve React logo192.png"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'logo192.png')


@static_bp.route('/logo512.png')
def serve_logo512():
    """Serve React logo512.png"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'logo512.png')


@static_bp.route('/jabaki-logo.png')
def serve_jabaki_logo():
    """Serve Jabaki logo"""
    build_folder = '/app/frontend/build'
    return send_from_directory(build_folder, 'jabaki-logo.png')


@static_bp.route('/config.js')
def serve_config():
    """Serve React config.js"""
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    return send_from_directory(build_folder, 'config.js')


@static_bp.route('/')
def serve_index():
    """Serve React index.html"""
    build_folder = '/app/frontend/build'
    try:
        return send_from_directory(build_folder, 'index.html')
    except Exception as e:
        return jsonify({'error': 'Frontend not built', 'details': str(e)}), 404


@static_bp.app_errorhandler(404)
def handle_404(e):
    """Handle 404 errors by serving React app for non-API routes"""
    # For API routes, return JSON error - DO NOT serve HTML
    if request.path.startswith('/api/'):
        print(f"404 API route: {request.path}", flush=True)
        return jsonify({'error': 'API endpoint not found', 'path': request.path}), 404
    
    # Only serve React app for non-API routes
    build_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'build')
    try:
        return send_from_directory(build_folder, 'index.html')
    except:
        return jsonify({'error': 'Frontend not built'}), 404
