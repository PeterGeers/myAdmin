"""
Tenant Admin User Management Routes

This module provides API endpoints for Tenant_Admin role to manage users within their tenant(s).
Tenant admins can only manage users who have access to their assigned tenants.

Endpoints:
- GET /api/tenant-admin/users - List users in current tenant
- POST /api/tenant-admin/users - Create user and assign to tenant
- PUT /api/tenant-admin/users/<username> - Update user (name, status)
- DELETE /api/tenant-admin/users/<username> - Delete user
- POST /api/tenant-admin/users/<username>/groups - Assign role to user
- DELETE /api/tenant-admin/users/<username>/groups/<group> - Remove role from user
- GET /api/tenant-admin/roles - List available roles for tenant
"""

import json

from botocore.exceptions import ClientError
from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.admin_pool_resolver import PoolResolutionError
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_membership_required
from database import DatabaseManager
from routes._tenant_admin_users_notifications import (
    send_new_user_invitation,
    send_tenant_added_notification,
)
from routes._tenant_admin_users_shared import (
    cognito_client,
    cognito_service,
    get_available_roles_for_tenant,
    get_user_attribute,
)
from routes.error_responses import error_response
from routes.sysadmin_helpers import _resolve_pool_id
from services.email_template_service import EmailTemplateService
from services.invitation_service import InvitationService

# Create blueprint
tenant_admin_users_bp = Blueprint(
    "tenant_admin_users", __name__, url_prefix="/api/tenant-admin"
)

# Cognito clients and the user/role lookup helpers live in
# ``routes._tenant_admin_users_shared`` (task 15 split) and are imported above.
# Re-exporting them keeps ``routes.tenant_admin_roles`` and the existing patch
# points (``routes.tenant_admin_users.cognito_client``, ``.cognito_service``,
# ``.get_available_roles_for_tenant``, ``.get_user_attribute``) working unchanged.


# ============================================================================
# User Management Endpoints
# ============================================================================


