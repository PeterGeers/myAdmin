"""
Storage Resolver: Shared helper functions for provider-aware storage routing.

Resolves the configured storage provider for a tenant and provides convenience
functions for S3 operations (folder listing, folder creation). Used by route
handlers and services that need to dispatch storage operations to the correct
backend (GoogleDriveService or S3SharedStorage).

Reference: .kiro/specs/provider-aware-folder-routes/design.md
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def resolve_storage_provider(tenant: str, parameter_service=None) -> str:
    """Resolve the storage provider for a tenant.

    Returns 'google_drive' or 's3_shared' based on the tenant's
    configured `storage.invoice_provider` parameter.

    Args:
        tenant: The tenant/administration identifier.
        parameter_service: Optional ParameterService instance. If None,
            a new one is instantiated from DatabaseManager.

    Returns:
        'google_drive' or 's3_shared'. Defaults to 'google_drive' when
        the parameter is unset, None, or on error.
    """
    try:
        if parameter_service is None:
            from database import DatabaseManager
            db = DatabaseManager()
            from services.parameter_service import ParameterService
            parameter_service = ParameterService(db)

        provider = parameter_service.get_param(
            'storage', 'invoice_provider', tenant=tenant
        )

        if provider == 'google_drive':
            return 'google_drive'

        return 's3_shared'

    except Exception as e:
        logger.warning(
            "Failed to resolve storage provider for tenant '%s': %s. "
            "Defaulting to 's3_shared'.",
            tenant, e
        )
        return 's3_shared'


def get_s3_storage(tenant: str, parameter_service=None):
    """Return an initialized S3SharedStorage instance for the given tenant.

    Args:
        tenant: The tenant/administration identifier.
        parameter_service: Optional ParameterService instance. If None,
            a new one is instantiated from DatabaseManager.

    Returns:
        An S3SharedStorage instance configured for the tenant.
    """
    if parameter_service is None:
        from database import DatabaseManager
        db = DatabaseManager()
        from services.parameter_service import ParameterService
        parameter_service = ParameterService(db)

    import sys
    import os
    src_storage = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage')
    logger.info("Storage package path: %s, exists: %s, sys.path[0:3]: %s", 
                src_storage, os.path.exists(src_storage), sys.path[:3])
    if os.path.exists(src_storage) and os.path.dirname(src_storage) not in sys.path:
        sys.path.insert(0, os.path.dirname(src_storage))
    from storage.s3_shared_storage import S3SharedStorage
    return S3SharedStorage(tenant, parameter_service)


def list_s3_folders(tenant: str, parameter_service=None, category: str = 'invoices') -> List[str]:
    """List folder names under {tenant}/{category}/ in S3.

    Uses list_objects_v2 with Delimiter='/' to extract unique reference
    (folder) names from CommonPrefixes. Also checks for .folder marker
    objects in Contents to include empty folders that have no other files.

    Args:
        tenant: The tenant/administration identifier.
        parameter_service: Optional ParameterService instance.
        category: Storage category prefix (default: 'invoices').

    Returns:
        Sorted list of folder name strings. Returns empty list on error.
    """
    try:
        storage = get_s3_storage(tenant, parameter_service)
        prefix = f"{tenant}/{category}/"
        folder_names: set = set()

        # Paginate through all results
        continuation_token = None
        while True:
            kwargs = {
                'Bucket': storage.bucket,
                'Prefix': prefix,
                'Delimiter': '/',
            }
            if continuation_token:
                kwargs['ContinuationToken'] = continuation_token

            response = storage._client.list_objects_v2(**kwargs)

            # Extract folder names from CommonPrefixes
            for cp in response.get('CommonPrefixes', []):
                # cp['Prefix'] looks like '{tenant}/invoices/Supplier1/'
                folder_path = cp['Prefix']
                # Strip the base prefix and trailing slash to get folder name
                folder_name = folder_path[len(prefix):].rstrip('/')
                if folder_name:
                    folder_names.add(folder_name)

            # Check Contents for .folder marker objects
            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.endswith('/.folder'):
                    # Key looks like '{tenant}/invoices/FolderName/.folder'
                    # Extract the folder name between prefix and /.folder
                    relative = key[len(prefix):]
                    parts = relative.split('/')
                    if len(parts) == 2 and parts[1] == '.folder':
                        folder_name = parts[0]
                        if folder_name:
                            folder_names.add(folder_name)

            # Handle pagination
            if response.get('IsTruncated'):
                continuation_token = response.get('NextContinuationToken')
            else:
                break

        return sorted(folder_names)

    except Exception as e:
        logger.warning(
            "Failed to list S3 folders for tenant '%s', category '%s': %s",
            tenant, category, e
        )
        return []


def create_s3_folder(tenant: str, folder_name: str, parameter_service=None) -> dict:
    """Create a folder marker in S3 for the given tenant and folder name.

    Persists a zero-byte object at {tenant}/invoices/{folder_name}/.folder
    so the folder appears in listings before any files are uploaded.

    Args:
        tenant: The tenant/administration identifier.
        folder_name: The folder (reference) name to create.
        parameter_service: Optional ParameterService instance.

    Returns:
        Success dict matching Google Drive create_folder response shape:
        {'id': s3_key, 'name': folder_name, 'url': s3_key}
        On error, returns {'success': False, 'error': str}.
    """
    try:
        storage = get_s3_storage(tenant, parameter_service)
        key = f"{tenant}/invoices/{folder_name}/.folder"

        storage._client.put_object(
            Bucket=storage.bucket,
            Key=key,
            Body=b'',
            ContentType='application/x-directory',
        )

        logger.info(
            "Created S3 folder marker: s3://%s/%s", storage.bucket, key
        )
        return {'id': key, 'name': folder_name, 'url': key}

    except Exception as e:
        logger.warning(
            "Failed to create S3 folder '%s' for tenant '%s': %s",
            folder_name, tenant, e
        )
        return {'success': False, 'error': str(e)}
