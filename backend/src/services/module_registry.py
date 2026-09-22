"""
ModuleRegistry: In-code Python dictionary defining required parameters,
tax rates, and roles per module.

Provides has_module() to check if a tenant has a module enabled, and
module_required() decorator to enforce module access on Flask routes.

Module descriptor schema
-------------------------
Each MODULE_REGISTRY entry describes one module. All of the following keys apply
identically regardless of how the module is backed:

    description            human-readable label (string)
    depends_on             list of module names that must be active first (optional)
    required_params        dict of parameter name -> {type, default}
    required_tax_rates     list of tax-rate keys the module needs
    required_roles         list of Cognito role names granting access

Backing (optional)
------------------
An entry MAY carry an optional ``backing`` block describing where the module's
logic runs. When ``backing`` is absent the module is an in-process Flask module
(today's behavior) — this is why FIN/ZZP/STR/TENADMIN carry no ``backing`` key.

    backing.kind            "flask" (default when omitted) or "sam"
    backing.api_base_env    (sam only) NAME of the env var that yields the
                            module's API base URL. The registry never stores a
                            URL, only the env var name.
    backing.data_namespace  (sam only, optional) DynamoDB table prefix/namespace
                            the module owns.

Example of a SAM-backed entry::

    "EXAMPLE": {
        "description": "Example SAM-backed module",
        "required_params": {},
        "required_tax_rates": [],
        "required_roles": ["Example_Read"],
        "backing": {
            "kind": "sam",
            "api_base_env": "EXAMPLE_MODULE_API_BASE",
            "data_namespace": "example",  # optional
        },
    }

Entitlement (has_module / module_required / activate_module / provisioning) is
identical for both kinds; only the backing block differs.

Requirements: 4.1, 4.4, 4.5, 4.6, 1.1, 4.1 (S1 backing kind)
Reference: .kiro/specs/parameter-driven-config/design.md
Reference: .kiro/specs/multi-tenant/s1-prepare-platform/design.md
"""

import functools
import logging
import os

# NOTE: `flask` is imported LAZILY inside the two functions that use it
# (`module_required` / `activate_module` -> both use `jsonify` only on the Flask
# request path). Keeping it off the module top level lets non-Flask carriers
# import `MODULE_REGISTRY` (the pure in-code descriptor dict) WITHOUT pulling the
# whole Flask/Werkzeug/Jinja2 tree onto their runtime. In particular the S4
# Pre-Token-Generation Lambda (`sam/pretokengen/handler.py`) does
# `from services.module_registry import MODULE_REGISTRY`; vendoring Flask into
# that latency-sensitive (~5s Cognito budget) layer purely for an unused
# `jsonify` would be dead weight. The Flask plane is unaffected — the import just
# moves into the function bodies that actually call `jsonify`.

logger = logging.getLogger(__name__)

