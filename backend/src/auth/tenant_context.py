"""
Multi-Tenant Context Management for myAdmin

This module provides tenant context extraction, validation, and filtering
for multi-tenant database operations.

Based on the architecture at .kiro/specs/Common/Multitennant/architecture.md
"""

import json
import base64
from typing import Optional, List, Dict, Any, Tuple
from flask import request, jsonify
import functools


def get_user_tenants(jwt_token: str) -> List[str]:
    """
    Extract custom:tenants from JWT token
    
    Args:
        jwt_token: JWT token string
        
    Returns:
        list: List of tenant names user has access to
    """
    try:
        # Split JWT token into parts
        parts = jwt_token.split('.')
        if len(parts) != 3:
            return []
        
        # Decode payload (second part of JWT)
        payload_encoded = parts[1]
        
        # Add padding if necessary
        padding = 4 - (len(payload_encoded) % 4)
        if padding != 4:
            payload_encoded += '=' * padding
        
        # Decode base64
        payload_decoded = base64.urlsafe_b64decode(payload_encoded)
        payload = json.loads(payload_decoded)
        
        # Extract custom:tenants attribute
        tenants = payload.get('custom:tenants', [])
        
        # Handle both string (JSON array) and list formats
        if isinstance(tenants, str):
            try:
                tenants = json.loads(tenants)
            except:
                tenants = [tenants] if tenants else []
        elif not isinstance(tenants, list):
            tenants = [tenants] if tenants else []
        
        return tenants
        
    except Exception as e:
        print(f"Error extracting tenants from JWT: {e}", flush=True)
        return []


def get_current_tenant(request_obj) -> Optional[str]:
    """
    Get tenant from request header or JWT token
    
    Priority:
    1. X-Tenant header (user selected)
    2. First tenant from JWT custom:tenants
    
    Args:
        request_obj: Flask request object
        
    Returns:
        str: Tenant name or None
    """
    # Option 1: From X-Tenant header (user selected)
    tenant = request_obj.headers.get('X-Tenant')
    
    if tenant:
        return tenant
    
    # Option 2: From JWT token - get first tenant
    auth_header = request_obj.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        jwt_token = auth_header.replace('Bearer ', '').strip()
        tenants = get_user_tenants(jwt_token)
        if tenants:
            return tenants[0]
    
    return None


def is_tenant_admin(user_roles: List[str], tenant: str, user_tenants: List[str]) -> bool:
    """
    Check if user is admin for specific tenant
    
    Args:
        user_roles: List of user's Cognito groups
        tenant: Tenant name to check
        user_tenants: List of tenants user has access to
        
    Returns:
        bool: True if user is Tenant_Admin for this tenant
    """
    has_admin_role = 'Tenant_Admin' in user_roles
    has_tenant_access = tenant in user_tenants
    return has_admin_role and has_tenant_access


