"""
Import-boundary guard for the SAM / Lambda plane (spec full-test-suite-fixes-2026-09-26, task M2).

WHY THIS EXISTS
---------------
The SAM plane is deliberately Flask-free: its handlers run on AWS Lambda, not Flask,
and its CI job installs only ``sam/shared/requirements.txt`` (PyJWT / cryptography /
requests) — never the Flask/MySQL backend deps. The handlers do, however, vendor a
handful of Flask-AGNOSTIC helpers out of the backend ``auth`` package
(``auth.cognito_utils``, ``auth.entitlement_*``).

A regression once made the whole ``auth`` package un-importable without Flask:
``auth/__init__.py`` eagerly re-exported ``auth.tenant_context``, which did a
module-level ``from flask import jsonify, request``. Importing ANY ``auth.*`` symbol
therefore imported Flask, and the entire SAM suite collapsed at collection with
``ModuleNotFoundError: No module named 'flask'`` — but ONLY in CI, because a local
dev venv has Flask installed and silently masks it.

This test reproduces the CI condition deterministically (Flask hidden) in a child
process, so re-coupling Flask into the Lambda import path fails fast HERE regardless
of what happens to be installed locally. It complements — it does not replace — the
Flask-free CI job.
"""

import os
import subprocess
import sys
import textwrap

# The Lambda import surface that must stay Flask-free. Each entry is imported in a
# child process from which the real ``flask`` module has been made unavailable.
_LAMBDA_IMPORT_SURFACE = (
    "import auth.cognito_utils",
    "import auth.entitlement_claim_codec",
    "import auth.entitlement_resolver",
    "import sam.pretokengen.handler",
)


def _run_import_with_flask_hidden(import_stmt: str) -> subprocess.CompletedProcess:
    """Run ``import_stmt`` in a child process where importing ``flask`` raises.

    We install a ``meta_path`` finder that blocks ``flask`` (and any ``flask.*``
    submodule) so the import genuinely fails the way the Flask-free Lambda/CI
    environment would — without uninstalling anything from the current venv.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    backend_src = os.path.join(repo_root, "backend", "src")

    prelude = textwrap.dedent(
        """
        import sys
        from importlib.abc import MetaPathFinder

        class _BlockFlask(MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name == "flask" or name.startswith("flask."):
                    raise ModuleNotFoundError("No module named 'flask'")
                return None

        # Front of meta_path + drop any already-imported flask so the block is real.
        sys.meta_path.insert(0, _BlockFlask())
        for _m in [m for m in list(sys.modules) if m == "flask" or m.startswith("flask.")]:
            del sys.modules[_m]
        """
    )

    code = prelude + "\n" + import_stmt + "\n"
    env = dict(os.environ)
    # Mirror the path wiring the handler/conftest do, so `auth.*`/`services.*`/`sam.*`
    # resolve without relying on the parent process's sys.path.
    env["PYTHONPATH"] = os.pathsep.join(
        [backend_src, repo_root, env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )


def test_block_flask_finder_actually_blocks_flask():
    """Sanity check: the child-process Flask block really does make flask unimportable.

    Guards against the test passing vacuously (e.g. if the blocking mechanism broke and
    imports started succeeding only because Flask happens to be installed locally).
    """
    result = _run_import_with_flask_hidden("import flask")
    assert result.returncode != 0, (
        "Expected 'import flask' to FAIL under the Flask block, but it succeeded — "
        "the guard's blocking mechanism is not working.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "No module named 'flask'" in result.stderr


def test_lambda_import_surface_imports_without_flask():
    """Every Flask-free Lambda import must succeed with Flask unavailable (task M2).

    If this fails with ModuleNotFoundError: No module named 'flask', something on the
    ``auth`` / ``sam.pretokengen`` import path re-coupled Flask at module scope. The fix
    is to make that Flask usage lazy (import inside the function that needs it) or to
    move it off the Lambda import path — NOT to add Flask to the SAM environment.
    """
    for import_stmt in _LAMBDA_IMPORT_SURFACE:
        result = _run_import_with_flask_hidden(import_stmt)
        assert result.returncode == 0, (
            f"'{import_stmt}' must import without Flask on the SAM/Lambda plane, "
            f"but it failed:\n{result.stderr}"
        )
        assert "No module named 'flask'" not in result.stderr, (
            f"'{import_stmt}' transitively imported Flask on the Flask-free plane:\n"
            f"{result.stderr}"
        )
