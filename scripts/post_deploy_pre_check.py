#!/usr/bin/env python3
"""
Post-deploy pre-check (Deliverable #5).

Runs AFTER a deploy and verifies the deployed environment is sane:
  1. Required env vars for the PLANE (frontend: VITE_*; sam: AWS region)
  2. Cognito configuration (frontend plane only)
  3. Projection freshness (best-effort DynamoDB governance_projection updated_at;
     WARNING-level, never a hard failure; SKIPPED when boto3 or the table name
     is unavailable)

Plane-aware (--plane frontend|sam|auto). The SAM deploy job has NO VITE_* vars
and NO MySQL, so this script NEVER imports the Flask DB layer. A projection
freshness problem is surfaced as a WARNING, not a deploy blocker.

Exit codes: 0 = passed (possibly with warnings); 1 = hard error (missing
required config for the plane).
"""

import argparse
import os
import sys
from datetime import datetime, timezone

FRONTEND_ENV_VARS = [
    "VITE_API_URL",
    "VITE_COGNITO_USER_POOL_ID",
    "VITE_COGNITO_CLIENT_ID",
    "VITE_COGNITO_DOMAIN",
    "VITE_AWS_REGION",
    "VITE_REDIRECT_SIGN_IN",
    "VITE_REDIRECT_SIGN_OUT",
    "VITE_MEMBERS_API_BASE_URL",
]

COGNITO_VARS = [
    "VITE_COGNITO_USER_POOL_ID",
    "VITE_COGNITO_CLIENT_ID",
    "VITE_COGNITO_DOMAIN",
]


def resolve_plane(requested):
    """--plane auto: frontend if any VITE_* is set, else sam."""
    if requested in ("frontend", "sam"):
        return requested
    if any(os.environ.get(v) for v in FRONTEND_ENV_VARS):
        return "frontend"
    return "sam"


def check_env_vars(plane):
    errors = []
    if plane == "frontend":
        for var in FRONTEND_ENV_VARS:
            if not os.environ.get(var):
                errors.append(f"Missing required env var: {var}")
    else:
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            errors.append(
                "Missing required env var: AWS_REGION (or AWS_DEFAULT_REGION)"
            )
    return (not errors), errors


def check_cognito_config(plane):
    if plane != "frontend":
        return True, []
    errors = [
        f"Missing Cognito config: {v}" for v in COGNITO_VARS if not os.environ.get(v)
    ]
    return (not errors), errors


CANDIDATE_TS_ATTRS = ("updated_at", "projection_timestamp", "version_ts", "updatedAt")
PROJECTION_TABLE_ENV = ("GOVERNANCE_PROJECTION_TABLE", "PROJECTION_TABLE_NAME")


def _projection_table_name(env):
    for key in PROJECTION_TABLE_ENV:
        if os.environ.get(key):
            return os.environ[key]
    try:
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        cfg_path = root / "sam" / "members" / "samconfig.toml"
        cfg = tomllib.loads(cfg_path.read_text("utf-8"))
        overrides = (
            cfg.get(env, {})
            .get("deploy", {})
            .get("parameters", {})
            .get("parameter_overrides", [])
        )
        for kv in overrides:
            if isinstance(kv, str) and kv.startswith("GovernanceProjectionTableName="):
                return kv.split("=", 1)[1]
    except Exception:
        return None
    return None


def _to_dt(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def check_projection_freshness(env):
    """Best-effort; ALWAYS returns healthy=True with warning messages."""
    table_name = _projection_table_name(env)
    if not table_name:
        return True, [
            "SKIPPED projection freshness: no table configured "
            "(set GOVERNANCE_PROJECTION_TABLE)"
        ]
    try:
        import boto3
    except ImportError:
        return True, [
            "SKIPPED projection freshness: boto3 not installed on this runner"
        ]
    try:
        table = boto3.resource("dynamodb").Table(table_name)
        resp = table.scan(Limit=200)
        items = resp.get("Items", [])
        latest = None
        for item in items:
            for attr in CANDIDATE_TS_ATTRS:
                if attr in item:
                    dt = _to_dt(item[attr])
                    if dt and (latest is None or dt > latest):
                        latest = dt
        if latest is None:
            return True, [
                f"SKIPPED projection freshness: no timestamp attr on {len(items)} sampled items"
            ]
        age_hours = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
        if age_hours > 24:
            return True, [
                f"Projection may be stale: latest updated_at {age_hours:.1f}h ago "
                "(threshold 24h)"
            ]
        return True, []
    except Exception as exc:
        return True, [f"SKIPPED projection freshness: {type(exc).__name__}: {exc}"]


def main():
    parser = argparse.ArgumentParser(description="Post-deploy pre-checks")
    parser.add_argument("--env", required=True, choices=["test", "prod"])
    parser.add_argument("--plane", choices=["frontend", "sam", "auto"], default="auto")
    args = parser.parse_args()
    plane = resolve_plane(args.plane)

    hard_errors = []
    warnings = []

    print()
    print(f"=== Post-deploy pre-check - env={args.env} plane={plane} ===")
    print()

    print("1. Required environment variables...")
    ok, errs = check_env_vars(plane)
    if ok:
        print("   OK")
    else:
        for e in errs:
            print(f"   ERROR: {e}")
        hard_errors.extend(errs)
        if plane == "frontend":
            print(
                "   (VITE_* are frontend build vars: only meaningful on the frontend deploy)"
            )

    print()
    print("2. Cognito configuration...")
    ok, errs = check_cognito_config(plane)
    if plane != "frontend":
        print("   SKIPPED (sam plane has no VITE_COGNITO_* build vars)")
    elif ok:
        print("   OK")
    else:
        for e in errs:
            print(f"   ERROR: {e}")
        hard_errors.extend(errs)

    print()
    print("3. Projection freshness (warning-level)...")
    _ok, msgs = check_projection_freshness(args.env)
    if not msgs:
        print("   OK (fresh)")
    else:
        for m in msgs:
            print(f"   WARN: {m}")
        warnings.extend(msgs)

    print()
    print("=== Summary ===")
    if hard_errors:
        print(f"FAILED: {len(hard_errors)} error(s)")
        for e in hard_errors:
            print(f"  - {e}")
        return 1
    if warnings:
        print(f"PASSED WITH WARNINGS: {len(warnings)} warning(s)")
    else:
        print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
