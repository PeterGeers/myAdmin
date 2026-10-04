"""
SysAdmin Role Management Endpoints

API endpoints for managing Cognito groups (roles)

Bugfix ``cognito-admin-pool-resolution`` (R1/R2): these role/group admin ops previously
targeted the legacy single-pool ``COGNITO_USER_POOL_ID`` var (which points at the PROD
pool in every environment) via a module-level ``USER_POOL_ID``. They now resolve their
target pool through the shared registry-backed resolver in **token mode**
(:func:`auth.admin_pool_resolver.resolve_pool_id_for_token`), keyed to the caller
token's verified ``iss``. Every route here is gated by
``@cognito_required(required_roles=["SysAdmin"])`` so the caller token is reliably
present on the Flask ``request`` and token mode applies. Only the value passed as
``UserPoolId=...`` changes; every request/response contract is preserved. A
:class:`PoolResolutionError` (genuine misconfig) maps to the existing 500
``{"error": ...}`` shape.
"""

import logging
import os

import boto3
from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.admin_pool_resolver import PoolResolutionError
from auth.cognito_utils import cognito_required
from routes.sysadmin_helpers import _resolve_pool_id
from services.module_registry import MODULE_REGISTRY

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize Cognito client
cognito_client = boto3.client(
    "cognito-idp", region_name=os.getenv("AWS_REGION", "eu-west-1")
)


# ``_caller_token`` / ``_resolve_pool_id`` are the canonical copies imported from
# ``routes.sysadmin_helpers`` (task H2). They are re-exported into this module's
# namespace so handlers call them as module globals and existing patch points
# (``routes.sysadmin_roles._resolve_pool_id``) keep working unchanged.


# Build module role prefixes dynamically from MODULE_REGISTRY
# e.g. ['Finance', 'STR', 'ZZP'] derived from required_roles like 'Finance_Read', 'STR_CRUD'
_MODULE_ROLE_PREFIXES = list(
    {
        role.rsplit("_", 1)[0]
        for defn in MODULE_REGISTRY.values()
        for role in defn.get("required_roles", [])
        if "_" in role
    }
)

# Create blueprint
sysadmin_roles_bp = Blueprint("sysadmin_roles", __name__)


