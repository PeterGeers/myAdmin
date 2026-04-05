---
inclusion: auto
---

# API Conventions

## URL Patterns

- Base: `/api/{module}/{action}` (e.g., `/api/banking/scan-files`)
- Use kebab-case for URL segments
- Group by module: `banking`, `str`, `tax`, `invoices`, `admin`, `sysadmin`

## Blueprints

- Each module has its own Blueprint: `{module}_bp = Blueprint('{module}', __name__)`
- Blueprints registered in `app.py`
- Service instances initialized via `set_test_mode()` pattern

## Authentication

Two decorators, always in this order:

```python
@route_bp.route('/api/module/action', methods=['GET'])
@cognito_required(required_permissions=['module_read'])
@tenant_required()
def action_name(user_email, user_roles, tenant, user_tenants):
```

- `@cognito_required(required_permissions=[...])` — JWT validation, injects `user_email`, `user_roles`
- `@tenant_required()` — tenant isolation, injects `tenant`, `user_tenants`
- Sysadmin routes: `@tenant_required(allow_sysadmin=True)`
- Some routes skip `@tenant_required()` if tenant-agnostic

## Permissions

Format: `{module}_{action}` — e.g., `banking_read`, `banking_process`, `str_write`, `admin_manage`

## Response Format

Success:

```python
return jsonify({'success': True, 'data': result}), 200
```

Error:

```python
return jsonify({'success': False, 'error': str(e)}), 500
```

Access denied:

```python
return jsonify({'success': False, 'error': 'Access denied'}), 403
```

## Error Handling

Every route wraps logic in try/except:

```python
try:
    result = service.do_something(tenant, ...)
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400
except Exception as e:
    print(f"Module action error: {e}", flush=True)
    return jsonify({'success': False, 'error': str(e)}), 500
```

## Service Layer

- Routes delegate to service classes, never contain business logic directly
- Services instantiated with `test_mode` flag
- Pattern: `result = service.method(tenant, ...params)`

## Request Data

- GET params: `request.args.get('param', default)`
- POST/PUT body: `request.get_json()`
- Always validate required fields before processing
