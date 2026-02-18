"""
User Language Service - Cognito Integration

This service manages user language preferences stored in AWS Cognito custom attributes.
The custom attribute 'custom:preferred_language' was added in Phase 2.1 of i18n implementation.
"""
import os
import boto3
from typing import Optional

# Initialize Cognito client
cognito_client = None

def get_cognito_client():
    """Get or create Cognito client"""
    global cognito_client
    if cognito_client is None:
        cognito_client = boto3.client(
            'cognito-idp',
            region_name=os.getenv('AWS_REGION', 'eu-west-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
    return cognito_client


def get_user_language(user_email: str) -> str:
    """
    Get user's preferred language from Cognito custom attribute
    
    Args:
        user_email: User's email address (Cognito username)
        
    Returns:
        str: Language code ('nl' or 'en'), defaults to 'nl' if not set
    """
    try:
        client = get_cognito_client()
        user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        
        if not user_pool_id:
            print("❌ COGNITO_USER_POOL_ID not set in environment")
            return 'nl'
        
        # Get user attributes from Cognito
        response = client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=user_email
        )
        
        # Extract custom:preferred_language attribute
        for attr in response.get('UserAttributes', []):
            if attr['Name'] == 'custom:preferred_language':
                language = attr['Value']
                print(f"✅ Retrieved language preference for {user_email}: {language}")
                return language
        
        # Default to Dutch if not set
        print(f"ℹ️ No language preference set for {user_email}, defaulting to 'nl'")
        return 'nl'
        
    except client.exceptions.UserNotFoundException:
        print(f"❌ User not found in Cognito: {user_email}")
        return 'nl'
    except Exception as e:
        print(f"❌ Error getting user language from Cognito: {e}")
        return 'nl'


def update_user_language(user_email: str, language: str) -> bool:
    """
    Update user's preferred language in Cognito custom attribute
    
    Args:
        user_email: User's email address (Cognito username)
        language: Language code ('nl' or 'en')
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Validate language code
    if language not in ['nl', 'en']:
        print(f"❌ Invalid language code: {language}. Must be 'nl' or 'en'")
        return False
    
    try:
        client = get_cognito_client()
        user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        
        if not user_pool_id:
            print("❌ COGNITO_USER_POOL_ID not set in environment")
            return False
        
        # Update user attribute in Cognito
        client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=user_email,
            UserAttributes=[
                {
                    'Name': 'custom:preferred_language',
                    'Value': language
                }
            ]
        )
        
        print(f"✅ Updated language preference for {user_email}: {language}")
        return True
        
    except client.exceptions.UserNotFoundException:
        print(f"❌ User not found in Cognito: {user_email}")
        return False
    except Exception as e:
        print(f"❌ Error updating user language in Cognito: {e}")
        return False


def validate_language_code(language: str) -> bool:
    """
    Validate language code
    
    Args:
        language: Language code to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    return language in ['nl', 'en']
