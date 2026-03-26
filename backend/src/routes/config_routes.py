"""
Configuration Routes

Public endpoints for application configuration:
- GET /api/config/ledger-parameters — Predefined ledger account parameter definitions
"""

import os
import json
import logging
from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

config_bp = Blueprint('config', __name__, url_prefix='/api/config')

# Load ledger parameters once at import time
_ledger_parameters = None


def _get_ledger_parameters():
    global _ledger_parameters
    if _ledger_parameters is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'config', 'ledger_parameters.json'
        )
        try:
            with open(config_path, encoding='utf-8') as f:
                _ledger_parameters = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load ledger_parameters.json: {e}")
            _ledger_parameters = []
    return _ledger_parameters


@config_bp.route('/ledger-parameters', methods=['GET'])
def get_ledger_parameters():
    """
    Get predefined ledger account parameter definitions.

    Public endpoint — no authentication required.
    Used by the Account Modal to render the parameter editor.

    Returns:
        Array of parameter definitions with key, type, labels, and metadata.
    """
    return jsonify(_get_ledger_parameters())
