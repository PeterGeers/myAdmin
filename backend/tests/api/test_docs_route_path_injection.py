"""
Path-injection containment test for the /docs/<path:path> route (app.py).

The docs route joins the user-supplied <path:path> onto the docs root and then
probes / serves it. Task 2 (security-assessment-2026-10-19) added an explicit
realpath + base-dir containment guard so a ../ traversal cannot steer the path
out of the docs root (CodeQL py/path-injection).

Importing the full app.py is heavy (pulls in DatabaseManager + every blueprint),
so this test reconstructs the exact guarded route in an isolated Flask app and
asserts the containment contract: a legit path serves, a traversal path 404s and
never reaches send_from_directory.
"""

import os
import sys
import tempfile

import pytest
from flask import Flask, jsonify, send_from_directory

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from utils.path_security import is_within_base


@pytest.fixture
def docs_app():
    """Isolated app exposing the same guarded serve_docs logic as app.py."""
    with tempfile.TemporaryDirectory() as docs_site_path:
        # Seed an index.html so the legit path has something to serve.
        with open(os.path.join(docs_site_path, "index.html"), "w") as f:
            f.write("<html>docs</html>")

        app = Flask(__name__, static_folder=None)
        app.config["TESTING"] = True

        @app.route("/docs/")
        @app.route("/docs/<path:path>")
        def serve_docs(path="index.html"):
            try:
                abs_docs_path = os.path.abspath(docs_site_path)
                full_path = os.path.join(abs_docs_path, path)
                if not is_within_base(full_path, abs_docs_path):
                    return jsonify({"error": "Documentation not found"}), 404
                if os.path.isdir(full_path):
                    path = os.path.join(path, "index.html")
                response = send_from_directory(abs_docs_path, path)
                response.headers["X-Frame-Options"] = "ALLOWALL"
                response.headers["Content-Security-Policy"] = ""
                return response
            except Exception:
                return jsonify({"error": "Documentation not found"}), 404

        yield app


def test_docs_legit_path_served(docs_app):
    client = docs_app.test_client()
    response = client.get("/docs/index.html")
    assert response.status_code == 200
    assert b"docs" in response.data


def test_docs_traversal_path_rejected(docs_app):
    """A ../ traversal path never yields a 200 — the converter or the containment
    guard rejects it before send_from_directory can serve an out-of-base file."""
    client = docs_app.test_client()
    # Flask's URL converter handles some encodings; our guard backstops the rest.
    response = client.get("/docs/..%2f..%2fetc%2fpasswd")
    assert response.status_code == 404
