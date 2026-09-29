"""
System Administration Routes
Handles user and role management for SysAdmin users

Pool resolution (bugfix ``cognito-admin-pool-resolution``, R1/R2):
    These admin ops no longer read the legacy single-pool ``COGNITO_USER_POOL_ID``
    var (which pointed at the PROD pool in every environment). Every route is
    ``@cognito_required(required_roles=["SysAdmin"])`` and therefore carries an
    authenticated caller token, so each op resolves its target pool per request
    through the shared registry-backed resolver in **token mode**
    (:func:`auth.admin_pool_resolver.resolve_pool_id_for_token`), keyed to the
    caller token's verified ``iss`` — exactly how token validation resolves it. Only
    the value passed as ``UserPoolId=...`` changes; every request/response contract
    is preserved. When the pool cannot be resolved (registry misconfigured, or the
    registry-absent legacy fallback is also unset), the resolver raises
    :class:`PoolResolutionError`, which replaces the old ``COGNITO_USER_POOL_ID not
    configured`` guard with a clear 500 misconfiguration response.
"""

import os
import sys

from flask import Blueprint, jsonify, request

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import boto3
from botocore.exceptions import ClientError

from auth.admin_pool_resolver import PoolResolutionError, resolve_pool_id_for_token
from auth.cognito_utils import cognito_required

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

# Initialize Cognito client
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")

print(f"🔧 Admin Routes - AWS Region: {AWS_REGION}", flush=True)

cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)


