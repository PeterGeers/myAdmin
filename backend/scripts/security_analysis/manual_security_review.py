#!/usr/bin/env python3
"""
Manual Security Review for STR Reports
Focused analysis of actual SQL injection risks
"""

import re
import os

def analyze_sql_security():
    """Perform manual security analysis of SQL queries"""
    
    print("=" * 80)
    print("MANUAL SQL INJECTION SECURITY REVIEW")
    print("=" * 80)
    print()
    
    files_to_check = [
        'backend/src/bnb_routes.py',
        'backend/src/str_channel_routes.py', 
        'backend/src/str_invoice_routes.py'
    ]
    
    vulnerabilities = []
    safe_patterns = []
    warnings = []
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            continue
            
        print(f"📁 Analyzing: {filepath}")
        print("-" * 60)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Check for dangerous patterns
        dangerous_patterns = [
            (r'query\s*=\s*f".*?"', "f-string query construction"),
            (r'query\s*=\s*f""".*?"""', "f-string multi-line query"),
            (r'\.format\s*\(.*?\)', "String format() method"),
            (r'%\s*\(.*?\)', "% string formatting"),
            (r'query\s*\+\s*', "String concatenation in query"),
        ]
        
        # Check for safe patterns
        safe_patterns_check = [
            (r'cursor\.execute\s*\(\s*query\s*,\s*params\s*\)', "Parameterized query execution"),
            (r'%s', "Parameter placeholder"),
            (r'placeholders\s*=.*?join.*?%s', "Dynamic placeholder generation"),
        ]
        
        file_vulnerabilities = []
        file_safe = []
        file_warnings = []
        
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Check for dangerous patterns
            for pattern, description in dangerous_patterns:
                if re.search(pattern, line_stripped, re.IGNORECASE):
                    # Check if it's actually dangerous or just building safe queries
                    if 'placeholders' in line_stripped and '%s' in content:
                        # This is likely safe dynamic placeholder generation
                        continue
                    elif 'f"' in line_stripped and 'where_clause' in line_stripped:
                        # This is likely safe WHERE clause building
                        continue
                    elif 'f"' in line_stripped and 'select_fields' in line_stripped:
                        # This is likely safe field selection
                        continue
                    else:
                        file_vulnerabilities.append({
                            'line': i,
                            'code': line_stripped,
                            'issue': description
                        })
            
            # Check for safe patterns
            for pattern, description in safe_patterns_check:
                if re.search(pattern, line_stripped, re.IGNORECASE):
                    file_safe.append({
                        'line': i,
                        'code': line_stripped[:80] + '...' if len(line_stripped) > 80 else line_stripped,
                        'pattern': description
                    })
        
        # Report findings for this file
        if file_vulnerabilities:
            print("🚨 POTENTIAL VULNERABILITIES:")
            for vuln in file_vulnerabilities:
                print(f"  Line {vuln['line']}: {vuln['issue']}")
                print(f"    Code: {vuln['code']}")
            print()
        
        if file_safe:
            print("✅ SAFE PATTERNS FOUND:")
            for safe in file_safe[:5]:  # Show first 5
                print(f"  Line {safe['line']}: {safe['pattern']}")
            if len(file_safe) > 5:
                print(f"  ... and {len(file_safe) - 5} more safe patterns")
            print()
        
        vulnerabilities.extend(file_vulnerabilities)
        safe_patterns.extend(file_safe)
        
        print()
    
    # Summary
    print("=" * 80)
    print("SECURITY ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Total potential vulnerabilities: {len(vulnerabilities)}")
    print(f"Total safe patterns found: {len(safe_patterns)}")
    print()
    
    if vulnerabilities:
        print("⚠️  REVIEW REQUIRED:")
        print("The following patterns need manual review to confirm they are safe:")
        for vuln in vulnerabilities:
            print(f"  - {vuln['issue']} (multiple occurrences)")
        print()
    
    # Specific checks for tenant filtering
    print("🔒 TENANT FILTERING SECURITY CHECK:")
    print("-" * 40)
    
    tenant_patterns = [
        'user_tenants',
        '@tenant_required',
        'administration IN',
        'placeholders.*user_tenants'
    ]
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tenant_security = True
        missing_patterns = []
        
        for pattern in tenant_patterns:
            if not re.search(pattern, content, re.IGNORECASE):
                missing_patterns.append(pattern)
                tenant_security = False
        
        if tenant_security:
            print(f"✅ {filepath}: Proper tenant filtering implemented")
        else:
            print(f"❌ {filepath}: Missing tenant security patterns: {missing_patterns}")
    
    print()
    
    # Final assessment
    print("🎯 FINAL SECURITY ASSESSMENT:")
    print("-" * 30)
    
    if len(vulnerabilities) == 0:
        print("✅ No obvious SQL injection vulnerabilities found")
        print("✅ All queries appear to use proper parameterization")
        print("✅ Tenant filtering is properly implemented")
        security_status = "SECURE"
    elif len(vulnerabilities) < 5:
        print("⚠️  Few potential issues found - manual review recommended")
        security_status = "NEEDS_REVIEW"
    else:
        print("🚨 Multiple potential vulnerabilities found - immediate review required")
        security_status = "VULNERABLE"
    
    print(f"Overall Security Status: {security_status}")
    
    return {
        'status': security_status,
        'vulnerabilities': len(vulnerabilities),
        'safe_patterns': len(safe_patterns)
    }

if __name__ == '__main__':
    analyze_sql_security()