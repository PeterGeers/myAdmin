"""
User Routes - User-specific endpoints

This module provides API endpoints for user-specific operations,
including language preference management.
"""
from flask import Blueprint, jsonify, request
from src.auth.cognito_utils import cognito_required
from src.services.user_language_service import (
    get_user_language,
    update_user_language,
    validate_language_code
)

# Create Blueprint
user_bp = Blueprint('user', __name__, url_prefix='/api/user')


@user_bp.route('/language', methods=['GET'])
@cognito_required()
def get_user_language_preference(user_email, user_roles):
    """
    Get user's preferred language from Cognito
    
    Returns:
        JSON response with language code
        
    Example response:
        {
            "language": "nl"
        }
    """
    try:
        language = get_user_language(user_email)
        
        return jsonify({
            'language': language
        }), 200
        
    except Exception as e:
        print(f"❌ Error in get_user_language_preference: {e}")
        return jsonify({
            'error': 'Failed to retrieve language preference',
            'details': str(e)
        }), 500


@user_bp.route('/language', methods=['PUT'])
@cognito_required()
def update_user_language_preference(user_email, user_roles):
    """
    Update user's preferred language in Cognito
    
    Request body:
        {
            "language": "nl" | "en"
        }
        
    Returns:
        JSON response with success message
        
    Example response:
        {
            "message": "Language preference updated successfully",
            "language": "en"
        }
    """
    try:
        # Get request data
        data = request.get_json()
        
        if not data or 'language' not in data:
            return jsonify({
                'error': 'Missing required field: language'
            }), 400
        
        language = data['language']
        
        # Validate language code
        if not validate_language_code(language):
            return jsonify({
                'error': 'Invalid language code',
                'details': 'Language must be "nl" or "en"'
            }), 400
        
        # Update language in Cognito
        success = update_user_language(user_email, language)
        
        if not success:
            return jsonify({
                'error': 'Failed to update language preference'
            }), 500
        
        return jsonify({
            'message': 'Language preference updated successfully',
            'language': language
        }), 200
        
    except Exception as e:
        print(f"❌ Error in update_user_language_preference: {e}")
        return jsonify({
            'error': 'Failed to update language preference',
            'details': str(e)
        }), 500