MODULE_REGISTRY: dict[str, dict] = {
    "FIN": {
        "description": "Financial Administration",
        "required_params": {
            "fin.default_currency": {"type": "string", "default": "EUR"},
            "fin.fiscal_year_start_month": {"type": "number", "default": 1},
            "fin.locale": {"type": "string", "default": "nl"},
        },
        "required_tax_rates": ["btw"],
        "required_roles": ["Finance_CRUD", "Finance_Read", "Finance_Export"],
    },
    "STR": {
        "description": "Short-Term Rental Management",
        "required_params": {
            "str.aantal_kamers": {"type": "number", "default": None},
            "str.aantal_slaapplaatsen": {"type": "number", "default": None},
            "str.platforms": {"type": "json", "default": ["airbnb", "booking"]},
        },
        "required_tax_rates": ["tourist_tax", "btw_accommodation"],
        "required_roles": ["STR_CRUD", "STR_Read", "STR_Export"],
    },
    "TENADMIN": {
        "description": "Tenant Administration",
        "required_params": {},
        "required_tax_rates": [],
        "required_roles": ["Tenant_Admin"],
    },
    "ZZP": {
        "description": "ZZP Freelancer Administration",
        "depends_on": ["FIN"],
        "required_params": {
            "zzp.invoice_prefix": {"type": "string", "default": "INV"},
            "zzp.credit_note_prefix": {"type": "string", "default": "CN"},
            "zzp.default_payment_terms_days": {"type": "number", "default": 30},
            "zzp.default_currency": {"type": "string", "default": "EUR"},
            "zzp.invoice_number_padding": {"type": "number", "default": 4},
            "zzp.debtor_account": {"type": "string", "default": "1600"},
            "zzp.creditor_account": {"type": "string", "default": "1300"},
            "zzp.email_subject_template": {
                "type": "string",
                "default": "Factuur {invoice_number} - {company_name}",
            },
            "zzp.invoice_email_bcc": {"type": "string", "default": ""},
            "zzp.retention_years": {"type": "number", "default": 7},
            "zzp.time_tracking_enabled": {"type": "boolean", "default": True},
            "zzp.product_types": {
                "type": "json",
                "default": ["service", "product", "hours", "subscription"],
            },
            "zzp.contact_types": {
                "type": "json",
                "default": ["client", "supplier", "both", "other"],
            },
            "zzp.contact_field_config": {
                "type": "json",
                "default": {
                    "client_id": "required",
                    "contact_type": "required",
                    "company_name": "required",
                    "contact_person": "optional",
                    "street_address": "optional",
                    "postal_code": "optional",
                    "city": "optional",
                    "country": "optional",
                    "vat_number": "optional",
                    "kvk_number": "optional",
                    "phone": "optional",
                    "iban": "optional",
                    "emails": "optional",
                },
            },
            "zzp.product_field_config": {
                "type": "json",
                "default": {
                    "product_code": "required",
                    "name": "required",
                    "product_type": "required",
                    "unit_price": "required",
                    "vat_code": "required",
                    "description": "optional",
                    "unit_of_measure": "optional",
                    "external_reference": "optional",
                },
            },
            "zzp.invoice_field_config": {
                "type": "json",
                "default": {
                    "contact_id": "required",
                    "invoice_date": "required",
                    "payment_terms_days": "required",
                    "currency": "optional",
                    "exchange_rate": "hidden",
                    "notes": "optional",
                },
            },
            "zzp.time_entry_field_config": {
                "type": "json",
                "default": {
                    "contact_id": "required",
                    "entry_date": "required",
                    "hours": "required",
                    "hourly_rate": "required",
                    "product_id": "optional",
                    "project_name": "optional",
                    "description": "optional",
                    "is_billable": "optional",
                },
            },
            # Rittenregistratie parameters (namespace: zzp_ritten)
            "zzp_ritten.max_route_presets": {
                "type": "number",
                "default": 10,
            },
            "zzp_ritten.bijtelling_warning_threshold": {
                "type": "number",
                "default": 400,
            },
            "zzp_ritten.bijtelling_limit": {
                "type": "number",
                "default": 500,
            },
            "zzp_ritten.large_distance_warning": {
                "type": "number",
                "default": 300,
            },
            "zzp_ritten.default_km_rate": {
                "type": "number",
                "default": 0.23,
            },
            "zzp_ritten.trip_categories": {
                "type": "json",
                "default": ["Zakelijk", "Privé", "Woon-werk"],
            },
            "zzp_ritten.trip_purposes": {
                "type": "json",
                "default": [
                    "Klantbezoek",
                    "Vergadering",
                    "Materiaal ophalen",
                    "Overig",
                ],
            },
        },
        "required_tax_rates": ["btw"],
        "required_roles": ["ZZP_CRUD", "ZZP_Read", "ZZP_Export"],
    },
    "MEMBERS": {
        "description": "Members / Membership Administration",
        "required_params": {},
        "required_tax_rates": [],
        # Generic, tenant-agnostic role set following the <Module>_<Action>
        # convention used by the other modules. Members_CRUD backs the
        # scope-requiring capability (design C4/C7: required_for: ["Members_CRUD"])
        # and covers member CRUD, membership lifecycle, delegates, member
        # payments, and the Lidmaatschap Beheer (membership-type) catalog.
        "required_roles": ["Members_CRUD", "Members_Read", "Members_Export"],
        "backing": {
            "kind": "sam",
            # env var NAME only — resolve_module_api_base reads it at call time.
            "api_base_env": "MEMBERS_MODULE_API_BASE",
            # DynamoDB namespace this module owns (tenant_id-partitioned tables).
            "data_namespace": "members",
        },
    },
}


