 ---
inclusion: fileMatch
fileMatchPattern: "backend/src/routes/**/*.py,backend/src/services/**/*.py"
---

# API Conventions (Flask plane)

> **Scope: the Flask / MySQL plane only** (`backend/src/routes` + `backend/src/services`).
> These conventions — Blueprints, `@cognito_required` / `@tenant_required`, `jsonify`,
> the service layer — do **not** apply to the SAM-backed module plane. For SAM modules
> (API Gateway → Lambda handler → domain service → repository → DynamoDB, with the
> `sam/shared` verified-JWT + entitlement toolkit at the edge), see
> `35-sam-module-architecture-sam.md`. Tenant key here is `administration`; on the module
> plane it is `tenant_id`.

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

Error (never return `str(e)` to the client — it leaks internal detail, CodeQL
`py/stack-trace-exposure`). Log the full exception server-side (with stack) and return a
**generic** message plus a correlation `error_id` the user can quote in a support request:

```python
from routes.error_responses import error_response

except Exception as e:
    return error_response(e, "Module action failed", status=500)
    # -> ({'success': False, 'error': 'Module action failed', 'error_id': '<uuid>'}, 500)
    #    full exception + stack logged server-side, keyed by the same error_id
```

Validation / business errors you raise deliberately (not caught exceptions) keep their
explicit, caller-safe message — only the `except Exception` path must stop echoing `str(e)`:

```python
return jsonify({'success': False, 'error': 'amountGross is required'}), 400
```

Access denied:

```python
return jsonify({'success': False, 'error': 'Access denied'}), 403
```

## Error Handling

Every route wraps logic in try/except. On the caught-exception path, delegate to
`error_response` — it logs the full exception (with stack) server-side under a generated
`error_id` and returns the generic client body + the same status code. Never put `str(e)`
in the client response:

```python
from routes.error_responses import error_response

try:
    result = service.do_something(tenant, ...)
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400
except Exception as e:
    return error_response(e, "Module action failed", status=500)
```

- Response shape stays `{'success': False, 'error': <generic msg>, 'error_id': <uuid>}` and
  the HTTP status is unchanged from the old convention (500 for unexpected errors).
- The `error_id` ties the client-visible failure to the full server-side log line for triage
  without exposing internals.
- For routes that historically returned the bare `{'error': str(e)}` shape (no `success`
  key — e.g. the sysadmin role endpoints), pass `include_success=False` to
  `error_response` so the response stays `{'error': <generic msg>, 'error_id': <uuid>}`.

## Service Layer

- Routes delegate to service classes, never contain business logic directly
- Services instantiated with `test_mode` flag
- Pattern: `result = service.method(tenant, ...params)`

## Request Data

- GET params: `request.args.get('param', default)`
- POST/PUT body: `request.get_json()`
- Always validate required fields before processing

## Change-With-Tests Contract (product code ⇄ allocated tests)

**When you change behavior in a route/service, update its allocated test(s) in the SAME change.** A behavioral edit that leaves the paired test asserting the old behavior is incomplete — it passes locally by luck and breaks the nightly Full Test Suite days later (this is the single most common recurring CI failure; see `.kiro/specs/code-quality-maintenance/`).

Applies to any observable change: output/return shape, parsed values, an import/export FILE FORMAT (e.g. the Airbnb CSV parser), an API response contract, an error/abort path, or a fixture/sample file the tests read.

Required steps for every behavior change:
1. **Find the allocated test(s).** Naming: `src/services/foo.py` → `tests/unit/test_foo*.py`; `src/routes/foo.py` → `tests/**/test_foo*.py`. Also grep the test tree for the changed symbol / format / field name — a change often has *property* tests (`*_props.py`), *preservation* tests, and `*-bug` tests that encode intended behavior.
2. **Update the test AND any committed fixtures/samples** to the intended new behavior, in the same change. Never point a test at a git-ignored scratch file (e.g. `.agent-output/`) — commit fixtures under `backend/tests/fixtures/`.
3. **Do not weaken or delete assertions to go green.** Align them with the deliberate new behavior. If two tests now contradict each other (one asserts old, one asserts new), STOP and surface the conflict — do not pick a side silently.
4. **Run the paired test(s)** before considering the change done: `python -m pytest <paths> -q`.

The `test-sync-on-source-change` hook (`.kiro/hooks/`) reminds you of this on every product-file save; the rule here is the source of truth even when the hook does not fire.
