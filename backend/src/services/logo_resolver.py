"""
Logo Resolver Service

Resolves a tenant's company logo as a base64 data URI based on the configured
storage provider. Supports Google Drive (legacy) and S3 shared/tenant buckets.

Used by both the STR invoice generator and the ZZP PDF generator to avoid
duplicating logo fetch logic across multiple modules.

Reference: .kiro/specs/s3-shared-bucket-infrastructure/design.md §Provider-Aware Logo Resolution
"""

import os
import base64
import logging
from typing import Optional

import requests
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def resolve_tenant_logo(
    tenant: str,
    branding_namespace: str,
    parameter_service,
    db=None
) -> Optional[str]:
    """
    Resolve company logo as base64 data URI based on storage provider.

    Checks the tenant's `storage.invoice_provider` parameter to determine
    where the logo is stored, then fetches and encodes it.

    Args:
        tenant: The tenant/administration name.
        branding_namespace: Parameter namespace for branding config
            (e.g. 'str_branding', 'zzp_branding').
        parameter_service: ParameterService instance for reading config.
        db: Optional database connection (unused, kept for interface compatibility).

    Returns:
        A base64 data URI string (e.g. 'data:image/png;base64,...') or None
        if no logo is configured or an error occurs.
    """
    try:
        provider = parameter_service.get_param(
            'storage', 'invoice_provider', tenant=tenant
        )
    except Exception as e:
        logger.warning("Could not read storage.invoice_provider for tenant %s: %s", tenant, e)
        provider = None

    if provider == 'google_drive' or provider is None:
        # Default/legacy behavior: fetch from Google Drive
        return _resolve_google_drive_logo(tenant, branding_namespace, parameter_service)

    elif provider in ('s3_shared', 's3_tenant'):
        return _resolve_s3_logo(tenant, branding_namespace, parameter_service)

    # Unknown provider — no logo
    logger.debug("Unknown invoice_provider '%s' for tenant %s, returning None", provider, tenant)
    return None


def _resolve_google_drive_logo(
    tenant: str,
    branding_namespace: str,
    parameter_service
) -> Optional[str]:
    """Fetch logo from Google Drive via lh3.googleusercontent.com."""
    logo_file_id = parameter_service.get_param(
        branding_namespace, 'company_logo_file_id', tenant=tenant
    )
    if not logo_file_id:
        return None

    logo_url = f'https://lh3.googleusercontent.com/d/{logo_file_id}=w600'
    try:
        resp = requests.get(logo_url, timeout=10)
        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', 'image/png')
            b64 = base64.b64encode(resp.content).decode('utf-8')
            return f'data:{content_type};base64,{b64}'
        else:
            logger.warning(
                "Google Drive logo fetch returned %s for tenant %s",
                resp.status_code, tenant
            )
            return None
    except Exception as e:
        logger.warning("Could not fetch Google Drive logo for tenant %s: %s", tenant, e)
        return None


def _resolve_s3_logo(
    tenant: str,
    branding_namespace: str,
    parameter_service
) -> Optional[str]:
    """Fetch logo from S3 bucket using company_logo_s3_key parameter."""
    s3_key = parameter_service.get_param(
        branding_namespace, 'company_logo_s3_key', tenant=tenant
    )
    if not s3_key:
        return None

    bucket = os.getenv('S3_SHARED_BUCKET', '')
    if not bucket:
        logger.warning("S3_SHARED_BUCKET not configured, cannot resolve S3 logo for tenant %s", tenant)
        return None

    try:
        s3_client = boto3.client('s3')
        obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
        content_type = obj['ContentType']
        b64 = base64.b64encode(obj['Body'].read()).decode('utf-8')
        return f'data:{content_type};base64,{b64}'
    except ClientError as e:
        logger.warning(
            "S3 ClientError fetching logo for tenant %s (key=%s): %s",
            tenant, s3_key, e
        )
        return None
    except Exception as e:
        logger.warning("Could not fetch S3 logo for tenant %s: %s", tenant, e)
        return None
