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
from typing import Any

logger = logging.getLogger(__name__)

VALID_SCOPES = ("system", "tenant", "role", "user")
VALID_VALUE_TYPES = ("string", "number", "boolean", "json")
SCOPE_CHAIN = ["user", "role", "tenant", "system"]

# ---------------------------------------------------------------------------
# CODE_DEFAULTS — system-scope parameter defaults defined in code.
#
# These act as the system-level values for parameters that should be
# discoverable in the ParameterManagement UI without requiring seed scripts.
# Tenant-scope DB rows take precedence; deleting a tenant override reverts
# to the code default.
#
# Key: (namespace, key)  →  Value: {value, value_type, description}
# ---------------------------------------------------------------------------
CODE_DEFAULTS: dict[tuple[str, str], dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Value-type mapping: PARAMETER_SCHEMA uses 'type' names that may differ
# from the VALID_VALUE_TYPES used by ParameterService.
# ---------------------------------------------------------------------------
_SCHEMA_TYPE_MAP = {
    "string": "string",
    "number": "number",
    "boolean": "boolean",
    "json": "json",
}

# Default values per value_type when the schema param has no explicit default.
_TYPE_EMPTY_DEFAULTS: dict[str, Any] = {
    "string": "",
    "number": 0,
    "boolean": False,
    "json": {},
}


def _register_code_defaults() -> None:
    """Populate CODE_DEFAULTS from all known sources.

    Called once at module load.  Sources:
    1. PARAMETER_SCHEMA — auto-generates a CODE_DEFAULT for every param
       defined in parameter_schema.py (storage, fin, str, str_branding,
       zzp_branding, …).  Uses the schema 'default' when present,
       otherwise falls back to an empty value for the type.
    2. Manual entries — for namespaces not covered by PARAMETER_SCHEMA
       (ui.pivot, ui.tables).
    """
    # ------------------------------------------------------------------
    # Auto-generate from PARAMETER_SCHEMA
    # ------------------------------------------------------------------
    try:
        from services.parameter_schema import PARAMETER_SCHEMA

        for namespace, section in PARAMETER_SCHEMA.items():
            for key, param_def in section.get("params", {}).items():
                schema_type = param_def.get("type", "string")
                value_type = _SCHEMA_TYPE_MAP.get(schema_type, "string")
                default_value = param_def.get(
                    "default", _TYPE_EMPTY_DEFAULTS.get(value_type, "")
                )
                description = param_def.get("description", param_def.get("label", key))
                CODE_DEFAULTS[(namespace, key)] = {
                    "value": default_value,
                    "value_type": value_type,
                    "description": description,
                }
    except ImportError:
        logger.warning(
            "parameter_schema not available; schema-based CODE_DEFAULTS skipped"
        )

    # ------------------------------------------------------------------
    # asset_retention — Media asset retention period defaults (days)
    # ------------------------------------------------------------------
    CODE_DEFAULTS[("asset_retention", "invoices_days")] = {
        "value": 2555,
        "value_type": "number",
        "description": "Invoice PDF retention (7 years)",
    }
    CODE_DEFAULTS[("asset_retention", "branding_days")] = {
        "value": 30,
        "value_type": "number",
        "description": "Logo/letterhead retention",
    }
    CODE_DEFAULTS[("asset_retention", "templates_days")] = {
        "value": 90,
        "value_type": "number",
        "description": "Template file retention",
    }
    CODE_DEFAULTS[("asset_retention", "landing_pages_days")] = {
        "value": 7,
        "value_type": "number",
        "description": "Landing page web content retention",
    }
    CODE_DEFAULTS[("asset_retention", "landing_pages_media_days")] = {
        "value": 30,
        "value_type": "number",
        "description": "Landing page images/videos retention",
    }

    # ------------------------------------------------------------------
    # ui.pivot — Allowed pivot columns per data source
    # ------------------------------------------------------------------
    CODE_DEFAULTS[("ui.pivot", "allowed_columns.vw_mutaties")] = {
        "value": {
            "groupable": [
                "Aangifte",
                "TransactionDate",
                "Reknum",
                "AccountName",
                "Parent",
                "VW",
                "jaar",
                "kwartaal",
                "maand",
                "week",
                "ReferenceNumber",
                "administration",
            ],
            "aggregatable": ["Amount"],
        },
        "value_type": "json",
        "description": "Allowed pivot columns for Financial Transactions (vw_mutaties)",
    }
    CODE_DEFAULTS[("ui.pivot", "allowed_columns.vw_bnb_total")] = {
        "value": {
            "groupable": [
                "channel",
                "listing",
                "checkinDate",
                "year",
                "q",
                "m",
                "country",
                "countryName",
                "countryRegion",
                "source_type",
                "status",
            ],
            "aggregatable": [
                "nights",
                "guests",
                "amountGross",
                "amountNett",
                "amountChannelFee",
                "amountTouristTax",
                "amountVat",
                "pricePerNight",
                "daysBeforeReservation",
            ],
        },
        "value_type": "json",
        "description": "Allowed pivot columns for STR Revenue (vw_bnb_total)",
    }

    # ui.pivot — Excluded columns per data source (hidden from pivot UI)
    CODE_DEFAULTS[("ui.pivot", "exclude_columns.vw_mutaties")] = {
        "value": ["TransactionNumber", "TransactionDescription", "Ref3", "Ref4"],
        "value_type": "json",
        "description": "Columns excluded from pivot for Financial Transactions",
    }
    CODE_DEFAULTS[("ui.pivot", "exclude_columns.vw_bnb_total")] = {
        "value": ["checkoutDate"],
        "value_type": "json",
        "description": "Columns excluded from pivot for STR Revenue",
    }

    # ui.pivot — Force-groupable columns per data source
    # (numeric columns that represent categories, not measures)
    CODE_DEFAULTS[("ui.pivot", "force_groupable.vw_mutaties")] = {
        "value": ["jaar", "kwartaal", "maand", "week"],
        "value_type": "json",
        "description": "Numeric columns treated as groupable for Financial Transactions",
    }
    CODE_DEFAULTS[("ui.pivot", "force_groupable.vw_bnb_total")] = {
        "value": ["year", "q", "m", "nights", "guests", "daysBeforeReservation"],
        "value_type": "json",
        "description": "Numeric columns treated as groupable for STR Revenue",
    }

    # ui.pivot — Registered data sources (sysadmin-only whitelist)
    # Only views/tables listed here can be used for pivot queries.
    # Sysadmin manages this at system scope to prevent access to system tables.
    CODE_DEFAULTS[("ui.pivot", "registered_sources")] = {
        "value": ["vw_mutaties", "vw_bnb_total"],
        "value_type": "json",
        "description": "Views/tables available as pivot data sources (sysadmin only)",
    }

    # ui.pivot — Human-readable labels per data source
    CODE_DEFAULTS[("ui.pivot", "datasource_label.vw_mutaties")] = {
        "value": "Financial Transactions",
        "value_type": "string",
        "description": "Display label for vw_mutaties pivot data source",
    }
    CODE_DEFAULTS[("ui.pivot", "datasource_label.vw_bnb_total")] = {
        "value": "STR Revenue",
        "value_type": "string",
        "description": "Display label for vw_bnb_total pivot data source",
    }

    # ui.pivot — Module assignment per data source
    # Tags each data source with its module (FIN, STR, ZZP) so the frontend
    # can filter available sources per report tab.
    CODE_DEFAULTS[("ui.pivot", "datasource_module.vw_mutaties")] = {
        "value": "FIN",
        "value_type": "string",
        "description": "Module assignment for vw_mutaties pivot data source",
    }
    CODE_DEFAULTS[("ui.pivot", "datasource_module.vw_bnb_total")] = {
        "value": "STR",
        "value_type": "string",
        "description": "Module assignment for vw_bnb_total pivot data source",
    }

    # ------------------------------------------------------------------
    # ui.tables — Table configuration defaults (columns, filters, sort, page size)
    # These match the seed values from seed_table_config_params.sql.
    # ------------------------------------------------------------------
    _table_defaults = {
        "chart_of_accounts.columns": {
            "value": [
                "Account",
                "AccountName",
                "AccountLookup",
                "SubParent",
                "Parent",
                "VW",
                "Belastingaangifte",
                "parameters",
            ],
            "value_type": "json",
            "description": "Visible columns for Chart of Accounts table",
        },
        "chart_of_accounts.filterable_columns": {
            "value": [
                "Account",
                "AccountName",
                "AccountLookup",
                "SubParent",
                "Parent",
                "VW",
                "Belastingaangifte",
                "parameters",
            ],
            "value_type": "json",
            "description": "Filterable columns for Chart of Accounts table",
        },
        "chart_of_accounts.default_sort": {
            "value": {"field": "Account", "direction": "asc"},
            "value_type": "json",
            "description": "Default sort for Chart of Accounts table",
        },
        "chart_of_accounts.page_size": {
            "value": 1000,
            "value_type": "number",
            "description": "Page size for Chart of Accounts table",
        },
        "parameters.columns": {
            "value": ["namespace", "key", "value", "value_type", "scope_origin"],
            "value_type": "json",
            "description": "Visible columns for Parameter Management table",
        },
        "parameters.filterable_columns": {
            "value": ["namespace", "key", "value", "value_type", "scope_origin"],
            "value_type": "json",
            "description": "Filterable columns for Parameter Management table",
        },
        "parameters.default_sort": {
            "value": {"field": "namespace", "direction": "asc"},
            "value_type": "json",
            "description": "Default sort for Parameter Management table",
        },
        "parameters.page_size": {
            "value": 100,
            "value_type": "number",
            "description": "Page size for Parameter Management table",
        },
        "banking_mutaties.columns": {
            "value": [
                "ID",
                "TransactionNumber",
                "TransactionDate",
                "TransactionDescription",
                "TransactionAmount",
                "Debet",
                "Credit",
                "ReferenceNumber",
                "Ref1",
                "Ref2",
                "Ref3",
                "Ref4",
                "Administration",
            ],
            "value_type": "json",
            "description": "Visible columns for Banking Mutaties table",
        },
        "banking_mutaties.filterable_columns": {
            "value": [
                "ID",
                "TransactionNumber",
                "TransactionDate",
                "TransactionDescription",
                "TransactionAmount",
                "Debet",
                "Credit",
                "ReferenceNumber",
                "Ref1",
                "Ref2",
                "Ref3",
                "Ref4",
                "Administration",
            ],
            "value_type": "json",
            "description": "Filterable columns for Banking Mutaties table",
        },
        "banking_mutaties.default_sort": {
            "value": {"field": "TransactionDate", "direction": "desc"},
            "value_type": "json",
            "description": "Default sort for Banking Mutaties table",
        },
        "banking_mutaties.page_size": {
            "value": 100,
            "value_type": "number",
            "description": "Page size for Banking Mutaties table",
        },
    }
    for key, default_def in _table_defaults.items():
        CODE_DEFAULTS[("ui.tables", key)] = default_def


_register_code_defaults()


class ParameterService:
    """Resolves flat key-value parameters by walking the scope inheritance chain."""

    def __init__(self, db, credential_service=None):
        self._cache: dict[tuple, Any] = {}
        self.db = db
        self.credential_service = credential_service

    def get_param(
        self,
        namespace: str,
        key: str,
        tenant: str | None = None,
        role: str | None = None,
        user: str | None = None,
    ) -> Any:
        """
        Resolve parameter value by walking scope chain: user -> role -> tenant -> system.
        Falls back to CODE_DEFAULTS at system scope when no DB value exists.
        Returns None if no value found at any scope.
        """
        scope_lookups = [
            ("user", user),
            ("role", role),
            ("tenant", tenant),
            ("system", "_system_"),
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

        # Fallback: check CODE_DEFAULTS (acts as system scope)
        code_default = CODE_DEFAULTS.get((namespace, key))
        if code_default is not None:
            return code_default["value"]

        return None

    def get_param_revision(
        self,
        namespace: str,
        key: str,
        tenant: str | None = None,
        role: str | None = None,
        user: str | None = None,
    ) -> Any:
        """Return the per-param revision (``updated_at``) of the resolved row, else None.

        Reads the ``updated_at`` timestamp of the FIRST scope row that actually
        resolves the ``get_param`` value (walking the same user -> role -> tenant
        chain, skipping any scope whose id is ``None``). This is the per-parameter
        freshness signal the governance projection needs to fix the "version-bump
        trap": the ``members.*`` config rows must bump their projected ``version``
        when a param is EDITED even though the tenant row was not touched, so the
        version-guarded conditional put in ``ProjectionSync`` actually writes the
        change instead of silently skipping it.

        ``updated_at`` is the ``parameters`` table's ``ON UPDATE CURRENT_TIMESTAMP``
        column: it advances on a genuine value change and is stable on an unchanged
        re-sync — exactly the monotonic-yet-idempotent property the conditional
        write relies on (R5.6). It is READ-ONLY (a plain SELECT); this method never
        writes MySQL, so the sync's one-directional guarantee is preserved.

        Returns ``None`` when the value comes from a ``CODE_DEFAULTS`` fallback (no
        DB row to date-stamp) or when no scope resolves — callers treat that as "no
        per-param revision" and fall back to the tenant-row version.
        """
        scope_lookups = [
            ("user", user),
            ("role", role),
            ("tenant", tenant),
            ("system", "_system_"),
        ]
        for scope, scope_id in scope_lookups:
            if scope_id is None:
                continue
            revision = self._resolve_revision_from_db(scope, scope_id, namespace, key)
            if revision is not None:
                return revision
        return None

    def set_param(
        self,
        scope: str,
        scope_id: str,
        namespace: str,
        key: str,
        value: Any,
        value_type: str = "string",
        is_secret: bool = False,
        created_by: str | None = None,
    ) -> None:
        """
        Write parameter value at specified scope. Invalidates cache for this key.
        Encrypts value via CredentialService if is_secret=True.
        """
        if scope not in VALID_SCOPES:
            raise ValueError(
                f"Invalid scope '{scope}'. Valid scopes: {', '.join(VALID_SCOPES)}"
            )
        if value_type not in VALID_VALUE_TYPES:
            raise ValueError(
                f"Invalid value_type '{value_type}'. Valid types: {', '.join(VALID_VALUE_TYPES)}"
            )

        self._validate_value_type(value, value_type)

        store_value = value
        if is_secret:
            if self.credential_service is None:
                raise RuntimeError(
                    "CredentialService is required for secret parameters"
                )
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
            (
                scope,
                scope_id,
                namespace,
                key,
                json_value,
                value_type,
                is_secret,
                created_by,
            ),
            fetch=False,
            commit=True,
        )
        self._invalidate_cache(namespace, key)

    def delete_param(self, scope: str, scope_id: str, namespace: str, key: str) -> bool:
        """Delete parameter override at specified scope. Invalidates cache."""
        if scope not in VALID_SCOPES:
            raise ValueError(
                f"Invalid scope '{scope}'. Valid scopes: {', '.join(VALID_SCOPES)}"
            )

        delete_sql = """
            DELETE FROM parameters
            WHERE scope = %s AND scope_id = %s AND namespace = %s AND `key` = %s
        """
        result = self.db.execute_query(
            delete_sql, (scope, scope_id, namespace, key), fetch=False, commit=True
        )
        self._invalidate_cache(namespace, key)
        return result is not None and result > 0

    def get_params_by_namespace(self, namespace: str, tenant: str) -> list[dict]:
        """
        Return all parameters in a namespace for a tenant, with scope origin indicator.
        Used by the admin API to show where each value comes from.

        Merges three sources:
        1. Tenant-scope DB rows  (scope_origin = 'tenant')
        2. System-scope DB rows  (scope_origin = 'system')
        3. CODE_DEFAULTS entries  (scope_origin = 'system', id = None)

        Tenant-scope rows take precedence over system-scope rows and code defaults.
        System-scope DB rows take precedence over code defaults for the same key.
        Code defaults that have no DB row at all are included with scope_origin 'system'.
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

        seen_keys: dict[str, bool] = {}
        results: list[dict] = []

        # Process DB rows first (tenant rows come before system rows due to ORDER BY)
        for row in rows:
            key = row["key"]
            if key in seen_keys:
                continue
            seen_keys[key] = True

            raw_value = row["value"]
            parsed = self._parse_json_value(raw_value)

            if row["is_secret"] and self.credential_service:
                try:
                    parsed = self.credential_service.decrypt_credential(parsed)
                except Exception:
                    logger.warning(
                        "Failed to decrypt secret param %s.%s", namespace, key
                    )

            results.append(
                {
                    "id": row["id"],
                    "namespace": namespace,
                    "key": key,
                    "value": parsed,
                    "value_type": row["value_type"],
                    "scope_origin": row["scope"],
                    "is_secret": bool(row["is_secret"]),
                    "has_code_default": (namespace, key) in CODE_DEFAULTS,
                }
            )

        # Merge CODE_DEFAULTS entries that have no matching DB row
        for (ns, key), default_def in CODE_DEFAULTS.items():
            if ns != namespace:
                continue
            if key in seen_keys:
                continue
            seen_keys[key] = True
            results.append(
                {
                    "id": None,
                    "namespace": namespace,
                    "key": key,
                    "value": default_def["value"],
                    "value_type": default_def["value_type"],
                    "scope_origin": "system",
                    "is_secret": False,
                    "has_code_default": True,
                }
            )

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
        for param_key, param_def in module.get("required_params", {}).items():
            parts = param_key.split(".", 1)
            namespace = parts[0] if len(parts) > 1 else "general"
            key = parts[1] if len(parts) > 1 else parts[0]

            existing = self._resolve_from_db("tenant", tenant, namespace, key)
            if existing is not None:
                continue

            default = param_def.get("default")
            if default is None:
                continue

            value_type = param_def.get("type", "string")
            self.set_param(
                "tenant",
                tenant,
                namespace,
                key,
                default,
                value_type=value_type,
                created_by="module_seed",
            )
            seeded += 1

        return seeded

    def invalidate_namespace(self, namespace: str, tenant: str | None = None) -> None:
        """Drop cached values for a whole ``namespace`` (optionally one tenant).

        The governance projection sync (:class:`services.projection_sync.ProjectionSync`)
        is a long-lived, process-wide singleton: its ``ParameterService`` is built once
        and REUSED across every on-change sync for the life of the Flask process. Because
        :meth:`get_param` memoises resolved values in :attr:`_cache`, a value read during
        one sync run stays cached, so a LATER sync run can serialize STALE content even
        though a tenant admin has since edited the param through a DIFFERENT service
        instance (the save route's own ``ParameterService``, whose write-through
        invalidation never reaches this one). Meanwhile :meth:`get_param_revision` is
        UNCACHED and reads the fresh ``updated_at`` — so the projected row's ``version``
        advances while its CONTENT lags: the version/content desync (the "wedge").

        This seam lets the sync start each run from a coherent (non-stale) source: before
        building a tenant's ``config#*`` rows it drops this service's cached ``members.*``
        values for that tenant, so the builders re-read the CURRENT value and the built
        content always matches the (equally current) version. READ-ONLY cache maintenance —
        no MySQL I/O — so the sync's one-directional guarantee is untouched.

        Args:
            namespace: The parameter namespace to evict (e.g. ``"members"``).
            tenant: When given, evict only that tenant's cached values in the
                namespace (the ``("tenant", tenant, namespace, …)`` cache keys);
                when ``None``, evict every scope's entries in the namespace.
        """
        keys_to_remove = [
            k
            for k in self._cache
            if k[2] == namespace and (tenant is None or (k[0] == "tenant" and k[1] == tenant))
        ]
        for k in keys_to_remove:
            del self._cache[k]

    def _invalidate_cache(self, namespace: str, key: str) -> None:
        """Remove all cache entries matching this namespace+key across all scopes."""
        keys_to_remove = [k for k in self._cache if k[2] == namespace and k[3] == key]
        for k in keys_to_remove:
            del self._cache[k]

    def _resolve_revision_from_db(
        self, scope: str, scope_id: str, namespace: str, key: str
    ) -> Any:
        """Return the ``updated_at`` of a specific scope+key row, or ``None`` if absent.

        READ-ONLY (a single parameterized SELECT, no write) — mirrors
        :meth:`_resolve_from_db` but reads the per-row freshness column
        (``updated_at``, the table's ``ON UPDATE CURRENT_TIMESTAMP``) rather than the
        value. Used by :meth:`get_param_revision` to supply the per-parameter version
        the governance projection needs. Not cached: it backs a projection sync run
        that must observe the latest edit, and the value cache would otherwise mask a
        fresh ``updated_at`` after a save.
        """
        query = """
            SELECT updated_at FROM parameters
            WHERE scope = %s AND scope_id = %s AND namespace = %s AND `key` = %s
            LIMIT 1
        """
        rows = self.db.execute_query(
            query, (scope, scope_id, namespace, key), fetch=True
        )
        if not rows:
            return None
        return rows[0].get("updated_at")

    def _resolve_from_db(
        self, scope: str, scope_id: str, namespace: str, key: str
    ) -> Any:
        """Query the parameters table for a specific scope+key combination."""
        query = """
            SELECT value, is_secret FROM parameters
            WHERE scope = %s AND scope_id = %s AND namespace = %s AND `key` = %s
            LIMIT 1
        """
        rows = self.db.execute_query(
            query, (scope, scope_id, namespace, key), fetch=True
        )
        if not rows:
            return None

        row = rows[0]
        parsed = self._parse_json_value(row["value"])

        if row["is_secret"] and self.credential_service:
            try:
                parsed = self.credential_service.decrypt_credential(parsed)
            except Exception:
                logger.warning(
                    "Failed to decrypt secret param %s.%s at scope %s",
                    namespace,
                    key,
                    scope,
                )

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
        if value_type == "string" and not isinstance(value, str):
            raise ValueError(f"Expected string value, got {type(value).__name__}")
        elif value_type == "number" and not isinstance(value, (int, float)):
            raise ValueError(f"Expected number value, got {type(value).__name__}")
        elif value_type == "boolean" and not isinstance(value, bool):
            raise ValueError(f"Expected boolean value, got {type(value).__name__}")
        elif value_type == "json" and not isinstance(value, (dict, list)):
            raise ValueError(
                f"Expected json value (dict or list), got {type(value).__name__}"
            )
