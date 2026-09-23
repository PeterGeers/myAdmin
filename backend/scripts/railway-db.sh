#!/usr/bin/env bash
# ============================================================================
# Run a command OR raw SQL against Railway MySQL (public TCP proxy) from WSL.
# ============================================================================
# The backend reads DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME (see
# backend/src/database.py -> DatabaseManager). Locally those point at Docker
# MySQL. This wrapper sets them to the Railway proxy values for ONE command
# only (they are exported into the child process, not your shell), so local
# dev config in .env is never disturbed.
#
# The Railway connection facts (host/port/user/password) are NOT hardcoded
# here: they are read from RAILWAY_DB_* keys in the repo-root .env (gitignored).
#
# This replaces the retired PowerShell scripts:
#   railway-run.ps1  -> `railway-db.sh <command>`   (run a Python script)
#   railway-sql.ps1  -> `railway-db.sh -q/-f ...`    (run raw SQL)
# (WSL has no `mysql` CLI, so SQL mode uses the venv's mysql.connector.)
#
# Usage (run from repo root, venv active):
#   # Run a Python script / command against Railway:
#   PYTHONPATH=backend/src backend/scripts/railway-db.sh python backend/scripts/verify_schema.py
#
#   # Run a raw SQL query:
#   backend/scripts/railway-db.sh -q "SELECT COUNT(*) FROM mutaties"
#
#   # Run a .sql file:
#   backend/scripts/railway-db.sh -f backend/sql/migration.sql
#
# Optional overrides via env:
#   RAILWAY_DB_HOST, RAILWAY_DB_PORT, RAILWAY_DB_USER, RAILWAY_DB_NAME
#   TEST_MODE=true            # target testfinance instead of finance
# ============================================================================
set -euo pipefail

# Resolve repo root from this script's location (scripts live in backend/scripts).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

usage() {
  cat >&2 <<'EOF'
Usage:
  railway-db.sh <command> [args...]     Run a command (e.g. python script.py)
  railway-db.sh -q "<SQL>"              Run a raw SQL query
  railway-db.sh -f <file.sql>           Run a .sql file
Examples:
  PYTHONPATH=backend/src railway-db.sh python backend/scripts/verify_schema.py
  railway-db.sh -q "SELECT COUNT(*) FROM mutaties"
  railway-db.sh -f backend/sql/migration.sql
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found." >&2
  exit 1
fi

# Load .env (RAILWAY_DB_* etc.) without echoing values.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${RAILWAY_DB_PASSWORD:-}" ]]; then
  echo "ERROR: RAILWAY_DB_PASSWORD is not set in $ENV_FILE." >&2
  exit 1
fi

# Railway public TCP proxy connection. All values come from .env RAILWAY_DB_*
# keys; the literals below are only last-resort fallbacks.
export DB_HOST="${RAILWAY_DB_HOST:-shinkansen.proxy.rlwy.net}"
export DB_PORT="${RAILWAY_DB_PORT:-42375}"
export DB_USER="${RAILWAY_DB_USER:-root}"
# Data lives in the `finance` schema (Railway's default `railway` DB is empty).
# TEST_MODE=true overrides to testfinance below and inside DatabaseManager.
if [[ "${TEST_MODE:-false}" == "true" ]]; then
  export DB_NAME="${RAILWAY_DB_NAME:-testfinance}"
else
  export DB_NAME="${RAILWAY_DB_NAME:-finance}"
fi
export DB_PASSWORD="$RAILWAY_DB_PASSWORD"

echo "-> Railway MySQL: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}" >&2

# ---- SQL mode (-q query / -f file) ----------------------------------------
run_sql() {
  # $1 = 'query' | 'file', $2 = SQL text or file path
  local mode="$1" arg="$2"
  if [[ "$mode" == "file" && ! -f "$arg" ]]; then
    echo "ERROR: SQL file not found: $arg" >&2
    exit 1
  fi
  RAILWAY_SQL_MODE="$mode" RAILWAY_SQL_ARG="$arg" python3 - <<'PY'
import os, sys, mysql.connector

mode = os.environ["RAILWAY_SQL_MODE"]
arg = os.environ["RAILWAY_SQL_ARG"]
raw = open(arg, encoding="utf-8").read() if mode == "file" else arg

# Split into individual statements; ignore blanks and full-line comments.
statements = []
for chunk in raw.split(";"):
    s = "\n".join(
        ln for ln in chunk.splitlines()
        if ln.strip() and not ln.strip().startswith(("--", "#"))
    ).strip()
    if s:
        statements.append(s)

conn = mysql.connector.connect(
    host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
    user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
)
try:
    cur = conn.cursor()
    total_changes = 0
    for stmt in statements:
        cur.execute(stmt)
        if cur.with_rows:
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
            print("\t".join(cols))
            for r in rows:
                print("\t".join("NULL" if v is None else str(v) for v in r))
            print(f"({len(rows)} row{'s' if len(rows) != 1 else ''})", file=sys.stderr)
        else:
            total_changes += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    if total_changes:
        conn.commit()
        print(f"OK, {total_changes} row(s) affected (committed).", file=sys.stderr)
finally:
    try:
        cur.close(); conn.close()
    except Exception:
        pass
PY
}

case "${1:-}" in
  -q)
    [[ $# -ge 2 ]] || { echo "ERROR: -q needs a SQL string" >&2; usage; exit 2; }
    run_sql query "$2"
    ;;
  -f)
    [[ $# -ge 2 ]] || { echo "ERROR: -f needs a file path" >&2; usage; exit 2; }
    run_sql file "$2"
    ;;
  -h|--help)
    usage
    ;;
  *)
    # Command mode: run whatever was passed (python script, etc.)
    exec "$@"
    ;;
esac
