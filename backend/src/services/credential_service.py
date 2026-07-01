"""
Credential Service for Railway Migration
Handles encryption, decryption, and storage of tenant-specific credentials in MySQL.

This service provides secure credential management for multi-tenant applications,
storing encrypted credentials in the database using AES-256 encryption with
per-tenant key derivation via PBKDF2-SHA256.
"""

import os
import json
import base64
import logging
from typing import Optional, Any
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class CredentialDecryptionError(Exception):
    """
    Raised when a credential cannot be decrypted with either the tenant-derived
    key or the master key.

    Contains tenant and credential type context for diagnostics but never
    exposes key material.
    """

    def __init__(self, tenant: str, credential_type: str):
        self.tenant = tenant
        self.credential_type = credential_type
        super().__init__(
            f"Credential decryption failed for tenant '{tenant}', "
            f"type '{credential_type}': unrecoverable with available keys"
        )


class CredentialService:
    """
    Service for managing encrypted tenant credentials in MySQL database.

    Supports encryption/decryption of credentials and CRUD operations
    for tenant-specific credential storage. Uses per-tenant derived keys
    (PBKDF2-SHA256) for encryption isolation between tenants.
    """

    def __init__(self, db_manager, encryption_key: Optional[str] = None):
        """
        Initialize the credential service.

        Args:
            db_manager: DatabaseManager instance for database operations
            encryption_key: Optional encryption key. If not provided, reads from environment.

        Raises:
            ValueError: If encryption key is not provided and not found in environment
        """
        self.db = db_manager
        self.encryption_key = encryption_key or os.getenv("CREDENTIALS_ENCRYPTION_KEY")

        if not self.encryption_key:
            raise ValueError(
                "Encryption key not found. Set CREDENTIALS_ENCRYPTION_KEY environment variable "
                "or provide encryption_key parameter."
            )

        # Master Fernet cipher (used for backward compatibility / fallback)
        self._fernet = self._create_fernet_cipher(self.encryption_key)

        logger.info("CredentialService initialized successfully")

    def _create_fernet_cipher(self, key: str) -> Fernet:
        """
        Create a Fernet cipher from the encryption key using a static salt.

        This is the master key cipher used for backward compatibility during
        migration from single-key to per-tenant keys.

        Args:
            key: The encryption key string

        Returns:
            Fernet cipher instance
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"myAdmin_credential_salt",  # Static salt for master key consistency
            iterations=100000,
            backend=default_backend(),
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        return Fernet(derived_key)

    def _derive_tenant_key(self, master_key: str, tenant: str) -> Fernet:
        """
        Derive a tenant-specific Fernet key using PBKDF2-SHA256.

        Each tenant gets a unique encryption key derived from the master key
        with the tenant identifier as the salt. This ensures that compromising
        one tenant's derived key does not expose other tenants' credentials.

        Args:
            master_key: The CREDENTIALS_ENCRYPTION_KEY
            tenant: The administration identifier (used as salt)

        Returns:
            Fernet cipher using the derived key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=tenant.encode("utf-8"),
            iterations=100_000,
            backend=default_backend(),
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(derived_key)

    def encrypt_credential(self, value: Any, tenant: Optional[str] = None) -> str:
        """
        Encrypt a credential value.

        When a tenant is provided, uses the tenant-derived key for encryption.
        Otherwise falls back to the master key (backward compatibility for
        non-tenant-scoped encryption like parameter_service).

        Args:
            value: The credential value to encrypt (string, dict, etc.)
            tenant: Optional tenant identifier for per-tenant key derivation

        Returns:
            Base64-encoded encrypted string

        Raises:
            Exception: If encryption fails
        """
        try:
            # Convert value to JSON string if it's not already a string
            if isinstance(value, str):
                plaintext = value
            else:
                plaintext = json.dumps(value)

            # Select the appropriate cipher
            if tenant:
                cipher = self._derive_tenant_key(self.encryption_key, tenant)
            else:
                cipher = self._fernet

            # Encrypt the plaintext
            encrypted_bytes = cipher.encrypt(plaintext.encode("utf-8"))

            # Return as base64 string for database storage
            return base64.b64encode(encrypted_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"Encryption failed: {type(e).__name__}")
            raise Exception(f"Failed to encrypt credential: {type(e).__name__}")

    def decrypt_credential(
        self, encrypted_value: str, tenant: Optional[str] = None
    ) -> Any:
        """
        Decrypt an encrypted credential value.

        When a tenant is provided, attempts decryption with the tenant-derived
        key first. If that fails with InvalidToken, falls back to the master key.
        When no tenant is provided, uses the master key directly (backward
        compatibility for parameter_service).

        Args:
            encrypted_value: Base64-encoded encrypted string
            tenant: Optional tenant identifier for per-tenant key derivation

        Returns:
            Decrypted value (string or dict if JSON)

        Raises:
            CredentialDecryptionError: If both tenant-derived and master key fail (when tenant provided)
            Exception: If decryption fails (when no tenant provided)
        """
        try:
            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_value.encode("utf-8"))

            if tenant:
                # Try tenant-derived key first
                tenant_cipher = self._derive_tenant_key(self.encryption_key, tenant)
                try:
                    decrypted_bytes = tenant_cipher.decrypt(encrypted_bytes)
                except InvalidToken:
                    # Fall back to master key
                    try:
                        decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
                    except InvalidToken:
                        raise CredentialDecryptionError(tenant, "unknown")
            else:
                # No tenant context — use master key directly
                decrypted_bytes = self._fernet.decrypt(encrypted_bytes)

            plaintext = decrypted_bytes.decode("utf-8")

            # Try to parse as JSON
            try:
                return json.loads(plaintext)
            except json.JSONDecodeError:
                return plaintext

        except CredentialDecryptionError:
            raise
        except Exception as e:
            if tenant:
                raise CredentialDecryptionError(tenant, "unknown")
            logger.error(f"Decryption failed: {type(e).__name__}")
            raise Exception(f"Failed to decrypt credential: {type(e).__name__}")

    def store_credential(
        self, administration: str, credential_type: str, value: Any
    ) -> bool:
        """
        Store an encrypted credential in the database.

        Uses tenant-derived key for encryption to ensure per-tenant isolation.
        If a credential with the same administration and type exists, it will be updated.

        Args:
            administration: The tenant/administration identifier
            credential_type: Type of credential (e.g., 'google_drive', 's3')
            value: The credential value to store (will be encrypted)

        Returns:
            True if successful

        Raises:
            Exception: If storage fails
        """
        try:
            # Encrypt the credential with the tenant-derived key
            encrypted_value = self.encrypt_credential(value, tenant=administration)

            # Store in database (INSERT or UPDATE)
            query = """
                INSERT INTO tenant_credentials (administration, credential_type, encrypted_value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    encrypted_value = VALUES(encrypted_value),
                    updated_at = CURRENT_TIMESTAMP
            """

            self.db.execute_query(
                query,
                (administration, credential_type, encrypted_value),
                fetch=False,
                commit=True,
            )

            logger.info(
                f"Stored credential for administration '{administration}', type '{credential_type}'"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store credential: {type(e).__name__}")
            raise Exception(f"Failed to store credential: {type(e).__name__}")

    def get_credential(
        self, administration: str, credential_type: str
    ) -> Optional[Any]:
        """
        Retrieve and decrypt a credential from the database.

        Attempts decryption with the tenant-derived key first. If that fails,
        falls back to the master key for backward compatibility (lazy migration).
        On successful master-key decryption, re-encrypts with the tenant-derived
        key and updates the database row.

        Args:
            administration: The tenant/administration identifier
            credential_type: Type of credential to retrieve

        Returns:
            Decrypted credential value, or None if not found

        Raises:
            CredentialDecryptionError: If decryption fails with both keys
        """
        try:
            query = """
                SELECT encrypted_value 
                FROM tenant_credentials 
                WHERE administration = %s AND credential_type = %s
            """

            results = self.db.execute_query(query, (administration, credential_type))

            if not results or len(results) == 0:
                logger.warning(
                    f"No credential found for administration '{administration}', type '{credential_type}'"
                )
                return None

            encrypted_value = results[0]["encrypted_value"]

            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_value.encode("utf-8"))

            # Try tenant-derived key first
            tenant_cipher = self._derive_tenant_key(self.encryption_key, administration)
            try:
                decrypted_bytes = tenant_cipher.decrypt(encrypted_bytes)
                plaintext = decrypted_bytes.decode("utf-8")
            except InvalidToken:
                # Fall back to master key (lazy migration)
                try:
                    decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
                    plaintext = decrypted_bytes.decode("utf-8")

                    # Re-encrypt with tenant-derived key and update the database
                    self._migrate_credential(
                        administration, credential_type, plaintext, tenant_cipher
                    )
                except InvalidToken:
                    raise CredentialDecryptionError(administration, credential_type)

            # Try to parse as JSON
            try:
                result = json.loads(plaintext)
            except json.JSONDecodeError:
                result = plaintext

            logger.info(
                f"Retrieved credential for administration '{administration}', type '{credential_type}'"
            )
            return result

        except CredentialDecryptionError:
            raise
        except Exception as e:
            logger.error(f"Failed to get credential: {type(e).__name__}")
            raise CredentialDecryptionError(administration, credential_type)

    def _migrate_credential(
        self,
        administration: str,
        credential_type: str,
        plaintext: str,
        tenant_cipher: Fernet,
    ) -> None:
        """
        Re-encrypt a credential with the tenant-derived key and update the DB.

        Called during lazy migration when a credential is successfully decrypted
        with the master key but needs to be migrated to the tenant-derived key.

        Args:
            administration: The tenant/administration identifier
            credential_type: Type of credential
            plaintext: The decrypted plaintext value
            tenant_cipher: The tenant-derived Fernet cipher
        """
        try:
            new_encrypted_bytes = tenant_cipher.encrypt(plaintext.encode("utf-8"))
            new_encrypted_value = base64.b64encode(new_encrypted_bytes).decode("utf-8")

            update_query = """
                UPDATE tenant_credentials 
                SET encrypted_value = %s, updated_at = CURRENT_TIMESTAMP
                WHERE administration = %s AND credential_type = %s
            """
            self.db.execute_query(
                update_query,
                (new_encrypted_value, administration, credential_type),
                fetch=False,
                commit=True,
            )
            logger.info(
                f"Migrated credential to tenant-derived key for "
                f"administration '{administration}', type '{credential_type}'"
            )
        except Exception as e:
            # Migration failure is non-fatal — credential was already decrypted
            logger.warning(
                f"Failed to migrate credential for administration '{administration}', "
                f"type '{credential_type}': {type(e).__name__}"
            )

    def delete_credential(self, administration: str, credential_type: str) -> bool:
        """
        Delete a credential from the database.

        Args:
            administration: The tenant/administration identifier
            credential_type: Type of credential to delete

        Returns:
            True if deleted, False if not found

        Raises:
            Exception: If deletion fails
        """
        try:
            query = """
                DELETE FROM tenant_credentials 
                WHERE administration = %s AND credential_type = %s
            """

            rows_affected = self.db.execute_query(
                query, (administration, credential_type), fetch=False, commit=True
            )

            if rows_affected > 0:
                logger.info(
                    f"Deleted credential for administration '{administration}', type '{credential_type}'"
                )
                return True
            else:
                logger.warning(
                    f"No credential found to delete for administration '{administration}', type '{credential_type}'"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to delete credential: {type(e).__name__}")
            raise Exception(f"Failed to delete credential: {type(e).__name__}")

    def list_credential_types(self, administration: str) -> list:
        """
        List all credential types stored for an administration.

        Args:
            administration: The tenant/administration identifier

        Returns:
            List of credential type strings

        Raises:
            Exception: If query fails
        """
        try:
            query = """
                SELECT credential_type, created_at, updated_at
                FROM tenant_credentials 
                WHERE administration = %s
                ORDER BY credential_type
            """

            results = self.db.execute_query(query, (administration,))

            return [
                {
                    "type": row["credential_type"],
                    "created_at": row["created_at"].isoformat()
                    if row["created_at"]
                    else None,
                    "updated_at": row["updated_at"].isoformat()
                    if row["updated_at"]
                    else None,
                }
                for row in results
            ]

        except Exception as e:
            logger.error(f"Failed to list credentials: {type(e).__name__}")
            raise Exception(f"Failed to list credentials: {type(e).__name__}")

    def credential_exists(self, administration: str, credential_type: str) -> bool:
        """
        Check if a credential exists for an administration.

        Args:
            administration: The tenant/administration identifier
            credential_type: Type of credential to check

        Returns:
            True if credential exists, False otherwise
        """
        try:
            query = """
                SELECT COUNT(*) as count
                FROM tenant_credentials 
                WHERE administration = %s AND credential_type = %s
            """

            results = self.db.execute_query(query, (administration, credential_type))

            return results[0]["count"] > 0 if results else False

        except Exception as e:
            logger.error(f"Failed to check credential existence: {type(e).__name__}")
            return False
