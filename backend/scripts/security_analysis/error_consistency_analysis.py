#!/usr/bin/env python3
"""
Error Handling Consistency Analysis
Validates that all endpoints have consistent error handling patterns
"""

import re
import os
from collections import defaultdict

def analyze_error_consistency():
    """Analyze error handling consistency across all route files"""
    
    print("=" * 80)
    print("ERROR HANDLING CONSISTENCY ANALYSIS")
    print("=" * 80)
    print()
    
    files_to_check = [
        'backend/src/bnb_routes.py',
        'backend/src/str_channel_routes.py', 
        'backend/src/str_invoice_routes.py'
    ]
    
    endpoint_analysis = {}
    error_patterns = defaultdict(list)
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            continue
            
        print(f"📁 Analyzing: {filepath}")
        print("-" * 60)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all route definitions
        route_pattern = r'@\w+_bp\.route\([\'"]([^\'"]+)[\'"].*?\ndef\s+(\w+)\('
        routes = re.findall(route_pattern, content, re.MULTILINE)
        
        file_analysis = {
            'routes': [],
            'has_logging': 'import logging' in content or 'logger' in content,
            'error_patterns': [],
            'consistency_issues': []
        }
        
        for route_path, function_name in routes:
            # Extract the function code
            func_pattern = rf'def {function_name}\(.*?\n(.*?)(?=\n@|\ndef\s+\w+|\Z)'
            func_match = re.search(func_pattern, content, re.DOTALL)
            
            if func_match:
                func_code = func_match.group(1)
                
                # Analyze error handling in this function
                route_analysis = analyze_route_error_handling(route_path, function_name, func_code)
                file_analysis['routes'].append(route_analysis)
                
                # Collect error patterns
                for pattern in route_analysis['error_patterns']:
                    error_patterns[pattern].append(f"{filepath}:{function_name}")
        
        endpoint_analysis[filepath] = file_analysis
        
        # Report findings for this file
        print(f"Routes found: {len(file_analysis['routes'])}")
        print(f"Has logging: {'✅' if file_analysis['has_logging'] else '❌'}")
        
        consistent_routes = [r for r in file_analysis['routes'] if r['is_consistent']]
        print(f"Consistent error handling: {len(consistent_routes)}/{len(file_analysis['routes'])}")
        
        if len(consistent_routes) < len(file_analysis['routes']):
            print("⚠️  Inconsistent routes:")
            for route in file_analysis['routes']:
                if not route['is_consistent']:
                    print(f"  - {route['function_name']} ({route['route_path']})")
                    for issue in route['issues']:
                        print(f"    • {issue}")
        
        print()
    
    # Overall consistency analysis
    print("=" * 80)
    print("OVERALL CONSISTENCY ANALYSIS")
    print("=" * 80)
    
    total_routes = sum(len(analysis['routes']) for analysis in endpoint_analysis.values())
    consistent_routes = sum(len([r for r in analysis['routes'] if r['is_consistent']]) 
                          for analysis in endpoint_analysis.values())
    
    consistency_percentage = (consistent_routes / total_routes * 100) if total_routes > 0 else 0
    
    print(f"Total routes analyzed: {total_routes}")
    print(f"Consistent routes: {consistent_routes}")
    print(f"Consistency percentage: {consistency_percentage:.1f}%")
    print()
    
    # Error pattern analysis
    print("🔍 ERROR PATTERN ANALYSIS:")
    print("-" * 30)
    
    for pattern, locations in error_patterns.items():
        print(f"{pattern}: {len(locations)} occurrences")
        if len(locations) <= 3:
            for location in locations:
                print(f"  - {location}")
        else:
            for location in locations[:2]:
                print(f"  - {location}")
            print(f"  - ... and {len(locations) - 2} more")
        print()
    
    # Recommendations
    print("📋 CONSISTENCY RECOMMENDATIONS:")
    print("-" * 35)
    
    if consistency_percentage < 80:
        print("🚨 CRITICAL: Low consistency across endpoints")
        print("1. Standardize error response format")
        print("2. Implement consistent status codes")
        print("3. Add missing try-catch blocks")
        print("4. Ensure all endpoints have proper logging")
    elif consistency_percentage < 95:
        print("⚠️  MODERATE: Some inconsistencies found")
        print("1. Review inconsistent endpoints")
        print("2. Standardize error messages")
        print("3. Add missing error handling")
    else:
        print("✅ GOOD: High consistency across endpoints")
        print("1. Monitor for future consistency")
        print("2. Document error handling standards")
    
    print()
    
    # Security assessment
    security_issues = []
    for filepath, analysis in endpoint_analysis.items():
        for route in analysis['routes']:
            if 'exposes_exception' in route['issues']:
                security_issues.append(f"{filepath}:{route['function_name']}")
    
    if security_issues:
        print("🔒 SECURITY ISSUES:")
        print("-" * 20)
        print(f"Endpoints exposing exceptions: {len(security_issues)}")
        for issue in security_issues[:5]:
            print(f"  - {issue}")
        if len(security_issues) > 5:
            print(f"  - ... and {len(security_issues) - 5} more")
    else:
        print("🔒 SECURITY: ✅ No exception exposure found")
    
    return {
        'total_routes': total_routes,
        'consistent_routes': consistent_routes,
        'consistency_percentage': consistency_percentage,
        'security_issues': len(security_issues)
    }

def analyze_route_error_handling(route_path, function_name, func_code):
    """Analyze error handling for a single route"""
    
    analysis = {
        'route_path': route_path,
        'function_name': function_name,
        'has_try_catch': False,
        'has_logging': False,
        'error_patterns': [],
        'issues': [],
        'is_consistent': True
    }
    
    # Check for try-catch blocks
    if 'try:' in func_code and 'except' in func_code:
        analysis['has_try_catch'] = True
    else:
        analysis['issues'].append('Missing try-catch block')
        analysis['is_consistent'] = False
    
    # Check for logging
    if 'logger.' in func_code or 'logging.' in func_code:
        analysis['has_logging'] = True
    else:
        analysis['issues'].append('Missing error logging')
        analysis['is_consistent'] = False
    
    # Check error response patterns
    error_responses = re.findall(r'return jsonify\(\{[^}]*[\'"]error[\'"][^}]*\}\)', func_code)
    
    for response in error_responses:
        if 'str(e)' in response:
            analysis['error_patterns'].append('exposes_exception')
            analysis['issues'].append('Exposes exception details')
            analysis['is_consistent'] = False
        elif 'Internal server error' in response:
            analysis['error_patterns'].append('generic_error')
        elif 'success.*False' in response:
            analysis['error_patterns'].append('standard_format')
        else:
            analysis['error_patterns'].append('custom_error')
    
    # Check status codes
    status_codes = re.findall(r'return.*?,\s*(\d+)', func_code)
    
    if not status_codes:
        analysis['issues'].append('Missing explicit status codes')
        analysis['is_consistent'] = False
    else:
        # Check for consistent status code usage
        error_codes = [code for code in status_codes if int(code) >= 400]
        if not error_codes:
            analysis['issues'].append('No error status codes found')
            analysis['is_consistent'] = False
    
    # Check for validation patterns
    if 'request.args.get' in func_code or 'request.get_json' in func_code:
        # This endpoint handles input - should have validation
        if not any(pattern in func_code for pattern in ['if not', 'required', 'missing']):
            analysis['issues'].append('Missing input validation')
            analysis['is_consistent'] = False
    
    return analysis

if __name__ == '__main__':
    analyze_error_consistency()