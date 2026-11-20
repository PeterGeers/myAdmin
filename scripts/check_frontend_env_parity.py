#!/usr/bin/env python3
"""
Guard-rail: the PRODUCTION frontend build config has ONE source of truth.

`scripts/post_deploy_pre_check.py --plane frontend` hard-requires every var in
`FRONTEND_ENV_VARS`. `.github/workflows/deploy-frontend.yml` must therefore define
each of them exactly once, in the workflow-level `env:` block, so the `build` job
and the `deploy` job's post-deploy pre-check inherit THE SAME values.

Why this exists: the two lists were once duplicated, the `deploy` copy used
`secrets.*` for three values that are committed constants in `build`, and the PROD
deploy went red AFTER publishing (`Post-deploy pre-check` failed while
`Deploy to GitHub Pages` had already succeeded).

Checks:
  1. every `FRONTEND_ENV_VARS` entry is defined at workflow level, non-empty;
  2. no `VITE_*` var is redeclared in a step-level `env` (no second list);
  3. the `Post-deploy pre-check` step declares no local `env` (it inherits).

Usage:
  python3 scripts/check_frontend_env_parity.py
  python3 scripts/check_frontend_env_parity.py --workflow .github/workflows/deploy-frontend.yml
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml==6.0.1
    yaml = None

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOW = _ROOT / ".github" / "workflows" / "deploy-frontend.yml"
PRE_CHECK_SCRIPT = _ROOT / "scripts" / "post_deploy_pre_check.py"
PRE_CHECK_STEP_NAME = "Post-deploy pre-check"


def load_required_vars(_script=PRE_CHECK_SCRIPT):
    """Return FRONTEND_ENV_VARS from the pre-check script (single definition)."""
    spec = importlib.util.spec_from_file_location("post_deploy_pre_check", _script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.FRONTEND_ENV_VARS)


def load_workflow(path=DEFAULT_WORKFLOW):
    if yaml is None:
        raise SystemExit("ERROR: PyYAML is required (pip install pyyaml==6.0.1)")
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def iter_step_envs(workflow):
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            yield job_name, step.get("name"), step.get("env") or {}


def check_env_parity(workflow, required_vars):
    """Return a list of problems; an empty list means the guard passed."""
    problems = []
    env = workflow.get("env") or {}
    for var in required_vars:
        if not str(env.get(var, "")).strip():
            problems.append(
                f"workflow-level env is missing required var {var!r} "
                "(post_deploy_pre_check.py FRONTEND_ENV_VARS)"
            )
    for job_name, step_name, step_env in iter_step_envs(workflow):
        for key in step_env:
            if str(key).startswith("VITE_"):
                problems.append(
                    f"step-level env redeclares {key!r} in {job_name}/{step_name}: "
                    "VITE_* must live only in the workflow-level env block"
                )
    deploy_steps = ((workflow.get("jobs") or {}).get("deploy") or {}).get("steps") or []
    pre_checks = [s for s in deploy_steps if s.get("name") == PRE_CHECK_STEP_NAME]
    if len(pre_checks) != 1:
        problems.append(
            f"expected exactly one {PRE_CHECK_STEP_NAME!r} step in the deploy job, "
            f"found {len(pre_checks)}"
        )
    elif "env" in pre_checks[0]:
        problems.append(
            f"{PRE_CHECK_STEP_NAME!r} declares a local env block; it must inherit the "
            "workflow-level env (the same source the build used)"
        )
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW))
    args = parser.parse_args()

    required = load_required_vars()
    problems = check_env_parity(load_workflow(args.workflow), required)

    if problems:
        print("FAIL: deploy-frontend.yml frontend env is NOT single-source:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"OK: deploy-frontend.yml defines all {len(required)} required frontend vars "
        "once, at workflow level (build + post-deploy pre-check share them)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
