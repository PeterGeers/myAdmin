"""
ParameterService: Resolves flat key-value parameters with scope inheritance and caching.

Scope resolution order: user -> role -> tenant -> system.
Secrets are encrypted/decrypted via CredentialService delegation.
Cache is in-process dict with write-through invalidation.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_SCOPES = ('system', 'tenant', 'role', 'user')
VALID_VALUE_TYPES = ('string', 'number', 'boolean', 'json')
SCOPE_CHAIN = ['user', 'role', 'tenant', 'system']


class ParameterService:
    """Resolves flat key-value parameters by walking the scope inheritance chain."""

    def __init__(self, db, credential_service=None):
        self._cache: Dict[tuple, Any] = {}
        self.db = db
        self.credential_service = credential_service

    def get_param(self, namespace: str, key: str, tenant: str = None,
                  role: str = None, user: str = None) -> Any:
        """
        Resolve parameter value by walking scope chain: user -> role -> tenant -> system.
        Returns None if no value found at any scope.
        """
        scope_lookups = [
            ('user', user),
            ('role', role),
            ('tenant', tenant),
            ('system', '_system_'),
        ]

        for scope, scope_id in scope_lookups:
            if scope_id is None:
                continue
            cache_key = (scope, scope_id, namespace, key)
            if cache_key in self._cache:
                return self._cache[cache_key]

            value = self._resolve_from_db(scope, scope_id, namespace, key)
            if value is not None:
                self._cache[cache_key] = value
                return value

        return None

    def set_param(self, scope: str, scope_id: str, namespace: str, key: str,
                  value: Any, value_type: str = 'string', is_secret: bool = False,
                  created_by: str = None) -> None:
        """
        Write parameter value at specified scope. Invalidates cache for this key.
        Encrypts value via CredentialService if is_secret=True.
        """
        if scope not in VALID_SCOPES:
            raise ValueError(f"Invalid scope '{scope}'. Valid scopes: {', '.join(VALID_SCOPES)}")
        if value_type not in VALID_VALUE_TYPES:
            raise ValueError(f"Invalid value_type '{value_type}'. Valid types: {', '.join(VALID_VALUE_TYPES)}")

        self._validate_value_type(value, value_type)

        store_value = value
        if is_secret:
            if self.credential_service is None:
                raise RuntimeError("CredentialService is required for secret parameters")
            store_value = self.credential_service.encrypt_credential(value)

        json_value = json.dumps(store_value)

        upsert_sql = """
            INSERT INTO parameters (scope, scope_id, namespace, `key`, value, value_type, is_secret, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                value = VALUES(value),
                value_type = VALUES(value_type),
                is_secret = VALUES(is_secret),
                created_by = VALUES(created_by)
        """
        self.db.execute_query(
            upsert_sql,
            (scope, scope_id, namespace, key, json_value, value_type, is_secret, created_by),
            fetch=False, commit=True
        )
        self._invalidate_cache(namespace, key)

    def delete_param(self, scope: str, scope_id: str, namespace: str, key: str) -> bool:
        """Delete parameter override at specified scope. Invalidates cache."""
        if scope not in VALID_SCOPES:
            raise ValueError(f"Invalid scope '{scope}'. Valid scopes: {', '.join(VALID_SCOPES)}")

        delete_sql = """
            DELETE FROM parameters
            WHERE scope = %s AND scope_id = %s AND namespace = %s AND `key` = %s
        """
        result = self.db.execute_query(
            delete_sql,
            (scope, scope_id, namespace, key),
            fetch=False, commit=True
        )
        self._invalidate_cache(namespace, key)
        return result is not None and result > 0

    def get_params_by_namespace(self, namespace: str, tenant: str) -> List[dict]:
        """
        Return all parameters in a namespace for a tenant, with scope origin indicator.
        Used by the admin API to show where each value comes from.
        """
        query = """
            SELECT id, scope, scope_id, namespace, `key`, value, value_type, is_secret
            FROM parameters
            WHERE namespace = %s AND (
                (scope = 'tenant' AND scope_id = %s)
                OR scope = 'system'
            )
            ORDER BY `key`, FIELD(scope, 'tenant', 'system')
        """
        rows = self.db.execute_query(query, (namespace, tenant), fetch=True)

        seen_keys = {}
        results = []
        for row in rows:
            key = row['key']
            if key in seen_keys:
                continue
            seen_keys[key] = True

            raw_value = row['value']
            parsed = self._parse_json_value(raw_value)

            if row['is_secret'] and self.credential_service:
                try:
                    parsed = self.credential_service.decrypt_credential(parsed)
                except Exception:
                    logger.warning("Failed to decrypt secret param %s.%s", namespace, key)

            results.append({
                'id': row['id'],
                'namespace': namespace,
                'key': key,
                'value': parsed,
                'value_type': row['value_type'],
                'scope_origin': row['scope'],
                'is_secret': bool(row['is_secret']),
            })

        return results

    def seed_module_params(self, tenant: str, module_name: str) -> int:
        """
        Seed required parameters for a module from ModuleRegistry defaults.
        Only seeds params that don't already have a tenant-level value.
        Returns count of params seeded.
        """
        from services.module_registry import MODULE_REGISTRY

        module = MODULE_REGISTRY.get(module_name)
        if not module:
            logger.warning("Module '%s' not found in MODULE_REGISTRY", module_name)
            return 0

        seeded = 0
        for param_key, param_def in module.get('required_params', {}).items():
            parts = param_key.split('.', 1)
            namespace = parts[0] if len(parts) > 1 else 'general'
            key = parts[1] if len(parts) > 1 else parts[0]

            existing = self._resolve_from_db('tenant', tenant, namespace, key)
            if existing is not None:
                continue

            default = param_def.get('default')
            if default is None:
                continue

            value_type = param_def.get('type', 'string')
            self.set_param('tenant', tenant, namespace, key, default,
                           value_type=value_type, created_by='module_seed')
            seeded += 1

        return seeded

    def _invalidate_cache(self, namespace: str, key: str) -> None:
        """Remove all cache entries matching this namespace+key across all scopes."""
        keys_to_remove = [
            k for k in self._cache
            if k[2] == namespace and k[3] == key
        ]
        for k in keys_to_remove:
            del self._cache[k]

    def _resolve_from_db(self, scope: str, scope_id: str,
                         namespace: str, key: str) -> Any:
        """Query the parameters table for a specific scope+key combination."""
        query = """
            SELECT value, is_secret FROM parameters
            WHERE scope = %s AND scope_id = %s AND namespace = %s AND `key` = %s
            LIMIT 1
        """
        rows = self.db.execute_query(query, (scope, scope_id, namespace, key), fetch=True)
        if not rows:
            return None

        row = rows[0]
        parsed = self._parse_json_value(row['value'])

        if row['is_secret'] and self.credential_service:
            try:
                parsed = self.credential_service.decrypt_credential(parsed)
            except Exception:
                logger.warning("Failed to decrypt secret param %s.%s at scope %s", namespace, key, scope)

        return parsed

    @staticmethod
    def _parse_json_value(raw) -> Any:
        """Parse a JSON-encoded value from the database."""
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw
        return raw

    @staticmethod
    def _validate_value_type(value: Any, value_type: str) -> None:
        """Validate that value matches the declared value_type."""
        if value_type == 'string' and not isinstance(value, str):
            raise ValueError(f"Expected string value, got {type(value).__name__}")
        elif value_type == 'number' and not isinstance(value, (int, float)):
            raise ValueError(f"Expected number value, got {type(value).__name__}")
        elif value_type == 'boolean' and not isinstance(value, bool):
            raise ValueError(f"Expected boolean value, got {type(value).__name__}")
        elif value_type == 'json' and not isinstance(value, (dict, list)):
            raise ValueError(f"Expected json value (dict or list), got {type(value).__name__}")
