"""
Credential Service for Railway Migration
Handles encryption, decryption, and storage of tenant-specific credentials in MySQL.

This service provides secure credential management for multi-tenant applications,
storing encrypted credentials in the database using AES-256 encryption.
"""

import os
import json
import base64
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class CredentialService:
    """
    Service for managing encrypted tenant credentials in MySQL database.
    
    Supports encryption/decryption of credentials and CRUD operations
    for tenant-specific credential storage.
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
        self.encryption_key = encryption_key or os.getenv('CREDENTIALS_ENCRYPTION_KEY')
        
        if not self.encryption_key:
            raise ValueError(
                "Encryption key not found. Set CREDENTIALS_ENCRYPTION_KEY environment variable "
                "or provide encryption_key parameter."
            )
        
        # Derive a proper Fernet key from the encryption key
        self._fernet = self._create_fernet_cipher(self.encryption_key)
        
        logger.info("CredentialService initialized successfully")
    
    def _create_fernet_cipher(self, key: str) -> Fernet:
        """
        Create a Fernet cipher from the encryption key.
        
        Uses PBKDF2 to derive a proper 32-byte key from the provided key string.
        
        Args:
            key: The encryption key string
            
        Returns:
            Fernet cipher instance
        """
        # Use PBKDF2 to derive a proper key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'myAdmin_credential_salt',  # Static salt for consistency
            iterations=100000,
            backend=default_backend()
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
        return Fernet(derived_key)
    
    def encrypt_credential(self, value: Any) -> str:
        """
        Encrypt a credential value.
        
        Supports strings, dicts, and other JSON-serializable objects.
        
        Args:
            value: The credential value to encrypt (string, dict, etc.)
            
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
            
            # Encrypt the plaintext
            encrypted_bytes = self._fernet.encrypt(plaintext.encode('utf-8'))
            
            # Return as base64 string for database storage
            return base64.b64encode(encrypted_bytes).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise Exception(f"Failed to encrypt credential: {str(e)}")
    
    def decrypt_credential(self, encrypted_value: str) -> Any:
        """
        Decrypt an encrypted credential value.
        
        Automatically detects if the decrypted value is JSON and parses it.
        
        Args:
            encrypted_value: Base64-encoded encrypted string
            
        Returns:
            Decrypted value (string or dict if JSON)
            
        Raises:
            Exception: If decryption fails
        """
        try:
            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_value.encode('utf-8'))
            
            # Decrypt
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            plaintext = decrypted_bytes.decode('utf-8')
            
            # Try to parse as JSON
            try:
                return json.loads(plaintext)
            except json.JSONDecodeError:
                # Not JSON, return as string
                return plaintext
                
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise Exception(f"Failed to decrypt credential: {str(e)}")
    
    def store_credential(self, administration: str, credential_type: str, value: Any) -> bool:
        """
        Store an encrypted credential in the database.
        
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
            # Encrypt the credential
            encrypted_value = self.encrypt_credential(value)
            
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
                commit=True
            )
            
            logger.info(f"Stored credential for administration '{administration}', type '{credential_type}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store credential: {e}")
            raise Exception(f"Failed to store credential: {str(e)}")
    
    def get_credential(self, administration: str, credential_type: str) -> Optional[Any]:
        """
        Retrieve and decrypt a credential from the database.
        
        Args:
            administration: The tenant/administration identifier
            credential_type: Type of credential to retrieve
            
        Returns:
            Decrypted credential value, or None if not found
            
        Raises:
            Exception: If retrieval or decryption fails
        """
        try:
            query = """
                SELECT encrypted_value 
                FROM tenant_credentials 
                WHERE administration = %s AND credential_type = %s
            """
            
            results = self.db.execute_query(query, (administration, credential_type))
            
            if not results or len(results) == 0:
                logger.warning(f"No credential found for administration '{administration}', type '{credential_type}'")
                return None
            
            encrypted_value = results[0]['encrypted_value']
            
            # Decrypt and return
            decrypted_value = self.decrypt_credential(encrypted_value)
            logger.info(f"Retrieved credential for administration '{administration}', type '{credential_type}'")
            
            return decrypted_value
            
        except Exception as e:
            logger.error(f"Failed to get credential: {e}")
            raise Exception(f"Failed to retrieve credential: {str(e)}")
    
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
                query,
                (administration, credential_type),
                fetch=False,
                commit=True
            )
            
            if rows_affected > 0:
                logger.info(f"Deleted credential for administration '{administration}', type '{credential_type}'")
                return True
            else:
                logger.warning(f"No credential found to delete for administration '{administration}', type '{credential_type}'")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete credential: {e}")
            raise Exception(f"Failed to delete credential: {str(e)}")
    
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
                    'type': row['credential_type'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
                }
                for row in results
            ]
            
        except Exception as e:
            logger.error(f"Failed to list credentials: {e}")
            raise Exception(f"Failed to list credentials: {str(e)}")
    
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
            
            return results[0]['count'] > 0 if results else False
            
        except Exception as e:
            logger.error(f"Failed to check credential existence: {e}")
            return False
