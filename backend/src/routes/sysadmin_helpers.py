"""
SysAdmin Helper Functions

Shared utility functions for SysAdmin routes
"""

import os
import json
import boto3
import logging
from typing import Dict, Any, List, Optional

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize Cognito client
cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')


def get_user_attribute(user: Dict[str, Any], attribute_name: str) -> Any:
    """Extract attribute value from Cognito user object"""
    for attr in user.get('Attributes', []):
        if attr['Name'] == attribute_name:
            value = attr['Value']
            # Handle JSON arrays
            if attribute_name == 'custom:tenants':
                try:
                    # Handle escaped quotes in Cognito response
                    if '\\' in value:
                        value = value.replace('\\', '')
                    return json.loads(value)
                except:
                    return [value] if value else []
            return value
    return None


def get_user_groups(username: str) -> List[str]:
    """Get Cognito groups for a user"""
    try:
        response = cognito_client.admin_list_groups_for_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        return [group['GroupName'] for group in response.get('Groups', [])]
    except Exception as e:
        logger.error(f"Error getting user groups: {e}")
        return []


def get_tenant_user_count(administration: str) -> int:
    """Get count of users with access to a tenant"""
    try:
        # List all users
        response = cognito_client.list_users(
            UserPoolId=USER_POOL_ID,
            Limit=60  # Maximum allowed
        )
        
        count = 0
        for user in response.get('Users', []):
            tenants = get_user_attribute(user, 'custom:tenants')
            if tenants and administration in tenants:
                count += 1
        
        # Handle pagination if needed
        while 'PaginationToken' in response:
            response = cognito_client.list_users(
                UserPoolId=USER_POOL_ID,
                Limit=60,
                PaginationToken=response['PaginationToken']
            )
            for user in response.get('Users', []):
                tenants = get_user_attribute(user, 'custom:tenants')
                if tenants and administration in tenants:
                    count += 1
        
        return count
    except Exception as e:
        logger.error(f"Error getting tenant user count: {e}")
        return 0


def get_tenant_users(administration: str) -> List[Dict[str, Any]]:
    """Get all users with access to a tenant"""
    try:
        # List all users
        response = cognito_client.list_users(
            UserPoolId=USER_POOL_ID,
            Limit=60
        )
        
        users = []
        for user in response.get('Users', []):
            tenants = get_user_attribute(user, 'custom:tenants')
            if tenants and administration in tenants:
                email = get_user_attribute(user, 'email')
                groups = get_user_groups(user['Username'])
                users.append({
                    'email': email,
                    'groups': groups
                })
        
        # Handle pagination if needed
        while 'PaginationToken' in response:
            response = cognito_client.list_users(
                UserPoolId=USER_POOL_ID,
                Limit=60,
                PaginationToken=response['PaginationToken']
            )
            for user in response.get('Users', []):
                tenants = get_user_attribute(user, 'custom:tenants')
                if tenants and administration in tenants:
                    email = get_user_attribute(user, 'email')
                    groups = get_user_groups(user['Username'])
                    users.append({
                        'email': email,
                        'groups': groups
                    })
        
        return users
    except Exception as e:
        logger.error(f"Error getting tenant users: {e}")
        return []


def validate_administration_name(administration: str) -> tuple[bool, Optional[str]]:
    """
    Validate administration name format
    
    Rules:
    - 3-50 characters
    - Alphanumeric, hyphens, underscores only
    - No spaces
    - Must start with letter
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not administration:
        return False, "Administration name is required"
    
    if len(administration) < 3:
        return False, "Administration name must be at least 3 characters"
    
    if len(administration) > 50:
        return False, "Administration name must be at most 50 characters"
    
    if not administration[0].isalpha():
        return False, "Administration name must start with a letter"
    
    if not all(c.isalnum() or c in '-_' for c in administration):
        return False, "Administration name can only contain letters, numbers, hyphens, and underscores"
    
    if ' ' in administration:
        return False, "Administration name cannot contain spaces"
    
    return True, None