@sysadmin_roles_bp.route("", methods=["GET"])
@cognito_required(required_roles=["SysAdmin"])
def list_roles(user_email, user_roles) -> ResponseReturnValue:
    """
    List all Cognito groups (roles)

    Authorization: SysAdmin role required

    Returns groups categorized by type:
    - platform: SysAdmin, Tenant_Admin
    - module: Finance_Read, Finance_CRUD, Finance_Export, STR_Read, STR_CRUD, STR_Export
    """
    try:
        # Resolve the target Cognito pool from the caller token (token mode)
        user_pool_id = _resolve_pool_id()

        # List all groups
        response = cognito_client.list_groups(UserPoolId=user_pool_id, Limit=60)

        groups = []
        for group in response.get("Groups", []):
            group_name = group["GroupName"]

            # Get user count for this group
            users_response = cognito_client.list_users_in_group(
                UserPoolId=user_pool_id, GroupName=group_name, Limit=60
            )
            user_count = len(users_response.get("Users", []))

            # Categorize group
            if group_name in ["SysAdmin", "Tenant_Admin"]:
                category = "platform"
            elif any(module in group_name for module in ["Finance", "STR"]):
                category = "module"
            else:
                category = "other"

            groups.append(
                {
                    "name": group_name,
                    "description": group.get("Description", ""),
                    "precedence": group.get("Precedence"),
                    "user_count": user_count,
                    "category": category,
                    "created_date": group.get("CreationDate").isoformat()
                    if group.get("CreationDate")
                    else None,
                }
            )

        # Handle pagination if needed
        while "NextToken" in response:
            response = cognito_client.list_groups(
                UserPoolId=user_pool_id, Limit=60, NextToken=response["NextToken"]
            )
            for group in response.get("Groups", []):
                group_name = group["GroupName"]
                users_response = cognito_client.list_users_in_group(
                    UserPoolId=user_pool_id, GroupName=group_name, Limit=60
                )
                user_count = len(users_response.get("Users", []))

                if group_name in ["SysAdmin", "Tenant_Admin"]:
                    category = "platform"
                elif any(module in group_name for module in ["Finance", "STR"]):
                    category = "module"
                else:
                    category = "other"

                groups.append(
                    {
                        "name": group_name,
                        "description": group.get("Description", ""),
                        "precedence": group.get("Precedence"),
                        "user_count": user_count,
                        "category": category,
                        "created_date": group.get("CreationDate").isoformat()
                        if group.get("CreationDate")
                        else None,
                    }
                )

        return jsonify({"success": True, "roles": groups, "total": len(groups)})

    except PoolResolutionError as e:
        # Target pool could not be resolved (genuine misconfig) — preserve the
        # existing 500 {"error": ...} shape.
        logger.error(f"Error listing roles: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"Error listing roles: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@sysadmin_roles_bp.route("", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def create_role(user_email, user_roles) -> ResponseReturnValue:
    """
    Create new Cognito group (role)

    Authorization: SysAdmin role required

    Request body:
    {
        "name": "NewRole",
        "description": "Description of the role"
    }
    """
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get("name"):
            return jsonify({"error": "Missing required field: name"}), 400

        group_name = data["name"]
        description = data.get("description", "")
        precedence = data.get("precedence")

        # Resolve the target Cognito pool from the caller token (token mode)
        user_pool_id = _resolve_pool_id()

        # Check if group already exists
        try:
            cognito_client.get_group(UserPoolId=user_pool_id, GroupName=group_name)
            return jsonify({"error": f"Role {group_name} already exists"}), 400
        except cognito_client.exceptions.ResourceNotFoundException:
            pass  # Group doesn't exist, we can create it

        # Create group
        create_params = {
            "UserPoolId": user_pool_id,
            "GroupName": group_name,
            "Description": description,
        }
        if precedence is not None:
            create_params["Precedence"] = int(precedence)

        cognito_client.create_group(**create_params)

        logger.info(f"Role {group_name} created by {user_email}")

        return jsonify(
            {
                "success": True,
                "name": group_name,
                "description": description,
                "message": f"Role {group_name} created successfully",
            }
        ), 201

    except PoolResolutionError as e:
        # Target pool could not be resolved (genuine misconfig) — preserve the
        # existing 500 {"error": ...} shape.
        logger.error(f"Error creating role: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"Error creating role: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@sysadmin_roles_bp.route("/<role_name>", methods=["PUT"])
@cognito_required(required_roles=["SysAdmin"])
def update_role(user_email, user_roles, role_name) -> ResponseReturnValue:
    """
    Update Cognito group (role) description and precedence

    Authorization: SysAdmin role required

    Request body:
    {
        "description": "Updated description",
        "precedence": 50
    }

    Note: Group name cannot be changed
    """
    try:
        data = request.get_json()

        # Resolve the target Cognito pool from the caller token (token mode)
        user_pool_id = _resolve_pool_id()

        # Check if group exists
        try:
            cognito_client.get_group(UserPoolId=user_pool_id, GroupName=role_name)
        except cognito_client.exceptions.ResourceNotFoundException:
            return jsonify({"error": f"Role {role_name} not found"}), 404

        # Prepare update parameters
        update_params = {"UserPoolId": user_pool_id, "GroupName": role_name}

        if "description" in data:
            update_params["Description"] = data["description"]

        if "precedence" in data:
            update_params["Precedence"] = int(data["precedence"])

        # Update group
        cognito_client.update_group(**update_params)

        logger.info(f"Role {role_name} updated by {user_email}")

        return jsonify(
            {
                "success": True,
                "name": role_name,
                "message": f"Role {role_name} updated successfully",
            }
        )

    except PoolResolutionError as e:
        # Target pool could not be resolved (genuine misconfig) — preserve the
        # existing 500 {"error": ...} shape.
        logger.error(f"Error updating role: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"Error updating role: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@sysadmin_roles_bp.route("/<role_name>", methods=["DELETE"])
@cognito_required(required_roles=["SysAdmin"])
def delete_role(user_email, user_roles, role_name) -> ResponseReturnValue:
    """
    Delete Cognito group (role)

    Authorization: SysAdmin role required

    Note: Group must have zero users before deletion
    """
    try:
        # Resolve the target Cognito pool from the caller token (token mode)
        user_pool_id = _resolve_pool_id()

        # Check if group exists
        try:
            cognito_client.get_group(UserPoolId=user_pool_id, GroupName=role_name)
        except cognito_client.exceptions.ResourceNotFoundException:
            return jsonify({"error": f"Role {role_name} not found"}), 404

        # Check for users in group
        users_response = cognito_client.list_users_in_group(
            UserPoolId=user_pool_id, GroupName=role_name, Limit=1
        )

        if users_response.get("Users"):
            return jsonify(
                {
                    "error": f"Cannot delete role with active users. Please remove all users from {role_name} first."
                }
            ), 409

        # Delete group
        cognito_client.delete_group(UserPoolId=user_pool_id, GroupName=role_name)

        logger.info(f"Role {role_name} deleted by {user_email}")

        return jsonify(
            {
                "success": True,
                "name": role_name,
                "message": f"Role {role_name} deleted successfully",
            }
        )

    except PoolResolutionError as e:
        # Target pool could not be resolved (genuine misconfig) — preserve the
        # existing 500 {"error": ...} shape.
        logger.error(f"Error deleting role: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error(f"Error deleting role: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
