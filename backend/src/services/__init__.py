"""
Services package for myAdmin application.
Contains business logic services for credentials, templates, and other features.
"""

# Note: Import services directly from their modules instead of from this __init__.py
# Example: from services.credential_service import CredentialService
# This avoids circular import issues and import context problems

__all__ = ['credential_service', 'template_service', 'ai_template_assistant']
