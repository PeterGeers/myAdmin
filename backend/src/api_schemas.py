from flask import jsonify
from functools import wraps
import jsonschema
from jsonschema import validate

# Standard API response format
def standard_response(data=None, success=True, error=None, status_code=200):
    """
    Standardized API response format
    """
    response = {
        'success': success,
        'data': data,
        'error': error,
        'status': 'success' if success else 'error'
    }

    # Remove None values
    response = {k: v for k, v in response.items() if v is not None}

    return jsonify(response), status_code

# API Schema definitions
API_SCHEMAS = {
    'upload_file': {
        'type': 'object',
        'properties': {
            'file': {'type': 'string', 'format': 'binary'},
            'folderName': {'type': 'string'}
        },
        'required': ['file']
    },
    'approve_transactions': {
        'type': 'object',
        'properties': {
            'transactions': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'description': {'type': 'string'},
                        'amount': {'type': 'number'},
                        'date': {'type': 'string', 'format': 'date'},
                        'category': {'type': 'string'}
                    },
                    'required': ['description', 'amount', 'date']
                }
            }
        },
        'required': ['transactions']
    }
}

def validate_schema(schema_name):
    """
    Decorator to validate request data against schema
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                # Get schema
                schema = API_SCHEMAS.get(schema_name)
                if not schema:
                    return standard_response(error=f"Schema {schema_name} not found", success=False, status_code=400)

                # Validate based on request method
                if request.method in ['POST', 'PUT', 'PATCH']:
                    if request.is_json:
                        data = request.get_json()
                    else:
                        data = request.form.to_dict()

                    validate(instance=data, schema=schema)
                elif request.method == 'GET':
                    # Validate query parameters
                    params = request.args.to_dict()
                    validate(instance=params, schema=schema)

                return f(*args, **kwargs)

            except jsonschema.ValidationError as e:
                return standard_response(error=f"Validation error: {e.message}", success=False, status_code=400)
            except Exception as e:
                return standard_response(error=f"Schema validation failed: {str(e)}", success=False, status_code=400)

        return wrapper
    return decorator

def validate_response_schema(data, schema_name):
    """
    Validate response data against a schema
    """
    try:
        schema = API_SCHEMAS.get(schema_name)
        if not schema:
            return True  # If schema not found, don't validate
        
        validate(instance=data, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        print(f"Response validation error for {schema_name}: {e.message}")
        return False
    except Exception as e:
        print(f"Response validation failed: {str(e)}")
        return False
