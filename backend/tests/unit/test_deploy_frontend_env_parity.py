"""Unit tests for scripts/check_frontend_env_parity.py (frontend env guard).

Pins that the PRODUCTION frontend build config has ONE source of truth: the
workflow-level ``env:`` block of ``.github/workflows/deploy-frontend.yml``, shared
by the ``build`` job and the ``deploy`` job's post-deploy pre-check.

Also pins that the checker FLAGS each drift mode when re-introduced (missing or
empty required var, step-level ``VITE_*`` redeclaration, pre-check with a local
``env`` block, missing pre-check step). See the fallback-patterns spec: a
duplicated list made the PROD deploy red after the Pages publish succeeded.
"""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _ROOT / "scripts" / "check_frontend_env_parity.py"


def _load_checker_module():
    spec = importlib.util.spec_from_file_location("check_frontend_env_parity", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parity = _load_checker_module()
REQUIRED = list(parity.load_required_vars())


def _workflow_with(**overrides):
    """A minimal valid workflow; top-level ``env``/``jobs`` can be overridden."""
    workflow = {
        "env": {var: "value" for var in REQUIRED},
        "jobs": {
            "build": {"steps": [{"name": "Build frontend", "env": {"CI": "false"}}]},
            "deploy": {"steps": [{"name": "Post-deploy pre-check"}]},
        },
    }
    workflow.update(overrides)
    return workflow


def test_checker_passes_on_the_repo_workflow():
    assert parity.check_env_parity(parity.load_workflow(), REQUIRED) == []


def test_required_vars_are_the_vite_family():
    assert REQUIRED, "FRONTEND_ENV_VARS must not be empty"
    assert all(var.startswith("VITE_") for var in REQUIRED), REQUIRED


def test_flags_missing_required_var():
    workflow = _workflow_with()
    del workflow["env"]["VITE_MEMBERS_API_BASE_URL"]
    problems = parity.check_env_parity(workflow, REQUIRED)
    assert any("VITE_MEMBERS_API_BASE_URL" in p for p in problems), problems


def test_flags_empty_required_var():
    workflow = _workflow_with()
    workflow["env"]["VITE_API_URL"] = "   "
    problems = parity.check_env_parity(workflow, REQUIRED)
    assert any("VITE_API_URL" in p for p in problems), problems


def test_flags_step_level_vite_redeclaration():
    workflow = _workflow_with()
    workflow["jobs"]["build"]["steps"][0]["env"]["VITE_API_URL"] = (
        "${{ secrets.VITE_API_URL }}"
    )
    problems = parity.check_env_parity(workflow, REQUIRED)
    assert any("redeclares 'VITE_API_URL'" in p for p in problems), problems


def test_flags_pre_check_step_with_local_env():
    workflow = _workflow_with()
    workflow["jobs"]["deploy"]["steps"][0]["env"] = {
        "VITE_REDIRECT_SIGN_IN": "https://example.invalid/"
    }
    problems = parity.check_env_parity(workflow, REQUIRED)
    assert any("local env block" in p for p in problems), problems


def test_flags_missing_pre_check_step():
    workflow = _workflow_with(jobs={"build": {"steps": []}, "deploy": {"steps": []}})
    problems = parity.check_env_parity(workflow, REQUIRED)
    assert any("expected exactly one" in p for p in problems), problems
