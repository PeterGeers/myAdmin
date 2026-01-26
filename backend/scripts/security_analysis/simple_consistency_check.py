#!/usr/bin/env python3
"""
Simple Error Handling Consistency Check
Validates basic consistency patterns in STR route files
"""

import re
import os

def check_error_consistency():
    """Check error handling consistency in STR route files"""
    
    print("=" * 80)
    print("ERROR HANDLING CONSISTENCY CHECK")
    print("=" * 80)
    print()
    
    files_to_check = [
        'backend/src/bnb_routes.py',
        'backend/src/str_channel_routes.py', 
        'backend/src/str_invoice_routes.py'
    ]
    
    total_issues = 0
    total_endpoints = 0
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            continue
            
        print(f"📁 Analyzing: {filepath}")
        print("-" * 60)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count endpoints (functions with @route decorators)
        route_functions = re.findall(r'@\w+_bp\.route.*?\ndef\s+(\w+)\(', content, re.DOTALL)
        endpoint_count = len(route_functions)
        total_endpoints += endpoint_count
        
        print(f"Endpoints found: {endpoint_count}")
        
        # Check consistency patterns
        issues = []
        
        # 1. Check if all endpoints have try-catch blocks
        try_catch_count = len(re.findall(r'try:\s*\n.*?except.*?Exception.*?as.*?e:', content, re.DOTALL))
        if try_catch_count < endpoint_count:
            issues.append(f"Missing try-catch blocks: {endpoint_count - try_catch_count} endpoints")
        
        # 2. Check for consistent error response format
        error_responses = re.findall(r'return jsonify\(\{[^}]*[\'"]error[\'"][^}]*\}\)', content)
        success_false_responses = [r for r in error_responses if 'success.*False' in r or "'success': False" in r or '"success": False' in r]
        
        if len(success_false_responses) < len(error_responses):
            issues.append(f"Inconsistent error format: {len(error_responses) - len(success_false_responses)} responses missing 'success': False")
        
        # 3. Check for proper status codes
        status_500_count = len(re.findall(r'return.*?,\s*500', content))
        status_400_count = len(re.findall(r'return.*?,\s*400', content))
        status_403_count = len(re.findall(r'return.*?,\s*403', content))
        
        total_status_codes = status_500_count + status_400_count + status_403_count
        print(f"Status codes found: 500({status_500_count}), 400({status_400_count}), 403({status_403_count})")
        
        # 4. Check for logging
        has_logging_import = 'import logging' in content or 'logger' in content
        has_error_logging = 'logger.error' in content or 'logging.error' in content
        
        if not has_logging_import:
            issues.append("Missing logging import")
        if not has_error_logging:
            issues.append("Missing error logging")
        
        # 5. Check for secure error messages (no str(e) exposure)
        str_e_count = len(re.findall(r'str\(e\)', content))
        if str_e_count > 0:
            issues.append(f"Security issue: {str_e_count} instances of str(e) exposure")
        
        # 6. Check for tenant filtering consistency
        tenant_required_count = len(re.findall(r'@tenant_required\(\)', content))
        if tenant_required_count > 0:
            print(f"Tenant-protected endpoints: {tenant_required_count}")
            
            # Check if tenant validation is consistent
            user_tenants_usage = len(re.findall(r'user_tenants', content))
            if user_tenants_usage < tenant_required_count * 2:  # Should appear at least twice per endpoint
                issues.append("Inconsistent tenant filtering implementation")
        
        # Report issues
        if issues:
            print("⚠️  CONSISTENCY ISSUES:")
            for issue in issues:
                print(f"  • {issue}")
            total_issues += len(issues)
        else:
            print("✅ No consistency issues found")
        
        print()
    
    # Overall summary
    print("=" * 80)
    print("CONSISTENCY SUMMARY")
    print("=" * 80)
    
    print(f"Total endpoints analyzed: {total_endpoints}")
    print(f"Total consistency issues: {total_issues}")
    
    if total_issues == 0:
        print("🎉 EXCELLENT: All endpoints have consistent error handling")
        consistency_score = 100
    elif total_issues <= 3:
        print("✅ GOOD: Minor consistency issues found")
        consistency_score = 85
    elif total_issues <= 6:
        print("⚠️  MODERATE: Several consistency issues found")
        consistency_score = 70
    else:
        print("🚨 POOR: Many consistency issues found")
        consistency_score = 50
    
    print(f"Consistency Score: {consistency_score}%")
    print()
    
    # Recommendations
    print("📋 RECOMMENDATIONS:")
    print("-" * 20)
    
    if total_issues == 0:
        print("• Maintain current standards")
        print("• Document error handling patterns")
        print("• Regular consistency audits")
    else:
        print("• Fix identified consistency issues")
        print("• Implement error handling standards")
        print("• Add automated consistency checks")
        print("• Review and update documentation")
    
    return {
        'total_endpoints': total_endpoints,
        'total_issues': total_issues,
        'consistency_score': consistency_score
    }

if __name__ == '__main__':
    check_error_consistency()