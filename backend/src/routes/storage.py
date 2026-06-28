"""
Storage Routes - S3 Pre-signed URL and File Operations

This module provides API endpoints for S3 storage operations including
pre-signed URL generation for secure document downloads and logo uploads.

Endpoints:
- GET /api/storage/presigned-url - Generate pre-signed URL for S3 object download
- POST /api/storage/upload-logo - Upload company logo to S3

Requirements: 7.1–7.7, 9.1–9.3
"""

import os
import logging

import boto3
from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.parameter_service import ParameterService

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
storage_bp = Blueprint('storage', __name__, url_prefix='/api/storage')


@storage_bp.route('/presigned-url', methods=['GET'])
@cognito_required(required_permissions=[])
@tenant_required()
def get_presigned_url(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Generate a pre-signed URL for downloading an S3 object.

    Query Parameters:
        key (str): The S3 object key to generate a URL for.

    Security:
        - Requires authentication via Cognito JWT
        - Validates key starts with tenant prefix to prevent cross-tenant access

    Returns:
        200: {'success': True, 'url': '<presigned-url>', 'expires_in': 300}
        403: {'error': 'Access denied'} if cross-tenant key
        503: {'error': 'S3 storage not configured'} if S3_SHARED_BUCKET unset
        500: {'success': False, 'error': '<message>'} on unexpected error
    """
    try:
        key = request.args.get('key', '')

        # Tenant isolation: key must start with tenant prefix
        if not key.startswith(f"{tenant}/"):
            return jsonify({'error': 'Access denied'}), 403

        bucket = os.getenv('S3_SHARED_BUCKET', '')
        if not bucket:
            return jsonify({'error': 'S3 storage not configured'}), 503

        s3_client = boto3.client('s3')
        
        # Determine content type from file extension for inline display
        import mimetypes
        content_type = mimetypes.guess_type(key)[0] or 'application/octet-stream'
        
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket,
                'Key': key,
                'ResponseContentDisposition': 'inline',
                'ResponseContentType': content_type,
            },
            ExpiresIn=300
        )

        return jsonify({'success': True, 'url': url, 'expires_in': 300})

    except Exception as e:
        logger.error(f"Error generating pre-signed URL: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Allowed MIME types and max file size for logo upload
ALLOWED_LOGO_TYPES = {'image/png', 'image/jpeg', 'image/svg+xml'}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB

# Map MIME types to file extensions
MIME_TO_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/svg+xml': 'svg',
}


@storage_bp.route('/upload-logo', methods=['POST'])
@cognito_required(required_permissions=[])
@tenant_required()
def upload_logo(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Upload a company logo to S3.

    Accepts multipart file upload (PNG, JPG, SVG, max 2MB).
    Stores at fixed key {tenant}/branding/company_logo.{ext}.
    Updates company_logo_s3_key parameter via ParameterService.

    Returns:
        200: {'success': True, 'key': '<s3_key>'}
        400: {'success': False, 'error': '<message>'} on validation error
        503: {'error': 'S3 storage not configured'} if S3_SHARED_BUCKET unset
        500: {'success': False, 'error': '<message>'} on unexpected error
    """
    try:
        # Validate file is present in request
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        # Validate MIME type
        content_type = file.content_type or ''
        if content_type not in ALLOWED_LOGO_TYPES:
            return jsonify({
                'success': False,
                'error': f'Invalid file type. Allowed: PNG, JPG, SVG'
            }), 400

        # Validate file size (read content to check)
        file_data = file.read()
        if len(file_data) > MAX_LOGO_SIZE:
            return jsonify({
                'success': False,
                'error': 'File too large. Maximum size is 2MB'
            }), 400

        # Check S3 bucket is configured
        bucket = os.getenv('S3_SHARED_BUCKET', '')
        if not bucket:
            return jsonify({'error': 'S3 storage not configured'}), 503

        # Determine file extension from MIME type
        ext = MIME_TO_EXT.get(content_type, 'png')

        # Build S3 key: {tenant}/branding/company_logo.{ext}
        s3_key = f"{tenant}/branding/company_logo.{ext}"

        # Upload to S3
        s3_client = boto3.client('s3')
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=file_data,
            ContentType=content_type,
        )

        # Update company_logo_s3_key parameter via ParameterService
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        ps = ParameterService(db)
        ps.set_param(
            'tenant', tenant, 'branding', 'company_logo_s3_key',
            s3_key, value_type='string', created_by=user_email
        )

        return jsonify({'success': True, 'key': s3_key})

    except Exception as e:
        logger.error(f"Error uploading logo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