@tenant_admin_users_bp.route("/users", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_membership_required()
def list_tenant_users(user_email, user_roles, tenant) -> ResponseReturnValue:
    """
    List all users who have access to the current tenant

    Returns users with their roles, status, and tenant assignments
    """
    try:
        # Get current tenant from request header

        # Resolve the target Cognito pool from the caller token (token mode)
        try:
            user_pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return error_response(
                e,
                "Failed to resolve admin pool",
                status=500,
                log_context="tenant_admin_users _resolve_pool_id",
            )

        # Get all users from Cognito (paginated)
        all_cognito_users = []
        pagination_token = None
        while True:
            kwargs = {
                "UserPoolId": user_pool_id,
                "Limit": 60,
            }
            if pagination_token:
                kwargs["PaginationToken"] = pagination_token
            response = cognito_client.list_users(**kwargs)
            all_cognito_users.extend(response.get("Users", []))
            pagination_token = response.get("PaginationToken")
            if not pagination_token:
                break

        tenant_users = []

        for user in all_cognito_users:
            # Get user's tenants
            user_tenant_list = get_user_attribute(
                user.get("Attributes", []), "custom:tenants"
            )

            # Only include users who have access to this tenant
            if user_tenant_list and tenant in user_tenant_list:
                username = user.get("Username")

                # Get user's roles from DB (per-tenant)
                user_email_addr = get_user_attribute(
                    user.get("Attributes", []), "email"
                )
                try:
                    db = DatabaseManager()
                    role_rows = db.execute_query(
                        "SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s",
                        (user_email_addr, tenant),
                        fetch=True,
                    )
                    user_groups = [r["role"] for r in (role_rows or [])]
                except Exception:
                    user_groups = []

                tenant_users.append(
                    {
                        "username": username,
                        "email": get_user_attribute(
                            user.get("Attributes", []), "email"
                        ),
                        "name": get_user_attribute(user.get("Attributes", []), "name"),
                        "status": user.get("UserStatus"),
                        "enabled": user.get("Enabled"),
                        "groups": user_groups,
                        "tenants": [tenant],
                        "created": user.get("UserCreateDate").isoformat()
                        if user.get("UserCreateDate")
                        else None,
                        "modified": user.get("UserLastModifiedDate").isoformat()
                        if user.get("UserLastModifiedDate")
                        else None,
                    }
                )

        return jsonify(
            {
                "success": True,
                "tenant": tenant,
                "users": tenant_users,
                "count": len(tenant_users),
            }
        )

    except ClientError as e:
        return error_response(
            e,
            "Tenant user request failed",
            status=500,
            log_context="tenant_admin_users ClientError",
        )


@tenant_admin_users_bp.route("/users", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_membership_required()
def create_tenant_user(user_email, user_roles, tenant) -> ResponseReturnValue:
    """
    Create a new user and assign to current tenant

    If user already exists, adds the current tenant to their tenant list.

    Request body:
    {
        "email": "user@example.com",
        "name": "User Name",
        "password": "TempPassword123!",  # Only required for new users
        "groups": ["Finance_Read"]
    }
    """
    try:
        # Get current tenant from request header

        # Resolve the target Cognito pool from the caller token (token mode)
        try:
            user_pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return error_response(
                e,
                "Failed to resolve admin pool",
                status=500,
                log_context="tenant_admin_users _resolve_pool_id",
            )

        # Get request data
        data = request.get_json()
        email = data.get("email")
        name = data.get("name")
        _password = data.get("password")
        groups = data.get("groups", [])

        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        # Normalize email to lowercase for Cognito case-sensitivity
        email = email.strip().lower()

        # Validate groups are allowed for this tenant
        available_roles = get_available_roles_for_tenant(tenant)
        invalid_groups = [
            g for g in groups if g not in available_roles and g != "SysAdmin"
        ]

        if invalid_groups:
            return jsonify(
                {
                    "success": False,
                    "error": f"Invalid groups for this tenant: {', '.join(invalid_groups)}",
                    "available_roles": available_roles,
                }
            ), 400

        # Check if user already exists
        user_exists = False
        existing_user_tenants = []
        username = email

        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=user_pool_id, Username=email
            )
            user_exists = True
            existing_user_tenants = get_user_attribute(
                user_response.get("UserAttributes", []), "custom:tenants"
            )

            # Check if user already has this tenant
            if existing_user_tenants and tenant in existing_user_tenants:
                return jsonify(
                    {
                        "success": False,
                        "error": f"User {email} already has access to tenant {tenant}",
                        "message": "This user already exists in this tenant. Use the Edit button to modify their roles.",
                    }
                ), 409

        except ClientError as e:
            if e.response["Error"]["Code"] != "UserNotFoundException":
                raise

        if user_exists:
            # User exists but doesn't have this tenant - add tenant to their list
            updated_tenants = (
                existing_user_tenants + [tenant] if existing_user_tenants else [tenant]
            )

            cognito_client.admin_update_user_attributes(
                UserPoolId=user_pool_id,
                Username=username,
                UserAttributes=[
                    {"Name": "custom:tenants", "Value": json.dumps(updated_tenants)}
                ],
            )

            # Add user roles to DB
            db = DatabaseManager()
            for group_name in groups:
                try:
                    db.execute_query(
                        """INSERT INTO user_tenant_roles (email, administration, role, created_by)
                           VALUES (%s, %s, %s, %s)""",
                        (email, tenant, group_name, user_email),
                        fetch=False,
                        commit=True,
                    )
                except Exception as e:
                    print(
                        f"Warning: Failed to add role {group_name} for user in tenant: {e}",
                        flush=True,
                    )

            from auth.role_cache import invalidate_cache

            invalidate_cache(email, tenant)

            print(
                f"AUDIT: Existing user {email} added to tenant {tenant} by {user_email}",
                flush=True,
            )

            # Send notification email (no password — user already has credentials)
            send_tenant_added_notification(
                tenant=tenant,
                email=email,
                user_email=user_email,
                user_response=user_response,
            )

            return jsonify(
                {
                    "success": True,
                    "message": f"User {email} added to tenant {tenant}",
                    "username": username,
                    "tenant": tenant,
                    "existing_user": True,
                }
            )

        else:
            # User doesn't exist - create new user

            # Initialize invitation service
            invitation_service = InvitationService()
            email_service = EmailTemplateService(administration=tenant)

            # Create invitation record and generate temporary password
            invitation_result = invitation_service.create_invitation(
                administration=tenant,
                email=email,
                created_by=user_email,
                template_type="user_invitation",
            )

            if not invitation_result.get("success"):
                return jsonify(
                    {
                        "success": False,
                        "error": "Failed to create invitation",
                        "details": invitation_result.get("error"),
                    }
                ), 500

            # Use generated temporary password
            temp_password = invitation_result["temporary_password"]

            # Build user attributes
            user_attributes = [
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:tenants", "Value": json.dumps([tenant])},
            ]

            if name:
                user_attributes.append({"Name": "name", "Value": name})

            # Create user
            try:
                response = cognito_client.admin_create_user(
                    UserPoolId=user_pool_id,
                    Username=email,
                    UserAttributes=user_attributes,
                    TemporaryPassword=temp_password,
                    MessageAction="SUPPRESS",
                )

                username = response["User"]["Username"]

                # Update invitation with username
                invitation_service.create_invitation(
                    administration=tenant,
                    email=email,
                    username=username,
                    created_by=user_email,
                    template_type="user_invitation",
                )

            except ClientError as e:
                # Mark invitation as failed
                invitation_service.mark_invitation_failed(
                    administration=tenant, email=email, error_message=str(e)
                )
                raise

            # Add user roles to DB
            db_new = DatabaseManager()
            for group_name in groups:
                try:
                    db_new.execute_query(
                        """INSERT INTO user_tenant_roles (email, administration, role, created_by)
                           VALUES (%s, %s, %s, %s)""",
                        (email, tenant, group_name, user_email),
                        fetch=False,
                        commit=True,
                    )
                except Exception as e:
                    print(
                        f"Warning: Failed to add role {group_name} for new user: {e}",
                        flush=True,
                    )

            from auth.role_cache import invalidate_cache as invalidate_new

            invalidate_new(email, tenant)

            # Send invitation email
            send_new_user_invitation(
                tenant=tenant,
                email=email,
                user_email=user_email,
                temp_password=temp_password,
                email_service=email_service,
                invitation_service=invitation_service,
            )

            print(
                f"AUDIT: User {email} created by {user_email} for tenant {tenant}",
                flush=True,
            )

            return jsonify(
                {
                    "success": True,
                    "message": f"User {email} created successfully. Invitation email sent.",
                    "username": username,
                    "tenant": tenant,
                    "existing_user": False,
                    "invitation_sent": True,
                }
            )

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        if error_code == "InvalidPasswordException":
            return jsonify(
                {
                    "success": False,
                    "error": "Password does not meet requirements (minimum 8 characters)",
                }
            ), 400
        else:
            return jsonify({"success": False, "error": error_message}), 500


@tenant_admin_users_bp.route("/users/<username>", methods=["PUT"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_membership_required()
def update_tenant_user(username, user_email, user_roles, tenant) -> ResponseReturnValue:
    """
    Update user attributes (name, status)

    Request body:
    {
        "name": "Updated Name",
        "enabled": true
    }
    """
    try:
        # Get current tenant from request header

        # Resolve the target Cognito pool from the caller token (token mode)
        try:
            user_pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return error_response(
                e,
                "Failed to resolve admin pool",
                status=500,
                log_context="tenant_admin_users _resolve_pool_id",
            )

        # Get target user and verify they belong to this tenant
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=user_pool_id, Username=username
            )
            target_user_tenants = get_user_attribute(
                user_response.get("UserAttributes", []), "custom:tenants"
            )
        except ClientError:
            return jsonify({"error": f"User not found: {username}"}), 404

        if not target_user_tenants or tenant not in target_user_tenants:
            return jsonify(
                {
                    "error": "User not in this tenant",
                    "message": f"User {username} does not have access to tenant {tenant}",
                }
            ), 403

        # Get request data
        data = request.get_json()
        name = data.get("name")
        enabled = data.get("enabled")

        # Update name if provided
        if name is not None:
            user_attributes = [{"Name": "name", "Value": name}]
            cognito_client.admin_update_user_attributes(
                UserPoolId=user_pool_id,
                Username=username,
                UserAttributes=user_attributes,
            )

        # Update enabled status if provided
        if enabled is not None:
            if enabled:
                cognito_client.admin_enable_user(
                    UserPoolId=user_pool_id, Username=username
                )
            else:
                cognito_client.admin_disable_user(
                    UserPoolId=user_pool_id, Username=username
                )

        print(
            f"AUDIT: User {username} updated by {user_email} in tenant {tenant}",
            flush=True,
        )

        return jsonify(
            {"success": True, "message": f"User {username} updated successfully"}
        )

    except ClientError as e:
        return error_response(
            e,
            "Tenant user request failed",
            status=500,
            log_context="tenant_admin_users ClientError",
        )


@tenant_admin_users_bp.route("/users/<username>", methods=["DELETE"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_membership_required()
def delete_tenant_user(username, user_email, user_roles, tenant) -> ResponseReturnValue:
    """
    Delete user from current tenant. Uses CognitoService.remove_tenant_from_user()
    as the single code path for tenant removal / user deletion.
    """
    try:
        # Get current tenant from request header

        # Resolve the target Cognito pool from the caller token (token mode) and
        # thread it through CognitoService so it acts on the caller's registry pool.
        try:
            user_pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return error_response(
                e,
                "Failed to resolve admin pool",
                status=500,
                log_context="tenant_admin_users _resolve_pool_id",
            )

        # Verify target user belongs to this tenant before proceeding
        try:
            target_tenants = cognito_service.get_user_tenants(
                username, user_pool_id=user_pool_id
            )
        except Exception:
            return jsonify({"error": f"User not found: {username}"}), 404

        if not target_tenants or tenant not in target_tenants:
            return jsonify(
                {
                    "error": "User not in this tenant",
                    "message": f"User {username} does not have access to tenant {tenant}",
                }
            ), 403

        # Delegate to CognitoService — single code path with safety guard
        _success, user_deleted = cognito_service.remove_tenant_from_user(
            username, tenant, user_pool_id=user_pool_id
        )

        # Clean up per-tenant roles from DB
        target_email = username  # username is the email in Cognito
        db = DatabaseManager()
        db.execute_query(
            "DELETE FROM user_tenant_roles WHERE email = %s AND administration = %s",
            (target_email, tenant),
            fetch=False,
            commit=True,
        )
        from auth.role_cache import invalidate_cache

        invalidate_cache(target_email, tenant)

        if user_deleted:
            message = f"User {username} deleted (was only in this tenant)"
        else:
            message = f"User {username} removed from tenant {tenant}"

        print(f"AUDIT: {message} by {user_email}", flush=True)

        return jsonify(
            {"success": True, "message": message, "user_deleted": user_deleted}
        )

    except ValueError as e:
        # Safety guard triggered (malformed tenants) or user not found —
        # deliberate, caller-safe validation message (not a stack trace).
        validation_message = str(e)
        return jsonify({"success": False, "error": validation_message}), 400
    except ClientError as e:
        return error_response(
            e,
            "Tenant user request failed",
            status=500,
            log_context="tenant_admin_users ClientError",
        )