def module_backing(module_name: str) -> str:
    """
    Return the backing kind for a module: "flask" or "sam".

    Read-only accessor over MODULE_REGISTRY. Call sites should use this instead
    of inspecting the descriptor's ``backing`` block directly, so the dict shape
    stays contained here and future backing kinds don't leak into callers.

    A module with no ``backing`` block, or a ``backing`` block without a ``kind``
    key, is an in-process Flask module and reports "flask" (the default). This is
    why FIN/ZZP/STR/TENADMIN — which carry no ``backing`` key — report "flask".

    Args:
        module_name: Registered module name (e.g. 'FIN', 'STR', 'TENADMIN').

    Returns:
        "flask" or "sam".

    Raises:
        ValueError: If the module is not in MODULE_REGISTRY.
    """
    module_def = MODULE_REGISTRY.get(module_name)
    if module_def is None:
        raise ValueError(f"Unknown module: {module_name}")

    return module_def.get("backing", {}).get("kind", "flask")


def module_backing_or_none(module_name: str) -> str | None:
    """Return a module's backing kind ("flask"/"sam"), or ``None`` if unregistered.

    Non-raising sibling of :func:`module_backing`. Where a call site is walking a
    set of module names it did not curate — e.g. the reconciliation backstop
    sweeping *every* tenant's ``tenant_modules`` rows, which may include legacy /
    unregistered names from other tenants — a single unknown name must not abort
    the whole pass. Such callers use this accessor and treat ``None`` (unknown) as
    "not one of our backings" rather than an error.

    Known modules resolve exactly as :func:`module_backing` does (no validation is
    weakened for a registered module); only an *unregistered* name degrades to
    ``None`` instead of raising ``ValueError``.

    Args:
        module_name: Any module name (registered or not).

    Returns:
        "flask" or "sam" for a registered module; ``None`` if the name is not in
        MODULE_REGISTRY.
    """
    if module_name not in MODULE_REGISTRY:
        return None
    return module_backing(module_name)


def resolve_module_api_base(module_name: str) -> str | None:
    """
    Resolve a SAM-backed module's API base URL from the environment.

    The registry never stores a URL — a ``sam`` module only records the NAME of
    the env var (``backing.api_base_env``) that yields its API base. This
    accessor reads that env var at call time.

    Resolution fails fast: if the named env var is unset or empty, this raises
    rather than falling back to any default URL (per the no-dangerous-fallbacks
    guardrail in design.md §1). A wrong or missing base URL must surface loudly.

    Flask modules have no API base on the module plane and return ``None``.

    Args:
        module_name: Registered module name (e.g. 'FIN', 'STR', 'TENADMIN').

    Returns:
        The resolved API base URL (str) for a ``sam`` module, or ``None`` for a
        ``flask`` module.

    Raises:
        ValueError: If the module is not in MODULE_REGISTRY (via module_backing),
            if a ``sam`` module has no ``api_base_env`` configured, or if the
            named env var is unset/empty.
    """
    # module_backing validates the module name and contains the dict-shape logic.
    if module_backing(module_name) != "sam":
        return None

    backing = MODULE_REGISTRY[module_name].get("backing", {})
    env_var_name = backing.get("api_base_env")
    if not env_var_name:
        raise ValueError(
            f"SAM module '{module_name}' has no 'api_base_env' configured; "
            "cannot resolve its API base URL"
        )

    api_base = os.environ.get(env_var_name)
    if not api_base:
        raise ValueError(
            f"Environment variable '{env_var_name}' (API base for SAM module "
            f"'{module_name}') is unset or empty; refusing to fall back to a "
            "default URL"
        )

    return api_base