def validate_tenant_access(user_tenants: List[str], requested_tenant: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Validate user has access to requested tenant
    
    Args:
        user_tenants: List of tenants user has access to
        requested_tenant: Tenant being requested
        
    Returns:
        tuple: (is_authorized, error_response)
    """
    if not requested_tenant:
        return False, {
            'error': 'No tenant specified',
            'details': 'X-Tenant header or JWT custom:tenants required'
        }
    
    if requested_tenant not in user_tenants:
        return False, {
            'error': 'Access denied to tenant',
            'details': f'User does not have access to tenant: {requested_tenant}'
        }
    
    return True, None


def tenant_required(allow_sysadmin: bool = False):
    """
    Decorator to enforce tenant context on routes
    
    This decorator:
    1. Extracts tenant from X-Tenant header or JWT
    2. Validates user has access to the tenant
    3. Injects tenant and user_tenants into route function
    
    Args:
        allow_sysadmin: If True, SysAdmin can bypass tenant validation (for system operations)
        
    Usage:
        @app.route('/api/invoices', methods=['GET'])
        @cognito_required(required_permissions=['invoices_read'])
        @tenant_required()
        def get_invoices(user_email, user_roles, tenant, user_tenants):
            # tenant is validated and injected
            query = "SELECT * FROM mutaties WHERE administration = %s"
            results = db.execute_query(query, [tenant])
            return jsonify(results)
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Get user_roles from kwargs (injected by cognito_required)
            user_roles = kwargs.get('user_roles', [])
            
            # Extract tenant from request
            tenant = get_current_tenant(request)
            
            # Extract user tenants from JWT
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                jwt_token = auth_header.replace('Bearer ', '').strip()
                user_tenants = get_user_tenants(jwt_token)
            else:
                user_tenants = []
            
            # SysAdmin bypass (if allowed)
            if allow_sysadmin and 'SysAdmin' in user_roles:
                print(f"⚠️ SysAdmin bypass for {f.__name__}", flush=True)
                kwargs['tenant'] = tenant
                kwargs['user_tenants'] = user_tenants
                return f(*args, **kwargs)
            
            # Validate tenant access
            is_authorized, error_response = validate_tenant_access(user_tenants, tenant)
            
            if not is_authorized:
                print(f"❌ Tenant access denied for {f.__name__}: {error_response}", flush=True)
                return jsonify(error_response), 403
            
            print(f"✅ Tenant access granted for {f.__name__}: {tenant}", flush=True)
            
            # Inject tenant context into route function
            kwargs['tenant'] = tenant
            kwargs['user_tenants'] = user_tenants
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def add_tenant_filter(query: str, params: List[Any], tenant: str, table_alias: Optional[str] = None) -> Tuple[str, List[Any]]:
    """
    Add tenant filter to SQL query
    
    Args:
        query: SQL query string
        params: Query parameters list
        tenant: Tenant name to filter by
        table_alias: Optional table alias (e.g., 'm' for 'mutaties m')
        
    Returns:
        tuple: (modified_query, modified_params)
        
    Example:
        query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
        params = ['2024-01-01']
        query, params = add_tenant_filter(query, params, 'GoodwinSolutions')
        # Result: "SELECT * FROM mutaties WHERE TransactionDate > %s AND administration = %s"
        # params: ['2024-01-01', 'GoodwinSolutions']
    """
    # Determine the column reference
    column = f"{table_alias}.administration" if table_alias else "administration"
    
    # Check if query already has WHERE clause
    if 'WHERE' in query.upper():
        # Add AND condition
        query = f"{query} AND {column} = %s"
    else:
        # Add WHERE clause
        query = f"{query} WHERE {column} = %s"
    
    # Add tenant to params
    params = list(params) + [tenant]
    
    return query, params


def get_tenant_config(db, tenant: str, config_key: str, is_secret: bool = False) -> Optional[str]:
    """
    Get tenant configuration value
    
    Args:
        db: DatabaseManager instance
        tenant: Tenant name
        config_key: Configuration key
        is_secret: Whether to decrypt secret values
        
    Returns:
        str: Configuration value or None
    """
    try:
        query = """
            SELECT config_value, is_secret 
            FROM tenant_config 
            WHERE administration = %s AND config_key = %s
        """
        result = db.execute_query(query, [tenant, config_key], fetch=True)
        
        if result and len(result) > 0:
            config_value = result[0].get('config_value')
            is_secret_flag = result[0].get('is_secret', False)
            
            # TODO: Implement decryption for secrets
            if is_secret_flag and is_secret:
                # Decrypt value (placeholder for now)
                return config_value
            
            return config_value
        
        return None
        
    except Exception as e:
        print(f"Error getting tenant config: {e}", flush=True)
        return None


def set_tenant_config(db, tenant: str, config_key: str, config_value: str, 
                     is_secret: bool = False, created_by: str = None) -> bool:
    """
    Set tenant configuration value
    
    Args:
        db: DatabaseManager instance
        tenant: Tenant name
        config_key: Configuration key
        config_value: Configuration value
        is_secret: Whether to encrypt the value
        created_by: User email who created/updated the config
        
    Returns:
        bool: True if successful
    """
    try:
        # TODO: Implement encryption for secrets
        if is_secret:
            # Encrypt value (placeholder for now)
            pass
        
        query = """
            INSERT INTO tenant_config (administration, config_key, config_value, is_secret, created_by)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                config_value = VALUES(config_value),
                updated_at = CURRENT_TIMESTAMP
        """
        
        db.execute_query(query, [tenant, config_key, config_value, is_secret, created_by])
        return True
        
    except Exception as e:
        print(f"Error setting tenant config: {e}", flush=True)
        return False
