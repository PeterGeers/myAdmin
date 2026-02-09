"""
SysAdmin Routes for myAdmin

Main blueprint that combines all SysAdmin endpoints:
- Tenant management (create, list, get, update, delete)
- Role management (list, create, delete Cognito groups)
- Module management (enable/disable modules for tenants)

Based on the architecture at .kiro/specs/Common/SysAdmin-Module/design.md

File Structure:
- sysadmin_routes.py (this file) - Main blueprint registration
- sysadmin_helpers.py - Shared helper functions
- sysadmin_tenants.py - Tenant CRUD + module management endpoints
- sysadmin_roles.py - Role management endpoints
"""

from flask import Blueprint
from .sysadmin_tenants import sysadmin_tenants_bp
from .sysadmin_roles import sysadmin_roles_bp

# Create main blueprint for sysadmin routes
sysadmin_bp = Blueprint('sysadmin', __name__, url_prefix='/api/sysadmin')

# Register sub-blueprints
# Tenant routes: /api/sysadmin/tenants (includes module management)
sysadmin_bp.register_blueprint(sysadmin_tenants_bp, url_prefix='/tenants')

# Role routes: /api/sysadmin/roles
sysadmin_bp.register_blueprint(sysadmin_roles_bp, url_prefix='/roles')
