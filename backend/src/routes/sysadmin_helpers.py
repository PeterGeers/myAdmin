"""
SysAdmin Helper Functions

Shared utility functions for SysAdmin routes.

Bugfix ``cognito-admin-pool-resolution`` (R1/R2): these helper admin ops previously
targeted the legacy single-pool ``COGNITO_USER_POOL_ID`` var (which points at the PROD
pool in every environment) via a module-level ``USER_POOL_ID``. They now resolve their
target pool through the shared registry-backed resolver in **token mode**
(:func:`auth.admin_pool_resolver.resolve_pool_id_for_token`), keyed to the caller
token's verified ``iss``. Every caller of these helpers is a SysAdmin route gated by
``@cognito_required`` (see ``routes/sysadmin_tenants.py``), so the caller token is
reliably present on the Flask ``request`` and token mode applies. Only the value passed
as ``UserPoolId=...`` changes; every request/response contract is preserved, including
the ``[]`` / ``0`` swallow-all-on-failure behavior (a :class:`PoolResolutionError` is
mapped into the same failure contract rather than raised out).
"""

import json
import logging
import os
from typing import Any

import boto3
from flask import request

from auth.admin_pool_resolver import PoolResolutionError, resolve_pool_id_for_token

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize Cognito client
cognito_client = boto3.client(
    "cognito-idp", region_name=os.getenv("AWS_REGION", "eu-west-1")
)


def _caller_token() -> str:
    """Return the raw caller JWT from the request ``Authorization`` header.

    Every route that invokes these helpers is gated by ``@cognito_required``, which has
    already validated the ``Bearer`` token before the handler runs; this re-reads that
    same header and strips the ``Bearer `` prefix to hand the raw token to the shared
    resolver's token mode. Mirrors ``routes.tenant_admin_users._caller_token``.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :].strip()
    return auth_header.strip()


def _resolve_pool_id() -> str:
    """Resolve the target Cognito pool id for the current admin request (token mode).

    Resolves through the shared registry-backed resolver keyed to the caller token's
    verified ``iss`` (2.3), replacing the legacy ``COGNITO_USER_POOL_ID`` read. Raises
    :class:`PoolResolutionError` when the pool cannot be resolved; each helper maps that
    into its existing swallow-all failure contract (``[]`` / ``0``).
    """
    return resolve_pool_id_for_token(_caller_token())


def get_user_attribute(user: dict[str, Any], attribute_name: str) -> Any:
    """Extract attribute value from Cognito user object"""
    for attr in user.get("Attributes", []):
        if attr["Name"] == attribute_name:
            value = attr["Value"]
            # Handle JSON arrays
            if attribute_name == "custom:tenants":
                try:
                    # Handle escaped quotes in Cognito response
                    if "\\" in value:
                        value = value.replace("\\", "")
                    return json.loads(value)
                except Exception:
                    return [value] if value else []
            return value
    return None


def get_user_groups(username: str) -> list[str]:
    """Get Cognito groups for a user"""
    try:
        pool_id = _resolve_pool_id()
        response = cognito_client.admin_list_groups_for_user(
            UserPoolId=pool_id, Username=username
        )
        return [group["GroupName"] for group in response.get("Groups", [])]
    except PoolResolutionError as e:
        # Target pool could not be resolved; preserve the swallow-all contract.
        logger.error(f"Error getting user groups: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting user groups: {e}")
        return []


def get_tenant_user_count(administration: str) -> int:
    """Get count of users with access to a tenant"""
    try:
        pool_id = _resolve_pool_id()
        # List all users
        response = cognito_client.list_users(
            UserPoolId=pool_id,
            Limit=60,  # Maximum allowed
        )

        count = 0
        for user in response.get("Users", []):
            tenants = get_user_attribute(user, "custom:tenants")
            if tenants and administration in tenants:
                count += 1

        # Handle pagination if needed
        while "PaginationToken" in response:
            response = cognito_client.list_users(
                UserPoolId=pool_id,
                Limit=60,
                PaginationToken=response["PaginationToken"],
            )
            for user in response.get("Users", []):
                tenants = get_user_attribute(user, "custom:tenants")
                if tenants and administration in tenants:
                    count += 1

        return count
    except PoolResolutionError as e:
        # Target pool could not be resolved; preserve the swallow-all contract.
        logger.error(f"Error getting tenant user count: {e}")
        return 0
    except Exception as e:
        logger.error(f"Error getting tenant user count: {e}")
        return 0


def get_tenant_users(administration: str) -> list[dict[str, Any]]:
    """Get all users with access to a tenant"""
    try:
        pool_id = _resolve_pool_id()
        # List all users
        response = cognito_client.list_users(UserPoolId=pool_id, Limit=60)

        users = []
        for user in response.get("Users", []):
            tenants = get_user_attribute(user, "custom:tenants")
            if tenants and administration in tenants:
                email = get_user_attribute(user, "email")
                groups = get_user_groups(user["Username"])
                users.append({"email": email, "groups": groups})

        # Handle pagination if needed
        while "PaginationToken" in response:
            response = cognito_client.list_users(
                UserPoolId=pool_id,
                Limit=60,
                PaginationToken=response["PaginationToken"],
            )
            for user in response.get("Users", []):
                tenants = get_user_attribute(user, "custom:tenants")
                if tenants and administration in tenants:
                    email = get_user_attribute(user, "email")
                    groups = get_user_groups(user["Username"])
                    users.append({"email": email, "groups": groups})

        return users
    except PoolResolutionError as e:
        # Target pool could not be resolved; preserve the swallow-all contract.
        logger.error(f"Error getting tenant users: {e}")
        return []
    except Exception as e:
        logger.error(f"Error getting tenant users: {e}")
        return []


def validate_administration_name(administration: str) -> tuple[bool, str | None]:
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

    if not all(c.isalnum() or c in "-_" for c in administration):
        return (
            False,
            "Administration name can only contain letters, numbers, hyphens, and underscores",
        )

    if " " in administration:
        return False, "Administration name cannot contain spaces"

    return True, None