def _caller_token() -> str:
    """Return the raw caller JWT from the request ``Authorization`` header.

    Every admin route here is gated by ``@cognito_required``, which has already
    validated the ``Bearer`` token before the handler runs; this simply re-reads
    that same header and strips the ``Bearer `` prefix to hand the raw token to the
    shared resolver's token mode. Mirrors how
    :func:`auth.cognito_utils.extract_user_credentials` reads the token.

    Returns:
        The raw JWT (without the ``Bearer `` prefix), or ``""`` when the header is
        absent/malformed (the resolver then surfaces the misconfiguration).
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :].strip()
    return auth_header.strip()


def _resolve_pool_id():
    """Resolve the target Cognito pool id for this admin request (token mode).

    Resolves through the shared registry-backed resolver keyed to the caller
    token's verified ``iss`` (2.3), replacing the legacy ``COGNITO_USER_POOL_ID``
    read. Raises :class:`PoolResolutionError` when the pool cannot be resolved so
    each handler can map it to a clear misconfiguration response (replacing the old
    ``COGNITO_USER_POOL_ID not configured`` 500 guard).
    """
    return resolve_pool_id_for_token(_caller_token())


@admin_bp.route("/test", methods=["GET"])
@cognito_required(required_permissions=[])
def test_auth(user_email, user_roles):
    """Test endpoint to verify authentication is working"""
    return jsonify(
        {
            "success": True,
            "message": "Authentication working",
            "user_email": user_email,
            "user_roles": user_roles,
            "has_sysadmin": "SysAdmin" in user_roles,
        }
    )


@admin_bp.route("/users", methods=["GET", "OPTIONS"])
@cognito_required(required_roles=["SysAdmin"])
def list_users(user_email, user_roles):
    """List all users in the Cognito User Pool"""
    print(f"📋 List users called by: {user_email} with roles: {user_roles}", flush=True)

    # Handle OPTIONS request for CORS
    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200

    try:
        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        response = cognito_client.list_users(UserPoolId=pool_id, Limit=60)

        users = []
        for user in response.get("Users", []):
            # Extract attributes
            attributes = {
                attr["Name"]: attr["Value"] for attr in user.get("Attributes", [])
            }

            user_data = {
                "username": user.get("Username"),
                "email": attributes.get("email"),
                "name": attributes.get("name"),  # Get name attribute
                "status": user.get("UserStatus"),
                "enabled": user.get("Enabled"),
                "created": user.get("UserCreateDate").isoformat()
                if user.get("UserCreateDate")
                else None,
                "modified": user.get("UserLastModifiedDate").isoformat()
                if user.get("UserLastModifiedDate")
                else None,
            }

            # Get user's groups
            try:
                groups_response = cognito_client.admin_list_groups_for_user(
                    Username=user.get("Username"), UserPoolId=pool_id
                )
                user_data["groups"] = [
                    g["GroupName"] for g in groups_response.get("Groups", [])
                ]
            except Exception:
                user_data["groups"] = []

            users.append(user_data)

        return jsonify({"success": True, "users": users, "count": len(users)})

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/users", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def create_user(user_email, user_roles):
    """Create a new user in the Cognito User Pool"""
    print(
        f"➕ Create user called by: {user_email} with roles: {user_roles}", flush=True
    )

    try:
        data = request.get_json()
        email = data.get("email")
        name = data.get("name")
        password = data.get("password")
        groups = data.get("groups", [])

        if not email or not password:
            return jsonify(
                {"success": False, "error": "Email and password are required"}
            ), 400

        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        # Build user attributes
        user_attributes = [
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ]

        # Add name if provided
        if name:
            user_attributes.append({"Name": "name", "Value": name})

        # Create user
        response = cognito_client.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=user_attributes,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",  # Don't send welcome email
        )

        username = response["User"]["Username"]

        # Add user to groups
        for group_name in groups:
            try:
                cognito_client.admin_add_user_to_group(
                    UserPoolId=pool_id, Username=username, GroupName=group_name
                )
            except ClientError as e:
                print(f"⚠️ Failed to add user to group {group_name}: {e}", flush=True)

        return jsonify(
            {
                "success": True,
                "message": f"User {email} created successfully",
                "username": username,
            }
        )

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        if error_code == "UsernameExistsException":
            return jsonify(
                {"success": False, "error": "A user with this email already exists"}
            ), 400
        elif error_code == "InvalidPasswordException":
            return jsonify(
                {
                    "success": False,
                    "error": "Password does not meet requirements (minimum 8 characters)",
                }
            ), 400
        else:
            return jsonify({"success": False, "error": error_message}), 500


@admin_bp.route("/groups", methods=["GET", "OPTIONS"])
@cognito_required(required_roles=["SysAdmin"])
def list_groups(user_email, user_roles):
    """List all groups (roles) in the Cognito User Pool"""
    # Handle OPTIONS request for CORS
    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200

    try:
        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        response = cognito_client.list_groups(UserPoolId=pool_id, Limit=60)

        groups = []
        for group in response.get("Groups", []):
            groups.append(
                {
                    "name": group.get("GroupName"),
                    "description": group.get("Description"),
                    "precedence": group.get("Precedence"),
                    "created": group.get("CreationDate").isoformat()
                    if group.get("CreationDate")
                    else None,
                    "modified": group.get("LastModifiedDate").isoformat()
                    if group.get("LastModifiedDate")
                    else None,
                }
            )

        return jsonify({"success": True, "groups": groups, "count": len(groups)})

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/users/<username>/groups", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def add_user_to_group(username, user_email, user_roles):
    """Add a user to a group (assign role)"""
    try:
        data = request.get_json()
        group_name = data.get("groupName")

        if not group_name:
            return jsonify({"success": False, "error": "groupName is required"}), 400

        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        cognito_client.admin_add_user_to_group(
            UserPoolId=pool_id, Username=username, GroupName=group_name
        )

        return jsonify(
            {"success": True, "message": f"User {username} added to group {group_name}"}
        )

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/users/<username>/groups/<group_name>", methods=["DELETE"])
@cognito_required(required_roles=["SysAdmin"])
def remove_user_from_group(username, group_name, user_email, user_roles):
    """Remove a user from a group (revoke role)"""
    try:
        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        cognito_client.admin_remove_user_from_group(
            UserPoolId=pool_id, Username=username, GroupName=group_name
        )

        return jsonify(
            {
                "success": True,
                "message": f"User {username} removed from group {group_name}",
            }
        )

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/users/<username>/enable", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def enable_user(username, user_email, user_roles):
    """Enable a user account"""
    try:
        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        cognito_client.admin_enable_user(UserPoolId=pool_id, Username=username)

        return jsonify({"success": True, "message": f"User {username} enabled"})

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/users/<username>/disable", methods=["POST"])
@cognito_required(required_roles=["SysAdmin"])
def disable_user(username, user_email, user_roles):
    """Disable a user account"""
    try:
        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        cognito_client.admin_disable_user(UserPoolId=pool_id, Username=username)

        return jsonify({"success": True, "message": f"User {username} disabled"})

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/users/<username>", methods=["DELETE"])
@cognito_required(required_roles=["SysAdmin"])
def delete_user(username, user_email, user_roles):
    """Delete a user account"""
    try:
        try:
            pool_id = _resolve_pool_id()
        except PoolResolutionError as e:
            return jsonify({"success": False, "error": str(e)}), 500

        cognito_client.admin_delete_user(UserPoolId=pool_id, Username=username)

        return jsonify({"success": True, "message": f"User {username} deleted"})

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/users/<username>/attributes", methods=["PUT"])
@cognito_required(required_roles=["SysAdmin"])
def update_user_attributes(username, user_email, user_roles):
    """Update user attributes (e.g., name)"""
    try:
        data = request.get_json()
        name = data.get("name")

        if name is None:
            return jsonify(
                {"success": False, "error": "name attribute is required"}
            ), 400

        # Build attributes list
        user_attributes = []
        if name:  # Only update if name is provided and not empty
            user_attributes.append({"Name": "name", "Value": name})

        if user_attributes:
            try:
                pool_id = _resolve_pool_id()
            except PoolResolutionError as e:
                return jsonify({"success": False, "error": str(e)}), 500

            cognito_client.admin_update_user_attributes(
                UserPoolId=pool_id,
                Username=username,
                UserAttributes=user_attributes,
            )

        return jsonify(
            {"success": True, "message": f"User {username} attributes updated"}
        )

    except ClientError as e:
        return jsonify({"success": False, "error": str(e)}), 500
