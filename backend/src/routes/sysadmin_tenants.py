"""
SysAdmin Tenant Management Endpoints

API endpoints for managing tenants (create, list, get, update, delete)
Also includes module management endpoints nested under tenants
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from database import DatabaseManager
from .sysadmin_helpers import (
    get_tenant_user_count,
    get_tenant_users,
    validate_administration_name
)
import os
import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
sysadmin_tenants_bp = Blueprint('sysadmin_tenants', __name__)


@sysadmin_tenants_bp.route('', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def create_tenant(user_email, user_roles):
    """
    Create new tenant
    
    Authorization: SysAdmin role required
    
    Request body:
    {
        "administration": "NewCorp",
        "display_name": "New Corporation",
        "contact_email": "admin@newcorp.com",
        "phone_number": "+31123456789",
        "street": "Main Street 123",
        "city": "Amsterdam",
        "zipcode": "1012AB",
        "country": "Netherlands",
        "enabled_modules": ["FIN", "STR"],
        "initial_admin_email": "john@newcorp.com"  # Optional
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['administration', 'display_name', 'contact_email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        administration = data['administration']
        
        # Validate administration name format
        is_valid, error_msg = validate_administration_name(administration)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Check if tenant already exists
        existing = db.execute_query(
            "SELECT administration FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True
        )
        
        if existing:
            return jsonify({'error': f'Tenant {administration} already exists'}), 400
        
        # Insert tenant
        insert_query = """
            INSERT INTO tenants (
                administration, display_name, status, contact_email, phone_number,
                address_street, address_city, address_zipcode, address_country,
                created_at, updated_at, updated_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
        """
        
        db.execute_query(
            insert_query,
            (
                administration,
                data['display_name'],
                'active',
                data['contact_email'],
                data.get('phone_number'),
                data.get('street'),
                data.get('city'),
                data.get('zipcode'),
                data.get('country', 'Netherlands'),
                user_email
            ),
            commit=True
        )
        
        # Insert enabled modules
        enabled_modules = data.get('enabled_modules', [])
        if enabled_modules:
            for module in enabled_modules:
                db.execute_query(
                    """
                    INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
                    VALUES (%s, %s, TRUE, NOW())
                    """,
                    (administration, module),
                    commit=True
                )
        
        # Add TENADMIN module (all tenants have this)
        db.execute_query(
            """
            INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
            VALUES (%s, 'TENADMIN', TRUE, NOW())
            """,
            (administration,),
            commit=True
        )
        
        logger.info(f"Tenant {administration} created by {user_email}")
        
        return jsonify({
            'success': True,
            'administration': administration,
            'display_name': data['display_name'],
            'status': 'active',
            'message': f'Tenant {administration} created successfully'
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating tenant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sysadmin_tenants_bp.route('', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def list_tenants(user_email, user_roles):
    """
    List all tenants with filtering, pagination, and sorting
    
    Authorization: SysAdmin role required
    
    Query parameters:
    - page: int (default 1)
    - per_page: int (default 50, max 100)
    - status: string (active|suspended|inactive|deleted|all, default all)
    - sort_by: string (administration|display_name|created_at|status, default created_at)
    - sort_order: string (asc|desc, default desc)
    - search: string (search in administration, display_name, contact_email)
    """
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 100)
        status_filter = request.args.get('status', 'all')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc').upper()
        search = request.args.get('search', '').strip()
        
        # Validate sort_by
        valid_sort_fields = ['administration', 'display_name', 'created_at', 'status']
        if sort_by not in valid_sort_fields:
            sort_by = 'created_at'
        
        # Validate sort_order
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Build query
        where_clauses = []
        params = []
        
        # Status filter
        if status_filter != 'all':
            where_clauses.append("t.status = %s")
            params.append(status_filter)
        
        # Search filter
        if search:
            where_clauses.append(
                "(t.administration LIKE %s OR t.display_name LIKE %s OR t.contact_email LIKE %s)"
            )
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Count total
        count_query = f"SELECT COUNT(*) as total FROM tenants t WHERE {where_clause}"
        count_result = db.execute_query(count_query, tuple(params), fetch=True)
        total = count_result[0]['total'] if count_result else 0
        
        # Get tenants
        offset = (page - 1) * per_page
        query = f"""
            SELECT 
                t.administration,
                t.display_name,
                t.status,
                t.contact_email,
                t.phone_number,
                t.address_street as street,
                t.address_city as city,
                t.address_zipcode as zipcode,
                t.address_country as country,
                t.created_at,
                t.updated_at
            FROM tenants t
            WHERE {where_clause}
            ORDER BY t.{sort_by} {sort_order}
            LIMIT %s OFFSET %s
        """
        
        params.extend([per_page, offset])
        tenants = db.execute_query(query, tuple(params), fetch=True)
        
        # Get enabled modules for each tenant
        for tenant in tenants:
            modules_query = """
                SELECT module_name 
                FROM tenant_modules 
                WHERE administration = %s AND is_active = TRUE
            """
            modules = db.execute_query(
                modules_query,
                (tenant['administration'],),
                fetch=True
            )
            tenant['enabled_modules'] = [m['module_name'] for m in modules]
            
            # Get user count (this is expensive, consider caching)
            tenant['user_count'] = get_tenant_user_count(tenant['administration'])
            
            # Format dates
            if tenant.get('created_at'):
                tenant['created_at'] = tenant['created_at'].isoformat()
            if tenant.get('updated_at'):
                tenant['updated_at'] = tenant['updated_at'].isoformat()
        
        return jsonify({
            'success': True,
            'tenants': tenants,
            'total': total,
            'page': page,
            'per_page': per_page
        })
        
    except Exception as e:
        logger.error(f"Error listing tenants: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sysadmin_tenants_bp.route('/<administration>', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_tenant(user_email, user_roles, administration):
    """
    Get single tenant details
    
    Authorization: SysAdmin role required
    """
    try:
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Get tenant
        query = """
            SELECT 
                administration,
                display_name,
                status,
                contact_email,
                phone_number,
                address_street as street,
                address_city as city,
                address_zipcode as zipcode,
                address_country as country,
                created_at,
                updated_at,
                updated_by
            FROM tenants
            WHERE administration = %s
        """
        
        result = db.execute_query(query, (administration,), fetch=True)
        
        if not result:
            return jsonify({'error': f'Tenant {administration} not found'}), 404
        
        tenant = result[0]
        
        # Get enabled modules
        modules_query = """
            SELECT module_name 
            FROM tenant_modules 
            WHERE administration = %s AND is_active = TRUE
        """
        modules = db.execute_query(modules_query, (administration,), fetch=True)
        tenant['enabled_modules'] = [m['module_name'] for m in modules]
        
        # Get users
        tenant['users'] = get_tenant_users(administration)
        tenant['user_count'] = len(tenant['users'])
        
        # Format dates
        if tenant.get('created_at'):
            tenant['created_at'] = tenant['created_at'].isoformat()
        if tenant.get('updated_at'):
            tenant['updated_at'] = tenant['updated_at'].isoformat()
        
        return jsonify({
            'success': True,
            'tenant': tenant
        })
        
    except Exception as e:
        logger.error(f"Error getting tenant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sysadmin_tenants_bp.route('/<administration>', methods=['PUT'])
@cognito_required(required_roles=['SysAdmin'])
def update_tenant(user_email, user_roles, administration):
    """
    Update tenant details
    
    Authorization: SysAdmin role required
    
    Request body:
    {
        "display_name": "Updated Name",
        "status": "active",
        "contact_email": "new@email.com",
        "phone_number": "+31123456789",
        "street": "New Street 456",
        "city": "Rotterdam",
        "zipcode": "3000AB",
        "country": "Netherlands"
    }
    
    Note: administration field cannot be updated (immutable)
    """
    try:
        data = request.get_json()
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Check if tenant exists
        existing = db.execute_query(
            "SELECT administration FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True
        )
        
        if not existing:
            return jsonify({'error': f'Tenant {administration} not found'}), 404
        
        # Build update query dynamically based on provided fields
        update_fields = []
        params = []
        
        allowed_fields = {
            'display_name': 'display_name',
            'status': 'status',
            'contact_email': 'contact_email',
            'phone_number': 'phone_number',
            'street': 'address_street',
            'city': 'address_city',
            'zipcode': 'address_zipcode',
            'country': 'address_country'
        }
        
        for field, db_field in allowed_fields.items():
            if field in data:
                update_fields.append(f"{db_field} = %s")
                params.append(data[field])
        
        if not update_fields:
            return jsonify({'error': 'No fields to update'}), 400
        
        # Validate status if provided
        if 'status' in data:
            valid_statuses = ['active', 'suspended', 'inactive', 'deleted']
            if data['status'] not in valid_statuses:
                return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        # Add updated_at and updated_by
        update_fields.append("updated_at = NOW()")
        update_fields.append("updated_by = %s")
        params.append(user_email)
        
        # Add administration to params (for WHERE clause)
        params.append(administration)
        
        # Execute update
        update_query = f"""
            UPDATE tenants 
            SET {', '.join(update_fields)}
            WHERE administration = %s
        """
        
        db.execute_query(update_query, tuple(params), commit=True)
        
        logger.info(f"Tenant {administration} updated by {user_email}")
        
        return jsonify({
            'success': True,
            'administration': administration,
            'message': f'Tenant {administration} updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating tenant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sysadmin_tenants_bp.route('/<administration>', methods=['DELETE'])
@cognito_required(required_roles=['SysAdmin'])
def delete_tenant(user_email, user_roles, administration):
    """
    Soft delete tenant (set status to 'deleted')
    
    Authorization: SysAdmin role required
    
    Note: This is a soft delete. The tenant record remains in the database
    but is marked as deleted. Active users will prevent deletion.
    """
    try:
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Check if tenant exists
        existing = db.execute_query(
            "SELECT administration, status FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True
        )
        
        if not existing:
            return jsonify({'error': f'Tenant {administration} not found'}), 404
        
        # Check for active users
        user_count = get_tenant_user_count(administration)
        if user_count > 0:
            return jsonify({
                'error': f'Cannot delete tenant with active users. Found {user_count} user(s). Please remove users first.'
            }), 409
        
        # Soft delete (set status to deleted)
        db.execute_query(
            """
            UPDATE tenants 
            SET status = 'deleted', updated_at = NOW(), updated_by = %s
            WHERE administration = %s
            """,
            (user_email, administration),
            commit=True
        )
        
        logger.info(f"Tenant {administration} deleted by {user_email}")
        
        return jsonify({
            'success': True,
            'administration': administration,
            'message': f'Tenant {administration} deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting tenant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Module Management Endpoints (nested under tenants)
# ============================================================================


@sysadmin_tenants_bp.route('/<administration>/modules', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_tenant_modules(user_email, user_roles, administration):
    """
    Get enabled modules for a tenant
    
    Authorization: SysAdmin role required
    """
    try:
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Check if tenant exists
        existing = db.execute_query(
            "SELECT administration FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True
        )
        
        if not existing:
            return jsonify({'error': f'Tenant {administration} not found'}), 404
        
        # Get all modules
        query = """
            SELECT module_name, is_active, created_at, updated_at
            FROM tenant_modules
            WHERE administration = %s
            ORDER BY module_name
        """
        
        modules = db.execute_query(query, (administration,), fetch=True)
        
        # Format dates
        for module in modules:
            if module.get('created_at'):
                module['created_at'] = module['created_at'].isoformat()
            if module.get('updated_at'):
                module['updated_at'] = module['updated_at'].isoformat()
        
        return jsonify({
            'success': True,
            'administration': administration,
            'modules': modules
        })
        
    except Exception as e:
        logger.error(f"Error getting tenant modules: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sysadmin_tenants_bp.route('/<administration>/modules', methods=['PUT'])
@cognito_required(required_roles=['SysAdmin'])
def update_tenant_modules(user_email, user_roles, administration):
    """
    Update enabled modules for a tenant
    
    Authorization: SysAdmin role required
    
    Request body:
    {
        "modules": [
            {"name": "FIN", "is_active": true},
            {"name": "STR", "is_active": false}
        ]
    }
    
    Note: This does NOT remove users from module groups. 
    Tenant_Admin must manage user group assignments separately.
    """
    try:
        data = request.get_json()
        
        if not data.get('modules'):
            return jsonify({'error': 'Missing required field: modules'}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Check if tenant exists
        existing = db.execute_query(
            "SELECT administration FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True
        )
        
        if not existing:
            return jsonify({'error': f'Tenant {administration} not found'}), 404
        
        # Update each module
        for module in data['modules']:
            module_name = module.get('name')
            is_active = module.get('is_active', True)
            
            if not module_name:
                continue
            
            # Check if module exists
            existing_module = db.execute_query(
                """
                SELECT id FROM tenant_modules 
                WHERE administration = %s AND module_name = %s
                """,
                (administration, module_name),
                fetch=True
            )
            
            if existing_module:
                # Update existing module
                db.execute_query(
                    """
                    UPDATE tenant_modules 
                    SET is_active = %s, updated_at = NOW()
                    WHERE administration = %s AND module_name = %s
                    """,
                    (is_active, administration, module_name),
                    commit=True
                )
            else:
                # Insert new module
                db.execute_query(
                    """
                    INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (administration, module_name, is_active),
                    commit=True
                )
        
        logger.info(f"Modules updated for tenant {administration} by {user_email}")
        
        return jsonify({
            'success': True,
            'administration': administration,
            'message': f'Modules updated for tenant {administration}'
        })
        
    except Exception as e:
        logger.error(f"Error updating tenant modules: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
