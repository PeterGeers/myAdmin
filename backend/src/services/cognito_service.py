"""
Cognito Service

Centralized service for AWS Cognito operations.
Provides methods for user and group management with proper error handling.
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from auth.admin_pool_resolver import PoolResolutionError, resolve_pool_id_for_email

# Initialize logger
logger = logging.getLogger(__name__)


class CognitoService:
    """Service class for AWS Cognito operations.

    Pool resolution (bugfix ``cognito-admin-pool-resolution``, R1 + R2): the target
    ``user_pool_id`` is no longer read from the legacy ``COGNITO_USER_POOL_ID`` var in
    ``__init__``. Instead, every admin op resolves its pool through the shared
    registry-backed resolver (:mod:`auth.admin_pool_resolver`), keyed to the target
    user, exactly like token validation. Callers may still pass an explicit
    ``user_pool_id`` (constructor or per call) to bypass resolution — e.g. a caller
    that already resolved the pool in token mode.
    """

    def __init__(self, user_pool_id: str | None = None):
        """Initialize the boto3 Cognito client.

        Args:
            user_pool_id: Optional explicit pool id. When provided it is used for
                every op on this instance (a caller that already resolved the pool,
                e.g. in token mode, passes it here). When ``None`` each user-scoped op
                resolves its pool per call via the shared resolver (email mode) using
                the target username; ops that carry no username require the pool id to
                be passed to the method (or set here).
        """
        self.region = os.getenv("AWS_REGION", "eu-west-1")
        # Explicit override (constructor). NOT a legacy COGNITO_USER_POOL_ID read.
        # Exposed as ``user_pool_id`` for backward compatibility with callers that
        # read it; it is ``None`` unless a caller passed an explicit pool id.
        self.user_pool_id = user_pool_id

        self.client = boto3.client("cognito-idp", region_name=self.region)

    # ========================================================================
    # Pool Resolution
    # ========================================================================

    def resolve_pool_id(
        self, username: str | None = None, user_pool_id: str | None = None
    ) -> str:
        """Resolve the target Cognito pool id for an admin op (registry-backed).

        Resolution order:

        1. An explicit ``user_pool_id`` passed to the call wins.
        2. Else an explicit pool id set on the instance (constructor) wins.
        3. Else, when a ``username`` (email) is available, resolve via the shared
           resolver in email mode (probe the registered pools for the user), sharing
           this service's boto3 client so probe and op hit the same client.
        4. Else there is nothing to resolve against — raise
           :class:`~auth.admin_pool_resolver.PoolResolutionError`.

        Only the ``UserPoolId`` value changes versus the legacy behavior; every
        request/response contract is preserved.
        """
        if user_pool_id is not None:
            return user_pool_id
        if self.user_pool_id is not None:
            return self.user_pool_id
        if username is not None:
            resolved = resolve_pool_id_for_email(username, client=self.client)
            # Email mode only returns None under anti_enumeration (not used here).
            if resolved is None:  # pragma: no cover - defensive
                raise PoolResolutionError(
                    f"Could not resolve a Cognito pool for user '{username}'."
                )
            return resolved
        raise PoolResolutionError(
            "Cannot resolve the target Cognito pool: no username to resolve by and "
            "no explicit user_pool_id was provided."
        )

    # ========================================================================
    # User Management Methods
    # ========================================================================

    def create_user(
        self,
        email: str,
        name: str | None = None,
        tenant: str | None = None,
        password: str | None = None,
        suppress_email: bool = True,
        user_pool_id: str | None = None,
    ) -> dict:
        """
        Create a new user in Cognito

        Args:
            email: User's email address (used as username)
            name: User's display name
            tenant: Tenant to assign user to
            password: Temporary password (required for new users)
            suppress_email: If True, don't send welcome email

        Returns:
            Dict with user information

        Raises:
            ClientError: If user creation fails
        """
        try:
            # Normalize email to lowercase for Cognito case-sensitivity
            email = email.strip().lower()

            pool_id = self.resolve_pool_id(
                username=email, user_pool_id=user_pool_id
            )

            # Build user attributes
            user_attributes = [
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ]

            if name:
                user_attributes.append({"Name": "name", "Value": name})

            if tenant:
                user_attributes.append(
                    {"Name": "custom:tenants", "Value": json.dumps([tenant])}
                )

            # Create user
            response = self.client.admin_create_user(
                UserPoolId=pool_id,
                Username=email,
                UserAttributes=user_attributes,
                TemporaryPassword=password,
                MessageAction="SUPPRESS" if suppress_email else "RESEND",
            )

            logger.info(f"User {email} created successfully")
            return response["User"]

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            logger.error(
                f"Failed to create user {email}: {error_code} - {error_message}"
            )
            raise

    def get_user(
        self, username: str, user_pool_id: str | None = None
    ) -> dict | None:
        """
        Get user details from Cognito

        Args:
            username: Username (email)
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            Dict with user information or None if not found
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            response = self.client.admin_get_user(
                UserPoolId=pool_id, Username=username
            )
            return response
        except ClientError as e:
            if e.response["Error"]["Code"] == "UserNotFoundException":
                return None
            logger.error(f"Failed to get user {username}: {e}")
            raise

    def list_users(
        self,
        tenant: str | None = None,
        limit: int = 60,
        user_pool_id: str | None = None,
    ) -> list[dict]:
        """
        List users from Cognito, optionally filtered by tenant

        Args:
            tenant: Optional tenant filter
            limit: Maximum number of users to return per page
            user_pool_id: Pool id to list from (no username to resolve by, so a
                caller passes the resolved pool id, e.g. from token mode)

        Returns:
            List of user dictionaries
        """
        try:
            pool_id = self.resolve_pool_id(user_pool_id=user_pool_id)
            users = []
            pagination_token = None

            while True:
                params = {"UserPoolId": pool_id, "Limit": limit}

                if pagination_token:
                    params["PaginationToken"] = pagination_token

                response = self.client.list_users(**params)

                # Filter by tenant if specified
                if tenant:
                    for user in response.get("Users", []):
                        user_tenants = self._get_user_attribute(
                            user.get("Attributes", []), "custom:tenants"
                        )
                        if user_tenants and tenant in user_tenants:
                            users.append(user)
                else:
                    users.extend(response.get("Users", []))

                pagination_token = response.get("PaginationToken")
                if not pagination_token:
                    break

            return users

        except ClientError as e:
            logger.error(f"Failed to list users: {e}")
            raise

    def update_user(
        self,
        username: str,
        name: str | None = None,
        enabled: bool | None = None,
        user_pool_id: str | None = None,
    ) -> bool:
        """
        Update user attributes

        Args:
            username: Username (email)
            name: New display name
            enabled: Enable/disable user
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            True if successful
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            # Update name if provided
            if name is not None:
                self.client.admin_update_user_attributes(
                    UserPoolId=pool_id,
                    Username=username,
                    UserAttributes=[{"Name": "name", "Value": name}],
                )

            # Update enabled status if provided
            if enabled is not None:
                if enabled:
                    self.client.admin_enable_user(
                        UserPoolId=pool_id, Username=username
                    )
                else:
                    self.client.admin_disable_user(
                        UserPoolId=pool_id, Username=username
                    )

            logger.info(f"User {username} updated successfully")
            return True

        except ClientError as e:
            logger.error(f"Failed to update user {username}: {e}")
            raise

    def delete_user(
        self, username: str, user_pool_id: str | None = None
    ) -> bool:
        """
        Delete user from Cognito

        Args:
            username: Username (email)
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            True if successful
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            self.client.admin_delete_user(
                UserPoolId=pool_id, Username=username
            )
            logger.info(f"User {username} deleted successfully")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete user {username}: {e}")
            raise

    # ========================================================================
    # Group (Role) Management Methods
    # ========================================================================

    def assign_role(
        self, username: str, role: str, user_pool_id: str | None = None
    ) -> bool:
        """
        Assign role (group) to user

        Args:
            username: Username (email)
            role: Role name (Cognito group name)
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            True if successful
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            self.client.admin_add_user_to_group(
                UserPoolId=pool_id, Username=username, GroupName=role
            )
            logger.info(f"Role {role} assigned to user {username}")
            return True
        except ClientError as e:
            logger.error(f"Failed to assign role {role} to user {username}: {e}")
            raise

    def remove_role(
        self, username: str, role: str, user_pool_id: str | None = None
    ) -> bool:
        """
        Remove role (group) from user

        Args:
            username: Username (email)
            role: Role name (Cognito group name)
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            True if successful
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            self.client.admin_remove_user_from_group(
                UserPoolId=pool_id, Username=username, GroupName=role
            )
            logger.info(f"Role {role} removed from user {username}")
            return True
        except ClientError as e:
            logger.error(f"Failed to remove role {role} from user {username}: {e}")
            raise

    def list_user_groups(
        self, username: str, user_pool_id: str | None = None
    ) -> list[str]:
        """
        Get list of groups (roles) for a user

        Args:
            username: Username (email)
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            List of group names
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            response = self.client.admin_list_groups_for_user(
                UserPoolId=pool_id, Username=username
            )
            return [group["GroupName"] for group in response.get("Groups", [])]
        except ClientError as e:
            logger.error(f"Failed to list groups for user {username}: {e}")
            raise

    def list_groups(
        self, limit: int = 60, user_pool_id: str | None = None
    ) -> list[dict]:
        """
        List all Cognito groups (roles)

        Args:
            limit: Maximum number of groups to return per page
            user_pool_id: Pool id to list from (no username to resolve by, so a
                caller passes the resolved pool id, e.g. from token mode)

        Returns:
            List of group dictionaries
        """
        try:
            pool_id = self.resolve_pool_id(user_pool_id=user_pool_id)
            groups = []
            next_token = None

            while True:
                params = {"UserPoolId": pool_id, "Limit": limit}

                if next_token:
                    params["NextToken"] = next_token

                response = self.client.list_groups(**params)
                groups.extend(response.get("Groups", []))

                next_token = response.get("NextToken")
                if not next_token:
                    break

            return groups

        except ClientError as e:
            logger.error(f"Failed to list groups: {e}")
            raise

    def create_group(
        self, name: str, description: str = "", user_pool_id: str | None = None
    ) -> dict:
        """
        Create a new Cognito group (role)

        Args:
            name: Group name
            description: Group description
            user_pool_id: Pool id to create the group in (no username to resolve by)

        Returns:
            Dict with group information
        """
        try:
            pool_id = self.resolve_pool_id(user_pool_id=user_pool_id)
            response = self.client.create_group(
                UserPoolId=pool_id, GroupName=name, Description=description
            )
            logger.info(f"Group {name} created successfully")
            return response["Group"]
        except ClientError as e:
            logger.error(f"Failed to create group {name}: {e}")
            raise

    def update_group(
        self,
        name: str,
        description: str | None = None,
        precedence: int | None = None,
        user_pool_id: str | None = None,
    ) -> dict:
        """
        Update Cognito group (role)

        Args:
            name: Group name
            description: New description
            precedence: New precedence value
            user_pool_id: Pool id the group lives in (no username to resolve by)

        Returns:
            Dict with updated group information
        """
        try:
            pool_id = self.resolve_pool_id(user_pool_id=user_pool_id)
            params = {"UserPoolId": pool_id, "GroupName": name}

            if description is not None:
                params["Description"] = description

            if precedence is not None:
                params["Precedence"] = precedence

            response = self.client.update_group(**params)
            logger.info(f"Group {name} updated successfully")
            return response["Group"]
        except ClientError as e:
            logger.error(f"Failed to update group {name}: {e}")
            raise

    def delete_group(
        self, name: str, user_pool_id: str | None = None
    ) -> bool:
        """
        Delete Cognito group (role)

        Args:
            name: Group name
            user_pool_id: Pool id the group lives in (no username to resolve by)

        Returns:
            True if successful
        """
        try:
            pool_id = self.resolve_pool_id(user_pool_id=user_pool_id)
            self.client.delete_group(UserPoolId=pool_id, GroupName=name)
            logger.info(f"Group {name} deleted successfully")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete group {name}: {e}")
            raise

    def get_group_user_count(
        self, group_name: str, user_pool_id: str | None = None
    ) -> int:
        """
        Get number of users in a group

        Args:
            group_name: Group name
            user_pool_id: Pool id the group lives in (no username to resolve by)

        Returns:
            Number of users in the group
        """
        try:
            pool_id = self.resolve_pool_id(user_pool_id=user_pool_id)
            response = self.client.list_users_in_group(
                UserPoolId=pool_id, GroupName=group_name, Limit=60
            )
            return len(response.get("Users", []))
        except ClientError as e:
            logger.error(f"Failed to get user count for group {group_name}: {e}")
            return 0

    # ========================================================================
    # Tenant Management Methods
    # ========================================================================

    def add_tenant_to_user(
        self, username: str, tenant: str, user_pool_id: str | None = None
    ) -> bool:
        """
        Add tenant to user's custom:tenants attribute

        Args:
            username: Username (email)
            tenant: Tenant identifier
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            True if successful
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            # Get current user
            user = self.get_user(username, user_pool_id=pool_id)
            if not user:
                raise ValueError(f"User {username} not found")

            # Get current tenants
            current_tenants = self._get_user_attribute(
                user.get("UserAttributes", []), "custom:tenants"
            )

            # Add new tenant if not already present
            if tenant not in current_tenants:
                current_tenants.append(tenant)

                self.client.admin_update_user_attributes(
                    UserPoolId=pool_id,
                    Username=username,
                    UserAttributes=[
                        {"Name": "custom:tenants", "Value": json.dumps(current_tenants)}
                    ],
                )
                logger.info(f"Tenant {tenant} added to user {username}")

            return True

        except ClientError as e:
            logger.error(f"Failed to add tenant {tenant} to user {username}: {e}")
            raise

    def remove_tenant_from_user(
        self, username: str, tenant: str, user_pool_id: str | None = None
    ) -> tuple[bool, bool]:
        """
        Remove tenant from user's custom:tenants attribute.

        Safety guard: validates the tenants list before deciding whether to
        remove-tenant or delete the user entirely. Prevents accidental full
        deletion when the custom:tenants attribute is malformed or empty.

        Args:
            username: Username (email)
            tenant: Tenant identifier
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            Tuple of (success, user_deleted)
            - success: True if operation succeeded
            - user_deleted: True if user was deleted (had only one tenant)
        """
        try:
            pool_id = self.resolve_pool_id(
                username=username, user_pool_id=user_pool_id
            )
            # Get current user
            user = self.get_user(username, user_pool_id=pool_id)
            if not user:
                raise ValueError(f"User {username} not found")

            # Get current tenants
            current_tenants = self._get_user_attribute(
                user.get("UserAttributes", []), "custom:tenants"
            )

            # Safety guard: validate tenants list is a proper list
            if not isinstance(current_tenants, list):
                logger.error(
                    f"SAFETY GUARD: custom:tenants for {username} is not a list "
                    f"(type={type(current_tenants).__name__}, value={current_tenants!r}). "
                    f"Refusing to delete. Manual intervention required."
                )
                # Suppression kept intentionally: the route handler in
                # tenant_admin_users.delete_tenant_user catches ValueError to
                # return HTTP 400 for this safety-guard case. Switching to
                # TypeError would change that to a 500. Behaviour preserved.
                raise ValueError(  # noqa: TRY004
                    f"Malformed tenants attribute for {username}. "
                    f"Cannot safely remove tenant. Contact SysAdmin."
                )

            logger.info(
                f"Remove tenant '{tenant}' from user {username}. "
                f"Current tenants: {current_tenants}"
            )

            if tenant not in current_tenants:
                logger.warning(f"Tenant {tenant} not in user {username}'s tenants list")
                return True, False

            # Remove tenant
            current_tenants.remove(tenant)

            # If user has no more tenants, delete user
            if not current_tenants:
                self.delete_user(username, user_pool_id=pool_id)
                logger.info(f"User {username} deleted (no remaining tenants)")
                return True, True

            # Otherwise, update tenants list
            self.client.admin_update_user_attributes(
                UserPoolId=pool_id,
                Username=username,
                UserAttributes=[
                    {"Name": "custom:tenants", "Value": json.dumps(current_tenants)}
                ],
            )
            logger.info(
                f"Tenant {tenant} removed from user {username}. "
                f"Remaining tenants: {current_tenants}"
            )

            return True, False

        except ClientError as e:
            logger.error(f"Failed to remove tenant {tenant} from user {username}: {e}")
            raise

    def get_user_tenants(
        self, username: str, user_pool_id: str | None = None
    ) -> list[str]:
        """
        Get list of tenants for a user

        Args:
            username: Username (email)
            user_pool_id: Optional explicit pool id (else resolved per user)

        Returns:
            List of tenant identifiers
        """
        try:
            user = self.get_user(username, user_pool_id=user_pool_id)
            if not user:
                return []

            return self._get_user_attribute(
                user.get("UserAttributes", []), "custom:tenants"
            )
        except ClientError as e:
            logger.error(f"Failed to get tenants for user {username}: {e}")
            return []

    # ========================================================================
    # Notification Methods
    # ========================================================================

    def send_invitation(self, email: str, temporary_password: str, tenant: str) -> bool:
        """
        Send invitation email via AWS SES directly to the recipient.

        Args:
            email: User's email address
            temporary_password: Temporary password
            tenant: Tenant name

        Returns:
            True if successful
        """
        try:
            # Import email template service
            from services.email_template_service import EmailTemplateService
            from services.ses_email_service import SESEmailService

            email_service = EmailTemplateService(administration=tenant)
            ses = SESEmailService()

            # Render HTML and plain text versions
            html_content = email_service.render_user_invitation(
                email=email,
                temporary_password=temporary_password,
                tenant=tenant,
                format="html",
            )

            text_content = email_service.render_user_invitation(
                email=email,
                temporary_password=temporary_password,
                tenant=tenant,
                format="txt",
            )

            # Get subject line
            subject = email_service.get_invitation_subject(tenant)

            # Fallback to simple text if templates fail
            if not text_content:
                text_content = f"""
Welcome to myAdmin!

You have been invited to join the {tenant} tenant.

Your login credentials:
Email: {email}
Temporary Password: {temporary_password}

Please log in and change your password at your earliest convenience.

Login URL: {self._get_frontend_url()}
"""

            result = ses.send_invitation(
                to_email=email,
                subject=subject,
                html_body=html_content,
                text_body=text_content,
                administration=tenant,
            )

            if result["success"]:
                logger.info(f"Invitation email sent to {email} for tenant {tenant}")
                return True
            else:
                logger.error(
                    f"SES failed to send invitation to {email}: {result.get('error')}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to send invitation to {email}: {e}")
            import traceback

            traceback.print_exc()
            return False

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _get_frontend_url(self) -> str:
        """Get frontend URL from request context or environment"""
        try:
            from utils.frontend_url import get_frontend_url

            return get_frontend_url()
        except Exception:
            return os.getenv("FRONTEND_URL", "http://localhost:3000")

    def _get_user_attribute(
        self, user_attributes: list[dict], attribute_name: str
    ) -> any:
        """
        Extract attribute value from Cognito user attributes

        Args:
            user_attributes: List of user attribute dictionaries
            attribute_name: Name of attribute to extract

        Returns:
            Attribute value (parsed JSON for custom:tenants)
        """
        for attr in user_attributes:
            if attr["Name"] == attribute_name:
                value = attr["Value"]

                # Handle JSON arrays (custom:tenants)
                if attribute_name == "custom:tenants":
                    try:
                        return json.loads(value) if value else []
                    except json.JSONDecodeError:
                        return [value] if value else []

                return value

        # Return appropriate default
        if attribute_name == "custom:tenants":
            return []
        return None
