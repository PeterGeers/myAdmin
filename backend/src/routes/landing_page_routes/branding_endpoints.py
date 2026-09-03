"""Branding / SEO / social settings endpoints for the landing page.

Handlers resolve shared helpers through the ``routes.landing_page_routes``
package namespace at call time so the test suite's
``patch('routes.landing_page_routes.<name>')`` calls keep working.
"""

import logging

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from routes import landing_page_routes as pkg

logger = logging.getLogger(__name__)

landing_page_bp = pkg.landing_page_bp

# All landing page settings keys stored in ParameterService (landing_page namespace)
BRANDING_KEYS = [
    "company_name",
    "tagline",
    "logo_url",
    "color_primary",
    "color_accent",
    "address",
    "postal_city",
    "country",
    "phone",
    "email",
    "coc",
    "vat",
    "font_heading",
    "font_body",
    "base_spacing",
    "border_radius_global",
    "shadow_style",
]
SEO_KEYS = ["seo_title", "seo_description", "og_image_url"]
SETTINGS_KEYS = ["social_links", "show_share_buttons"]


@landing_page_bp.route("/api/landing/branding", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def get_branding_settings(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Get all landing page settings (branding, social links, SEO).

    Returns all ParameterService values from the landing_page namespace
    that are relevant for branding, footer, social, and SEO configuration.

    Authorization: Tenant_Admin role required
    """
    try:
        import json as json_module

        param_svc = pkg._get_parameter_service()
        result = {}

        # Load branding fields
        for key in BRANDING_KEYS:
            result[key] = param_svc.get_param("landing_page", key, tenant=tenant) or ""

        # Load SEO fields
        for key in SEO_KEYS:
            result[key] = param_svc.get_param("landing_page", key, tenant=tenant) or ""

        # Load social_links (stored as JSON string)
        social_raw = param_svc.get_param("landing_page", "social_links", tenant=tenant)
        if social_raw:
            if isinstance(social_raw, str):
                try:
                    result["social_links"] = json_module.loads(social_raw)
                except (json_module.JSONDecodeError, TypeError):
                    result["social_links"] = {}
            elif isinstance(social_raw, dict):
                result["social_links"] = social_raw
            else:
                result["social_links"] = {}
        else:
            result["social_links"] = {}

        # Load show_share_buttons
        show_share = param_svc.get_param(
            "landing_page", "show_share_buttons", tenant=tenant
        )
        result["show_share_buttons"] = show_share in ("true", "True", True)

        # Load theme (preset + overrides)
        theme_raw = param_svc.get_param("landing_page", "theme", tenant=tenant)
        if theme_raw:
            if isinstance(theme_raw, str):
                try:
                    result["theme"] = json_module.loads(theme_raw)
                except (json_module.JSONDecodeError, TypeError):
                    result["theme"] = {"preset": None, "overrides": {}}
            elif isinstance(theme_raw, dict):
                result["theme"] = theme_raw
            else:
                result["theme"] = {"preset": None, "overrides": {}}
        else:
            result["theme"] = {"preset": None, "overrides": {}}

        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Error loading branding settings for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@landing_page_bp.route("/api/landing/branding", methods=["PUT"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def save_branding_settings(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Save all landing page settings (branding, social links, SEO).

    Accepts a flat JSON body with branding, SEO, and social fields.
    Saves each field individually to ParameterService (landing_page namespace, tenant scope).

    Authorization: Tenant_Admin role required
    """
    try:
        import json as json_module

        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        param_svc = pkg._get_parameter_service()

        # Save branding fields (string values)
        for key in BRANDING_KEYS:
            if key in data:
                value = data[key] if data[key] is not None else ""
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key=key,
                    value=str(value),
                    value_type="string",
                    created_by=user_email,
                )

        # Save SEO fields (string values)
        for key in SEO_KEYS:
            if key in data:
                value = data[key] if data[key] is not None else ""
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key=key,
                    value=str(value),
                    value_type="string",
                    created_by=user_email,
                )

        # Save social_links as JSON string
        if "social_links" in data:
            social = data["social_links"]
            if isinstance(social, dict):
                # Filter out empty values
                social_clean = {k: v for k, v in social.items() if v}
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key="social_links",
                    value=json_module.dumps(social_clean),
                    value_type="string",
                    created_by=user_email,
                )

        # Save show_share_buttons
        if "show_share_buttons" in data:
            param_svc.set_param(
                scope="tenant",
                scope_id=tenant,
                namespace="landing_page",
                key="show_share_buttons",
                value="true" if data["show_share_buttons"] else "false",
                value_type="string",
                created_by=user_email,
            )

        # Save theme selection (preset + overrides)
        if "theme" in data:
            theme = data["theme"]
            if isinstance(theme, dict):
                theme_value = json_module.dumps(
                    {
                        "preset": theme.get("preset"),
                        "overrides": theme.get("overrides", {}),
                    }
                )
                param_svc.set_param(
                    scope="tenant",
                    scope_id=tenant,
                    namespace="landing_page",
                    key="theme",
                    value=theme_value,
                    value_type="string",
                    created_by=user_email,
                )

        logger.info(f"Branding settings saved for tenant {tenant} by {user_email}")
        return jsonify({"success": True, "message": "Settings saved successfully"})

    except Exception as e:
        logger.error(f"Error saving branding settings for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
