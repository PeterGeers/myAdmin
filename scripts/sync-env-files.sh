#!/bin/bash
# Sync Environment Files
# Checks consistency across .env files (root, backend, frontend)

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Environment Files Sync Utility                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Get repository root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi

ROOT_ENV="$REPO_ROOT/.env"
BACKEND_ENV="$REPO_ROOT/backend/.env"
FRONTEND_ENV="$REPO_ROOT/frontend/.env"

# Function to check file status
show_file_status() {
    local path="$1"
    local name="$2"
    
    if [ -f "$path" ]; then
        local lines=$(wc -l < "$path")
        echo "  ✓ $name ($lines lines)"
        return 0
    else
        echo "  ✗ $name (missing)"
        return 1
    fi
}

echo "Environment Files Status:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

show_file_status "$ROOT_ENV" ".env (root)"
root_exists=$?
show_file_status "$BACKEND_ENV" "backend/.env"
backend_exists=$?
show_file_status "$FRONTEND_ENV" "frontend/.env"
frontend_exists=$?

echo ""

if [ $root_exists -ne 0 ] || [ $backend_exists -ne 0 ] || [ $frontend_exists -ne 0 ]; then
    echo "⚠ Some .env files are missing"
    echo "  Please create them manually or restore from .env.example files"
    exit 1
fi

# Function to get env value from file
get_env_value() {
    local file="$1"
    local key="$2"
    grep "^${key}=" "$file" 2>/dev/null | head -1 | sed "s/^${key}=//" | tr -d '"' | tr -d "'"
}

# Show differences
echo "Key Differences:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check DB_HOST
root_db_host=$(get_env_value "$ROOT_ENV" "DB_HOST")
backend_db_host=$(get_env_value "$BACKEND_ENV" "DB_HOST")
frontend_db_host=$(get_env_value "$FRONTEND_ENV" "DB_HOST")

echo "  DB_HOST:"
if [ "$root_db_host" = "mysql" ]; then
    echo "    Root:     $root_db_host ✓ (Docker)"
else
    echo "    Root:     $root_db_host ⚠ (Expected: mysql)"
fi

if [ "$backend_db_host" = "localhost" ]; then
    echo "    Backend:  $backend_db_host ✓ (Local)"
else
    echo "    Backend:  $backend_db_host ⚠ (Expected: localhost)"
fi

if [ -n "$frontend_db_host" ]; then
    if [ "$frontend_db_host" = "localhost" ]; then
        echo "    Frontend: $frontend_db_host ✓ (Local)"
    else
        echo "    Frontend: $frontend_db_host ⚠ (Expected: localhost)"
    fi
else
    echo "    Frontend: (not set) ✓ (not needed)"
fi

echo ""

# Check SNS (backend only)
backend_sns=$(get_env_value "$BACKEND_ENV" "SNS_TOPIC_ARN")
frontend_sns=$(get_env_value "$FRONTEND_ENV" "SNS_TOPIC_ARN")

echo "  SNS_TOPIC_ARN:"
if [ -n "$backend_sns" ]; then
    echo "    Backend:  Present ✓"
else
    echo "    Backend:  Missing ✗"
fi

if [ -n "$frontend_sns" ]; then
    echo "    Frontend: Present ⚠ (not needed)"
else
    echo "    Frontend: Not present ✓"
fi

echo ""

# Check secret consistency
echo "Checking Secret Consistency:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

secret_keys=(
    "COGNITO_USER_POOL_ID"
    "COGNITO_CLIENT_ID"
    "COGNITO_CLIENT_SECRET"
    "AWS_REGION"
    "DB_USER"
    "DB_PASSWORD"
)

all_consistent=true

for key in "${secret_keys[@]}"; do
    root_val=$(get_env_value "$ROOT_ENV" "$key")
    backend_val=$(get_env_value "$BACKEND_ENV" "$key")
    
    # Only compare root and backend (frontend may not have all backend vars)
    if [ -z "$root_val" ] && [ -z "$backend_val" ]; then
        echo "  - $key (not set in either)"
    elif [ "$root_val" = "$backend_val" ]; then
        echo "  ✓ $key (consistent)"
    else
        echo "  ✗ $key (INCONSISTENT between root and backend!)"
        all_consistent=false
    fi
done

echo ""

if [ "$all_consistent" = true ]; then
    echo "✓ All checked secrets are consistent!"
else
    echo "⚠ Some secrets are inconsistent!"
    echo "  Please update them manually to match"
fi

echo ""

# Summary
echo "Summary:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  • .env (root):   Docker Compose (DB_HOST=mysql)"
echo "  • backend/.env:  Python/Flask (DB_HOST=localhost + SNS)"
echo "  • frontend/.env: React (Cognito + API URL)"
echo ""
echo "Recommendations:"
echo "  1. Update secrets in all .env files when changed"
echo "  2. Use this script to verify consistency"
echo "  3. For Railway: env vars are set separately in Railway dashboard"
echo ""

exit 0