def has_module(db, tenant: str, module_name: str) -> bool:
    """
    Check if a tenant has a specific module enabled.
    Replaces the duplicated has_fin_module() function.

    Entitlement is backing-agnostic: this reads ``tenant_modules`` only and never
    inspects the descriptor's backing kind. A ``sam``-backed module is entitled
    exactly like an in-process ``flask`` one.

    Args:
        db: DatabaseManager instance
        tenant: The tenant administration name
        module_name: Module name (e.g. 'FIN', 'STR', 'TENADMIN')

    Returns:
        True if the module exists and is active for the tenant.
    """
    try:
        query = """
            SELECT is_active
            FROM tenant_modules
            WHERE administration = %s AND module_name = %s
        """
        result = db.execute_query(query, (tenant, module_name))
        return bool(result and result[0].get("is_active"))
    except Exception as e:
        logger.error(
            "Error checking module %s for tenant %s: %s", module_name, tenant, e
        )
        return False


def module_required(module_name: str):
    """
    Decorator that checks whether the current tenant has the specified module enabled.
    Returns HTTP 403 if the module is not active.

    Entitlement is backing-agnostic: the check delegates to has_module() and never
    inspects the module's backing kind, so a ``sam``-backed module is gated exactly
    like an in-process ``flask`` one.

    Must be used after @tenant_required() which injects 'tenant' into kwargs.

    Usage:
        @app.route('/api/fin/accounts')
        @cognito_required(required_permissions=[])
        @tenant_required()
        @module_required('FIN')
        def get_accounts(user_email, user_roles, tenant, user_tenants):
            ...
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Lazy Flask import: only the Flask request path needs `jsonify`, so
            # importing here (not at module top level) keeps `MODULE_REGISTRY`
            # importable by non-Flask carriers (e.g. the PreTokenGen Lambda).
            from flask import jsonify

            tenant = kwargs.get("tenant")
            if not tenant:
                return jsonify({"error": "Tenant context required"}), 403

            from database import DatabaseManager

            test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
            db = DatabaseManager(test_mode=test_mode)

            if not has_module(db, tenant, module_name):
                return jsonify(
                    {"error": f"{module_name} module not enabled for this tenant"}
                ), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def activate_module(
    db, tenant: str, module_name: str, activated_by: str = "system"
) -> bool:
    """
    Activate a module for a tenant, enforcing dependency checks.

    Checks that all modules listed in 'depends_on' are already active
    for the tenant before allowing activation.

    Entitlement is backing-agnostic: depends_on / required_roles handling and the
    ``tenant_modules`` insert never inspect the module's backing kind. Activating a
    ``sam``-backed module is identical to activating an in-process ``flask`` one.

    Args:
        db: DatabaseManager instance
        tenant: The tenant administration name
        module_name: Module name to activate (e.g. 'ZZP')
        activated_by: User or system identifier

    Returns:
        True if activation succeeded.

    Raises:
        ValueError: If module is unknown or dependencies are not met.
    """
    module_def = MODULE_REGISTRY.get(module_name)
    if not module_def:
        raise ValueError(f"Unknown module: {module_name}")

    for dep in module_def.get("depends_on", []):
        if not has_module(db, tenant, dep):
            raise ValueError(
                f"Module '{dep}' must be active before enabling '{module_name}'"
            )

    try:
        query = """
            INSERT INTO tenant_modules (administration, module_name, is_active, created_by)
            VALUES (%s, %s, TRUE, %s)
            ON DUPLICATE KEY UPDATE is_active = TRUE, updated_at = CURRENT_TIMESTAMP
        """
        db.execute_query(
            query, (tenant, module_name, activated_by), fetch=False, commit=True
        )
        logger.info(
            "Module %s activated for tenant %s by %s", module_name, tenant, activated_by
        )

        # Seed required parameters for the newly activated module
        from services.parameter_service import ParameterService

        param_service = ParameterService(db)
        params_seeded = param_service.seed_module_params(tenant, module_name)
        logger.info(
            "Seeded %d params for module %s on tenant %s",
            params_seeded,
            module_name,
            tenant,
        )

        # S3 R5.7 — on-change projection sync trigger. tenant_modules changed and
        # committed; signal a projection sync for the affected tenant.
        # Best-effort: never breaks module activation (reconciliation backstops).
        from services.projection_sync_trigger import enqueue_sync

        enqueue_sync(tenant)

        return True
    except Exception as e:
        logger.error(
            "Failed to activate module %s for tenant %s: %s", module_name, tenant, e
        )
        raise
