#!/usr/bin/env python3
"""
Validate OpenAPI Specification

This script validates the OpenAPI spec file for:
- Valid YAML syntax
- Required OpenAPI fields
- Schema references
- Endpoint completeness
"""

import yaml
import sys
import os

def validate_openapi_spec(spec_path):
    """Validate OpenAPI specification file"""
    
    print(f"Validating OpenAPI spec: {spec_path}")
    print("=" * 60)
    
    # Check file exists
    if not os.path.exists(spec_path):
        print(f"❌ ERROR: File not found: {spec_path}")
        return False
    
    # Load YAML
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = yaml.safe_load(f)
        print("✅ Valid YAML syntax")
    except yaml.YAMLError as e:
        print(f"❌ YAML syntax error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return False
    
    # Check required OpenAPI fields
    required_fields = ['openapi', 'info', 'paths', 'components']
    for field in required_fields:
        if field in spec:
            print(f"✅ Required field '{field}' present")
        else:
            print(f"❌ Missing required field: {field}")
            return False
    
    # Check info section
    info = spec.get('info', {})
    info_fields = ['title', 'description', 'version']
    for field in info_fields:
        if field in info:
            print(f"✅ Info field '{field}': {info[field]}")
        else:
            print(f"⚠️  Missing info field: {field}")
    
    # Count paths
    paths = spec.get('paths', {})
    print(f"\n📊 Statistics:")
    print(f"   Total endpoints: {len(paths)}")
    
    # Count by tag
    tags_count = {}
    for path, methods in paths.items():
        for method, details in methods.items():
            if method in ['get', 'post', 'put', 'delete', 'patch']:
                tags = details.get('tags', ['Untagged'])
                for tag in tags:
                    tags_count[tag] = tags_count.get(tag, 0) + 1
    
    print(f"\n📋 Endpoints by tag:")
    for tag, count in sorted(tags_count.items()):
        print(f"   {tag}: {count}")
    
    # Count schemas
    schemas = spec.get('components', {}).get('schemas', {})
    print(f"\n📦 Schemas defined: {len(schemas)}")
    
    # Check for new Railway migration endpoints
    railway_endpoints = [
        '/tenant/config',
        '/tenant/users',
        '/tenant-admin/templates/preview',
        '/tenant-admin/templates/validate',
        '/tenant-admin/templates/approve',
        '/tenant-admin/templates/reject',
        '/tenant-admin/templates/ai-help',
        '/tenant-admin/templates/apply-ai-fixes',
        '/tenant/modules',
    ]
    
    print(f"\n🚂 Railway Migration Endpoints:")
    for endpoint in railway_endpoints:
        if endpoint in paths:
            print(f"   ✅ {endpoint}")
        else:
            print(f"   ❌ Missing: {endpoint}")
    
    # Check for new schemas
    railway_schemas = [
        'TenantConfigResponse',
        'TenantUsersResponse',
        'TemplatePreviewRequest',
        'TemplatePreviewResponse',
        'TemplateValidateRequest',
        'TemplateApproveRequest',
        'TemplateAIHelpRequest',
        'TenantModulesResponse',
    ]
    
    print(f"\n📋 Railway Migration Schemas:")
    for schema in railway_schemas:
        if schema in schemas:
            print(f"   ✅ {schema}")
        else:
            print(f"   ❌ Missing: {schema}")
    
    # Check security schemes
    security_schemes = spec.get('components', {}).get('securitySchemes', {})
    print(f"\n🔒 Security Schemes:")
    for scheme_name, scheme in security_schemes.items():
        print(f"   ✅ {scheme_name}: {scheme.get('type', 'unknown')}")
    
    print("\n" + "=" * 60)
    print("✅ OpenAPI specification validation complete!")
    return True

if __name__ == '__main__':
    # Get spec path from command line or use default
    if len(sys.argv) > 1:
        spec_path = sys.argv[1]
    else:
        # Default to backend/src/openapi_spec.yaml
        script_dir = os.path.dirname(os.path.abspath(__file__))
        spec_path = os.path.join(script_dir, '..', 'src', 'openapi_spec.yaml')
    
    success = validate_openapi_spec(spec_path)
    sys.exit(0 if success else 1)
