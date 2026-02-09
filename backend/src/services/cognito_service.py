"""
Cognito Service

Centralized service for AWS Cognito operations.
Provides methods for user and group management with proper error handling.
"""

import os
import json
import boto3
from botocore.exceptions import ClientError
import logging
from typing import List, Dict, Optional, Tuple

# Initialize logger
logger = logging.getLogger(__name__)


class CognitoService:
    """Service class for AWS Cognito operations"""
    
    def __init__(self):
        """Initialize boto3 Cognito client"""
        self.region = os.getenv('AWS_REGION', 'eu-west-1')
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        
        if not self.user_pool_id:
            logger.warning("COGNITO_USER_POOL_ID not set in environment variables")
        
        self.client = boto3.client('cognito-idp', region_name=self.region)
    
    # ========================================================================
    # User Management Methods
    # ========================================================================
    
    def create_user(
        self, 
        email: str, 
        name: Optional[str] = None,
        tenant: Optional[str] = None,
        password: Optional[str] = None,
        suppress_email: bool = True
    ) -> Dict:
        """
        Create a new user in Cognito
        
        Args:
            email: User's email address (used as username)
            name: User's display name
            tenant: Tenant to assign user to
            password: Temporary password (required for new users)
            suppress_email: If True, don't send welcome email
        
        Returns:
            Dict with user information
        
        Raises:
            ClientError: If user creation fails
        """
        try:
            # Build user attributes
            user_attributes = [
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'}
            ]
            
            if name:
                user_attributes.append({'Name': 'name', 'Value': name})
            
            if tenant:
                user_attributes.append({
                    'Name': 'custom:tenants',
                    'Value': json.dumps([tenant])
                })
            
            # Create user
            response = self.client.admin_create_user(
                UserPoolId=self.user_pool_id,
                Username=email,
                UserAttributes=user_attributes,
                TemporaryPassword=password,
                MessageAction='SUPPRESS' if suppress_email else 'RESEND'
            )
            
            logger.info(f"User {email} created successfully")
            return response['User']
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Failed to create user {email}: {error_code} - {error_message}")
            raise
    
    def get_user(self, username: str) -> Optional[Dict]:
        """
        Get user details from Cognito
        
        Args:
            username: Username (email)
        
        Returns:
            Dict with user information or None if not found
        """
        try:
            response = self.client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            return response
        except ClientError as e:
            if e.response['Error']['Code'] == 'UserNotFoundException':
                return None
            logger.error(f"Failed to get user {username}: {e}")
            raise
    
    def list_users(self, tenant: Optional[str] = None, limit: int = 60) -> List[Dict]:
        """
        List users from Cognito, optionally filtered by tenant
        
        Args:
            tenant: Optional tenant filter
            limit: Maximum number of users to return per page
        
        Returns:
            List of user dictionaries
        """
        try:
            users = []
            pagination_token = None
            
            while True:
                params = {
                    'UserPoolId': self.user_pool_id,
                    'Limit': limit
                }
                
                if pagination_token:
                    params['PaginationToken'] = pagination_token
                
                response = self.client.list_users(**params)
                
                # Filter by tenant if specified
                if tenant:
                    for user in response.get('Users', []):
                        user_tenants = self._get_user_attribute(
                            user.get('Attributes', []), 
                            'custom:tenants'
                        )
                        if user_tenants and tenant in user_tenants:
                            users.append(user)
                else:
                    users.extend(response.get('Users', []))
                
                pagination_token = response.get('PaginationToken')
                if not pagination_token:
                    break
            
            return users
            
        except ClientError as e:
            logger.error(f"Failed to list users: {e}")
            raise
    
    def update_user(
        self, 
        username: str, 
        name: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> bool:
        """
        Update user attributes
        
        Args:
            username: Username (email)
            name: New display name
            enabled: Enable/disable user
        
        Returns:
            True if successful
        """
        try:
            # Update name if provided
            if name is not None:
                self.client.admin_update_user_attributes(
                    UserPoolId=self.user_pool_id,
                    Username=username,
                    UserAttributes=[{'Name': 'name', 'Value': name}]
                )
            
            # Update enabled status if provided
            if enabled is not None:
                if enabled:
                    self.client.admin_enable_user(
                        UserPoolId=self.user_pool_id,
                        Username=username
                    )
                else:
                    self.client.admin_disable_user(
                        UserPoolId=self.user_pool_id,
                        Username=username
                    )
            
            logger.info(f"User {username} updated successfully")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to update user {username}: {e}")
            raise
    
    def delete_user(self, username: str) -> bool:
        """
        Delete user from Cognito
        
        Args:
            username: Username (email)
        
        Returns:
            True if successful
        """
        try:
            self.client.admin_delete_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            logger.info(f"User {username} deleted successfully")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete user {username}: {e}")
            raise
    
    # ========================================================================
    # Group (Role) Management Methods
    # ========================================================================
    
    def assign_role(self, username: str, role: str) -> bool:
        """
        Assign role (group) to user
        
        Args:
            username: Username (email)
            role: Role name (Cognito group name)
        
        Returns:
            True if successful
        """
        try:
            self.client.admin_add_user_to_group(
                UserPoolId=self.user_pool_id,
                Username=username,
                GroupName=role
            )
            logger.info(f"Role {role} assigned to user {username}")
            return True
        except ClientError as e:
            logger.error(f"Failed to assign role {role} to user {username}: {e}")
            raise
    
    def remove_role(self, username: str, role: str) -> bool:
        """
        Remove role (group) from user
        
        Args:
            username: Username (email)
            role: Role name (Cognito group name)
        
        Returns:
            True if successful
        """
        try:
            self.client.admin_remove_user_from_group(
                UserPoolId=self.user_pool_id,
                Username=username,
                GroupName=role
            )
            logger.info(f"Role {role} removed from user {username}")
            return True
        except ClientError as e:
            logger.error(f"Failed to remove role {role} from user {username}: {e}")
            raise
    
    def list_user_groups(self, username: str) -> List[str]:
        """
        Get list of groups (roles) for a user
        
        Args:
            username: Username (email)
        
        Returns:
            List of group names
        """
        try:
            response = self.client.admin_list_groups_for_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            return [group['GroupName'] for group in response.get('Groups', [])]
        except ClientError as e:
            logger.error(f"Failed to list groups for user {username}: {e}")
            raise
    
    def list_groups(self, limit: int = 60) -> List[Dict]:
        """
        List all Cognito groups (roles)
        
        Args:
            limit: Maximum number of groups to return per page
        
        Returns:
            List of group dictionaries
        """
        try:
            groups = []
            next_token = None
            
            while True:
                params = {
                    'UserPoolId': self.user_pool_id,
                    'Limit': limit
                }
                
                if next_token:
                    params['NextToken'] = next_token
                
                response = self.client.list_groups(**params)
                groups.extend(response.get('Groups', []))
                
                next_token = response.get('NextToken')
                if not next_token:
                    break
            
            return groups
            
        except ClientError as e:
            logger.error(f"Failed to list groups: {e}")
            raise
    
    def create_group(self, name: str, description: str = '') -> Dict:
        """
        Create a new Cognito group (role)
        
        Args:
            name: Group name
            description: Group description
        
        Returns:
            Dict with group information
        """
        try:
            response = self.client.create_group(
                UserPoolId=self.user_pool_id,
                GroupName=name,
                Description=description
            )
            logger.info(f"Group {name} created successfully")
            return response['Group']
        except ClientError as e:
            logger.error(f"Failed to create group {name}: {e}")
            raise
    
    def update_group(
        self, 
        name: str, 
        description: Optional[str] = None,
        precedence: Optional[int] = None
    ) -> Dict:
        """
        Update Cognito group (role)
        
        Args:
            name: Group name
            description: New description
            precedence: New precedence value
        
        Returns:
            Dict with updated group information
        """
        try:
            params = {
                'UserPoolId': self.user_pool_id,
                'GroupName': name
            }
            
            if description is not None:
                params['Description'] = description
            
            if precedence is not None:
                params['Precedence'] = precedence
            
            response = self.client.update_group(**params)
            logger.info(f"Group {name} updated successfully")
            return response['Group']
        except ClientError as e:
            logger.error(f"Failed to update group {name}: {e}")
            raise
    
    def delete_group(self, name: str) -> bool:
        """
        Delete Cognito group (role)
        
        Args:
            name: Group name
        
        Returns:
            True if successful
        """
        try:
            self.client.delete_group(
                UserPoolId=self.user_pool_id,
                GroupName=name
            )
            logger.info(f"Group {name} deleted successfully")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete group {name}: {e}")
            raise
    
    def get_group_user_count(self, group_name: str) -> int:
        """
        Get number of users in a group
        
        Args:
            group_name: Group name
        
        Returns:
            Number of users in the group
        """
        try:
            response = self.client.list_users_in_group(
                UserPoolId=self.user_pool_id,
                GroupName=group_name,
                Limit=60
            )
            return len(response.get('Users', []))
        except ClientError as e:
            logger.error(f"Failed to get user count for group {group_name}: {e}")
            return 0
    
    # ========================================================================
    # Tenant Management Methods
    # ========================================================================
    
    def add_tenant_to_user(self, username: str, tenant: str) -> bool:
        """
        Add tenant to user's custom:tenants attribute
        
        Args:
            username: Username (email)
            tenant: Tenant identifier
        
        Returns:
            True if successful
        """
        try:
            # Get current user
            user = self.get_user(username)
            if not user:
                raise ValueError(f"User {username} not found")
            
            # Get current tenants
            current_tenants = self._get_user_attribute(
                user.get('UserAttributes', []),
                'custom:tenants'
            )
            
            # Add new tenant if not already present
            if tenant not in current_tenants:
                current_tenants.append(tenant)
                
                self.client.admin_update_user_attributes(
                    UserPoolId=self.user_pool_id,
                    Username=username,
                    UserAttributes=[{
                        'Name': 'custom:tenants',
                        'Value': json.dumps(current_tenants)
                    }]
                )
                logger.info(f"Tenant {tenant} added to user {username}")
            
            return True
            
        except ClientError as e:
            logger.error(f"Failed to add tenant {tenant} to user {username}: {e}")
            raise
    
    def remove_tenant_from_user(self, username: str, tenant: str) -> Tuple[bool, bool]:
        """
        Remove tenant from user's custom:tenants attribute
        
        Args:
            username: Username (email)
            tenant: Tenant identifier
        
        Returns:
            Tuple of (success, user_deleted)
            - success: True if operation succeeded
            - user_deleted: True if user was deleted (had only one tenant)
        """
        try:
            # Get current user
            user = self.get_user(username)
            if not user:
                raise ValueError(f"User {username} not found")
            
            # Get current tenants
            current_tenants = self._get_user_attribute(
                user.get('UserAttributes', []),
                'custom:tenants'
            )
            
            # Remove tenant
            if tenant in current_tenants:
                current_tenants.remove(tenant)
                
                # If user has no more tenants, delete user
                if not current_tenants:
                    self.delete_user(username)
                    logger.info(f"User {username} deleted (no remaining tenants)")
                    return True, True
                
                # Otherwise, update tenants list
                self.client.admin_update_user_attributes(
                    UserPoolId=self.user_pool_id,
                    Username=username,
                    UserAttributes=[{
                        'Name': 'custom:tenants',
                        'Value': json.dumps(current_tenants)
                    }]
                )
                logger.info(f"Tenant {tenant} removed from user {username}")
            
            return True, False
            
        except ClientError as e:
            logger.error(f"Failed to remove tenant {tenant} from user {username}: {e}")
            raise
    
    def get_user_tenants(self, username: str) -> List[str]:
        """
        Get list of tenants for a user
        
        Args:
            username: Username (email)
        
        Returns:
            List of tenant identifiers
        """
        try:
            user = self.get_user(username)
            if not user:
                return []
            
            return self._get_user_attribute(
                user.get('UserAttributes', []),
                'custom:tenants'
            )
        except ClientError as e:
            logger.error(f"Failed to get tenants for user {username}: {e}")
            return []
    
    # ========================================================================
    # Notification Methods
    # ========================================================================
    
    def send_invitation(
        self, 
        email: str, 
        temporary_password: str,
        tenant: str
    ) -> bool:
        """
        Send invitation email via SNS
        
        Args:
            email: User's email address
            temporary_password: Temporary password
            tenant: Tenant name
        
        Returns:
            True if successful
        
        Note: This requires SNS_TOPIC_ARN to be configured
        """
        try:
            sns_topic_arn = os.getenv('SNS_TOPIC_ARN')
            if not sns_topic_arn:
                logger.warning("SNS_TOPIC_ARN not configured, skipping invitation email")
                return False
            
            sns_client = boto3.client('sns', region_name=self.region)
            
            message = f"""
Welcome to myAdmin!

You have been invited to join the {tenant} tenant.

Your login credentials:
Email: {email}
Temporary Password: {temporary_password}

Please log in and change your password at your earliest convenience.

Login URL: {os.getenv('FRONTEND_URL', 'http://localhost:3000')}
"""
            
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Subject=f'myAdmin Invitation - {tenant}',
                Message=message
            )
            
            logger.info(f"Invitation email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send invitation to {email}: {e}")
            return False
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _get_user_attribute(
        self, 
        user_attributes: List[Dict], 
        attribute_name: str
    ) -> any:
        """
        Extract attribute value from Cognito user attributes
        
        Args:
            user_attributes: List of user attribute dictionaries
            attribute_name: Name of attribute to extract
        
        Returns:
            Attribute value (parsed JSON for custom:tenants)
        """
        for attr in user_attributes:
            if attr['Name'] == attribute_name:
                value = attr['Value']
                
                # Handle JSON arrays (custom:tenants)
                if attribute_name == 'custom:tenants':
                    try:
                        return json.loads(value) if value else []
                    except json.JSONDecodeError:
                        return [value] if value else []
                
                return value
        
        # Return appropriate default
        if attribute_name == 'custom:tenants':
            return []
        return None
