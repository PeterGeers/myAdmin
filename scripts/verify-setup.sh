#!/bin/bash
# Setup Verification Script
# Checks that all required configuration is in place before starting the application

echo "🔍 Verifying myAdmin Setup..."
echo "============================================================"

errors=()
warnings=()

# Check if backend/.env exists
if [ -f "backend/.env" ]; then
    echo "✅ backend/.env exists"
    
    # Check for required variables in backend/.env
    required_vars=(
        "COGNITO_USER_POOL_ID"
        "COGNITO_CLIENT_ID"
        "COGNITO_CLIENT_SECRET"
        "AWS_REGION"
        "AWS_ACCESS_KEY_ID"
        "AWS_SECRET_ACCESS_KEY"
        "DB_HOST"
        "DB_USER"
        "DB_PASSWORD"
        "DB_NAME"
        "FACTUREN_FOLDER_ID"
        "OPENROUTER_API_KEY"
    )
    
    for var in "${required_vars[@]}"; do
        if grep -qE "^${var}=.+" "backend/.env"; then
            echo "  ✅ $var is set"
        else
            echo "  ❌ $var is MISSING"
            errors+=("$var is missing from backend/.env")
        fi
    done
else
    echo "❌ backend/.env NOT FOUND"
    errors+=("backend/.env file does not exist. Copy from backend/.env.example")
fi

echo ""

# Check if frontend/.env exists
if [ -f "frontend/.env" ]; then
    echo "✅ frontend/.env exists"
else
    echo "⚠️  frontend/.env NOT FOUND"
    warnings+=("frontend/.env file does not exist. Copy from frontend/.env.example")
fi

echo ""

# Check if Docker is running
if docker ps > /dev/null 2>&1; then
    echo "✅ Docker is running"
else
    echo "❌ Docker is NOT running"
    errors+=("Docker is not running. Start Docker.")
fi

# Check if containers are running
backend_running=$(docker ps --filter "name=myadmin-backend-1" --format "{{.Names}}" 2>/dev/null)
mysql_running=$(docker ps --filter "name=myadmin-mysql-1" --format "{{.Names}}" 2>/dev/null)

if [ -n "$backend_running" ]; then
    echo "✅ Backend container is running"
else
    echo "⚠️  Backend container is NOT running"
    warnings+=("Backend container is not running. Run: docker-compose up -d")
fi

if [ -n "$mysql_running" ]; then
    echo "✅ MySQL container is running"
else
    echo "⚠️  MySQL container is NOT running"
    warnings+=("MySQL container is not running. Run: docker-compose up -d")
fi

echo ""

# Check Python availability
if command -v python3 &> /dev/null || command -v python &> /dev/null; then
    python_version=$(python3 --version 2>/dev/null || python --version 2>/dev/null)
    echo "✅ Python available: $python_version"
else
    echo "❌ Python NOT found"
    errors+=("Python is not installed or not in PATH")
fi

# Check Node.js availability
if command -v node &> /dev/null; then
    node_version=$(node --version)
    echo "✅ Node.js available: $node_version"
else
    echo "❌ Node.js NOT found"
    errors+=("Node.js is not installed or not in PATH")
fi

echo ""
echo "============================================================"

# Summary
if [ ${#errors[@]} -eq 0 ] && [ ${#warnings[@]} -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED - System is ready!"
    exit 0
else
    if [ ${#errors[@]} -gt 0 ]; then
        echo "❌ ERRORS FOUND (${#errors[@]}):"
        for error in "${errors[@]}"; do
            echo "   - $error"
        done
    fi
    
    if [ ${#warnings[@]} -gt 0 ]; then
        echo "⚠️  WARNINGS (${#warnings[@]}):"
        for warning in "${warnings[@]}"; do
            echo "   - $warning"
        done
    fi
    
    echo ""
    echo "💡 Fix the errors above before starting the application"
    exit 1
fi
