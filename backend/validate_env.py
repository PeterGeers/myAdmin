#!/usr/bin/env python3
"""
Environment Variable Validation Script

This script validates that all required environment variables are set
before the application starts. It should be run at container startup.

Usage:
    python validate_env.py

Exit codes:
    0 - All required variables are set
    1 - One or more required variables are missing
"""

import os
import sys

# Required environment variables
REQUIRED_VARS = {
    # AWS Cognito
    'COGNITO_USER_POOL_ID': 'AWS Cognito User Pool ID',
    'COGNITO_CLIENT_ID': 'AWS Cognito Client ID',
    'COGNITO_CLIENT_SECRET': 'AWS Cognito Client Secret',
    'AWS_REGION': 'AWS Region',
    'AWS_ACCESS_KEY_ID': 'AWS Access Key ID (for boto3)',
    'AWS_SECRET_ACCESS_KEY': 'AWS Secret Access Key (for boto3)',
    
    # Database
    'DB_HOST': 'Database host',
    'DB_USER': 'Database user',
    'DB_PASSWORD': 'Database password',
    'DB_NAME': 'Database name',
    
    # Google Drive
    'FACTUREN_FOLDER_ID': 'Google Drive Facturen folder ID',
    
    # OpenRouter
    'OPENROUTER_API_KEY': 'OpenRouter API key',
}

# Optional but recommended variables
OPTIONAL_VARS = {
    'SNS_TOPIC_ARN': 'AWS SNS Topic ARN for notifications',
    'TEST_MODE': 'Test mode flag',
    'TEST_DB_NAME': 'Test database name',
}


def validate_environment():
    """Validate that all required environment variables are set"""
    # Skip validation in Docker - docker-compose handles env_file loading
    if os.getenv('DOCKER_ENV') == 'true':
        print("🐳 Running in Docker - skipping validation (docker-compose handles env_file)")
        return True
    
    missing_vars = []
    
    print("🔍 Validating environment variables...")
    print("=" * 60)
    
    # Check required variables
    for var, description in REQUIRED_VARS.items():
        value = os.getenv(var)
        if not value:
            missing_vars.append((var, description))
            print(f"❌ MISSING: {var} ({description})")
        else:
            # Mask sensitive values
            if 'SECRET' in var or 'PASSWORD' in var or 'KEY' in var:
                display_value = value[:4] + '...' + value[-4:] if len(value) > 8 else '***'
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
    
    print("=" * 60)
    
    # Check optional variables
    print("\n📋 Optional variables:")
    for var, description in OPTIONAL_VARS.items():
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value}")
        else:
            print(f"⚠️  {var}: Not set ({description})")
    
    print("=" * 60)
    
    # Report results
    if missing_vars:
        print(f"\n❌ VALIDATION FAILED: {len(missing_vars)} required variable(s) missing:")
        for var, description in missing_vars:
            print(f"   - {var}: {description}")
        print("\n💡 Add these variables to backend/.env file")
        return False
    else:
        print(f"\n✅ VALIDATION PASSED: All {len(REQUIRED_VARS)} required variables are set")
        return True


if __name__ == '__main__':
    if validate_environment():
        sys.exit(0)
    else:
        sys.exit(1)
