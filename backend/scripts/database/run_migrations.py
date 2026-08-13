#!/usr/bin/env python3
"""
Run database migrations on dev, production, or both.

Usage:
    python scripts/database/run_migrations.py              # dev only (default)
    python scripts/database/run_migrations.py --prod       # prod only
    python scripts/database/run_migrations.py --both       # dev + prod
    python scripts/database/run_migrations.py --status     # show status (no apply)
    python scripts/database/run_migrations.py --prod --status

Environment:
    Dev:  reads from backend/.env (DB_HOST=localhost)
    Prod: reads RAILWAY_DB_HOST, RAILWAY_DB_PORT, RAILWAY_DB_USER, RAILWAY_DB_NAME from env.
          Requires RAILWAY_DB_PASSWORD env var or prompts interactively.
          See .kiro/steering/commands.md for connection details.
"""

import argparse
import getpass
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


def set_dev_env():
    """Load dev environment from backend/.env"""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def set_prod_env():
    """Set environment for Railway production database.

    Reads connection details from environment variables:
      RAILWAY_DB_HOST, RAILWAY_DB_PORT, RAILWAY_DB_USER, RAILWAY_DB_PASSWORD, RAILWAY_DB_NAME

    If RAILWAY_DB_PASSWORD is not set, prompts interactively.
    Defaults match the Railway proxy documented in .kiro/steering/commands.md.
    """
    password = os.environ.get("RAILWAY_DB_PASSWORD")
    if not password:
        password = getpass.getpass("Railway DB password: ")

    os.environ["DB_HOST"] = os.environ.get("RAILWAY_DB_HOST", "")
    os.environ["DB_PORT"] = os.environ.get("RAILWAY_DB_PORT", "3306")
    os.environ["DB_USER"] = os.environ.get("RAILWAY_DB_USER", "root")
    os.environ["DB_PASSWORD"] = password
    os.environ["DB_NAME"] = os.environ.get("RAILWAY_DB_NAME", "finance")


def run_migrations(target: str, status_only: bool = False):
    """Run or show migrations for a target environment"""
    # Import fresh each time (env vars already set)
    # Force reimport of database module with new env
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("database", "database_migrations", "scalability_manager"):
            del sys.modules[mod_name]

    from database_migrations import DatabaseMigration

    migrator = DatabaseMigration(test_mode=False)

    status = migrator.get_migration_status()
    print(f"\n{'='*60}")
    print(f"  Target: {target.upper()}")
    print(f"  Host:   {os.environ.get('DB_HOST')}:{os.environ.get('DB_PORT', '3306')}")
    print(f"  DB:     {os.environ.get('DB_NAME')}")
    print(f"{'='*60}")
    print(f"  Total:   {status['total_migrations']}")
    print(f"  Applied: {status['applied_migrations']}")
    print(f"  Pending: {status['pending_migrations']}")

    if status["pending_migrations"] > 0:
        print(f"\n  Pending migrations:")
        for m in status["migrations"]:
            if not m["applied"]:
                print(f"    - {m['name']}: {m['description']}")

    if status_only:
        print(f"\n  (status only — no changes applied)")
        return

    if status["pending_migrations"] == 0:
        print(f"\n  ✅ All migrations already applied")
        return

    print(f"\n  Applying migrations...")
    applied = migrator.run_all_migrations()
    print(f"  ✅ Applied {applied} migration(s)")


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--prod", action="store_true", help="Run on production (Railway)"
    )
    parser.add_argument(
        "--both", action="store_true", help="Run on both dev and production"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show status only, don't apply"
    )
    args = parser.parse_args()

    run_dev = not args.prod or args.both
    run_prod = args.prod or args.both

    if run_dev:
        set_dev_env()
        run_migrations("dev", status_only=args.status)

    if run_prod:
        set_prod_env()
        run_migrations("prod", status_only=args.status)

    print()


if __name__ == "__main__":
    main()
