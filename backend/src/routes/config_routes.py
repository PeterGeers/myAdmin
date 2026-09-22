"""
Configuration Routes

Public endpoints for application configuration:
- GET /api/config/ledger-parameters — Predefined ledger account parameter definitions
- GET /api/config/members-parameters — Predefined members parameter (typed-editor) definitions
"""

import json
import logging
import os

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

logger = logging.getLogger(__name__)

config_bp = Blueprint("config", __name__, url_prefix="/api/config")

# Load ledger parameters once at import time
_ledger_parameters = None


def _get_ledger_parameters() -> dict:
    global _ledger_parameters
    if _ledger_parameters is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "ledger_parameters.json",
        )
        try:
            with open(config_path, encoding="utf-8") as f:
                _ledger_parameters = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load ledger_parameters.json: {e}")
            _ledger_parameters = []
    return _ledger_parameters


@config_bp.route("/ledger-parameters", methods=["GET"])
def get_ledger_parameters() -> ResponseReturnValue:
    """
    Get predefined ledger account parameter definitions.

    Public endpoint — no authentication required.
    Used by the Account Modal to render the parameter editor.

    Returns:
        Array of parameter definitions with key, type, labels, and metadata.
    """
    return jsonify(_get_ledger_parameters())


# Load members parameters once at import time
_members_parameters = None


def _get_members_parameters() -> dict:
    global _members_parameters
    if _members_parameters is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "members_parameters.json",
        )
        try:
            with open(config_path, encoding="utf-8") as f:
                _members_parameters = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load members_parameters.json: {e}")
            _members_parameters = []
    return _members_parameters


@config_bp.route("/members-parameters", methods=["GET"])
def get_members_parameters() -> ResponseReturnValue:
    """
    Get predefined members parameter (typed-editor) definitions.

    Public endpoint — no authentication required (analogous to
    GET /api/config/ledger-parameters). Used by the Members typed authoring
    editor to render the parameter editor for the three ``members.*`` params.

    The definition language extends the ledger def set (key, type, label_en/
    label_nl, description, depends_on, options, module) with two composite
    types Members needs: ``list<object>`` (scope_dimensions, view_contexts,
    the functional_groups catalog) and ``map<field_def>`` (field_overlay,
    each field carrying a functional_group).

    Returns:
        Array of parameter definitions with key, type, labels, and metadata.
    """
    return jsonify(_get_members_parameters())
