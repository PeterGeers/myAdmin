#!/usr/bin/env python3
"""
Error Handling Security Analysis
Checks for potential information leakage in error messages
"""

import re
import os

def analyze_error_handling():
    """Analyze error handling patterns for security issues"""
    
    print("=" * 80)
    print("ERROR HANDLING SECURITY ANALYSIS")
    print("=" * 80)
    print()
    
    files_to_check = [
        'backend/src/bnb_routes.py',
        'backend/src/str_channel_routes.py', 
        'backend/src/str_invoice_routes.py'
    ]
    
    security_issues = []
    safe_patterns = []
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            continue
            
        print(f"📁 Analyzing: {filepath}")
        print("-" * 60)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        file_issues = []
        file_safe = []
        
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Check for dangerous error patterns
            dangerous_patterns = [
                (r"'error':\s*str\(e\)", "Direct exception exposure with str(e)"),
                (r'"error":\s*str\(e\)', "Direct exception exposure with str(e)"),
                (r"'error':\s*e", "Direct exception object exposure"),
                (r'"error":\s*e', "Direct exception object exposure"),
                (r"str\(e\)", "Exception string conversion - potential info leak"),
            ]
            
            # Check for safe error patterns
            safe_patterns_check = [
                (r"'error':\s*'[^']*'", "Static error message"),
                (r'"error":\s*"[^"]*"', "Static error message"),
                (r"logging\.error", "Proper logging instead of user exposure"),
                (r"logger\.error", "Proper logging instead of user exposure"),
            ]
            
            for pattern, description in dangerous_patterns:
                if re.search(pattern, line_stripped):
                    file_issues.append({
                        'line': i,
                        'code': line_stripped,
                        'issue': description,
                        'severity': 'HIGH' if 'str(e)' in line_stripped else 'MEDIUM'
                    })
            
            for pattern, description in safe_patterns_check:
                if re.search(pattern, line_stripped):
                    file_safe.append({
                        'line': i,
                        'code': line_stripped[:80] + '...' if len(line_stripped) > 80 else line_stripped,
                        'pattern': description
                    })
        
        # Report findings for this file
        if file_issues:
            print("🚨 SECURITY ISSUES:")
            for issue in file_issues:
                severity_icon = "🔴" if issue['severity'] == 'HIGH' else "🟡"
                print(f"  {severity_icon} Line {issue['line']}: {issue['issue']}")
                print(f"    Code: {issue['code']}")
            print()
        
        if file_safe:
            print("✅ SAFE PATTERNS:")
            for safe in file_safe[:3]:  # Show first 3
                print(f"  Line {safe['line']}: {safe['pattern']}")
            if len(file_safe) > 3:
                print(f"  ... and {len(file_safe) - 3} more safe patterns")
            print()
        
        if not file_issues and not file_safe:
            print("ℹ️  No specific error handling patterns found")
            print()
        
        security_issues.extend(file_issues)
        safe_patterns.extend(file_safe)
        
        print()
    
    # Summary and recommendations
    print("=" * 80)
    print("ERROR HANDLING SECURITY SUMMARY")
    print("=" * 80)
    
    high_severity = [issue for issue in security_issues if issue['severity'] == 'HIGH']
    medium_severity = [issue for issue in security_issues if issue['severity'] == 'MEDIUM']
    
    print(f"High severity issues: {len(high_severity)}")
    print(f"Medium severity issues: {len(medium_severity)}")
    print(f"Safe patterns found: {len(safe_patterns)}")
    print()
    
    if security_issues:
        print("🚨 SECURITY RECOMMENDATIONS:")
        print("-" * 40)
        print("1. Replace str(e) with generic error messages")
        print("2. Log detailed errors server-side only")
        print("3. Return user-friendly error messages")
        print("4. Implement error categorization")
        print()
        
        print("📝 SUGGESTED FIXES:")
        print("-" * 20)
        print("Instead of:")
        print("  return jsonify({'success': False, 'error': str(e)}), 500")
        print()
        print("Use:")
        print("  logger.error(f'Database error in endpoint: {str(e)}')")
        print("  return jsonify({'success': False, 'error': 'Internal server error'}), 500")
        print()
        
        print("Or for specific errors:")
        print("  if 'connection' in str(e).lower():")
        print("      return jsonify({'success': False, 'error': 'Database connection error'}), 500")
        print("  else:")
        print("      return jsonify({'success': False, 'error': 'Internal server error'}), 500")
        print()
    else:
        print("✅ No obvious error handling security issues found")
    
    # Check for logging patterns
    print("🔍 LOGGING ANALYSIS:")
    print("-" * 20)
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        has_logging = bool(re.search(r'import logging|logger\.|logging\.', content))
        has_error_logging = bool(re.search(r'logging\.error|logger\.error', content))
        
        print(f"{filepath}:")
        print(f"  Has logging imports: {'✅' if has_logging else '❌'}")
        print(f"  Has error logging: {'✅' if has_error_logging else '❌'}")
    
    print()
    
    # Final security assessment
    if len(high_severity) > 0:
        security_status = "CRITICAL"
        print("🚨 CRITICAL: High severity error handling issues found")
    elif len(medium_severity) > 5:
        security_status = "HIGH_RISK"
        print("⚠️  HIGH RISK: Multiple error handling issues found")
    elif len(security_issues) > 0:
        security_status = "MEDIUM_RISK"
        print("⚠️  MEDIUM RISK: Some error handling issues found")
    else:
        security_status = "SECURE"
        print("✅ SECURE: No obvious error handling security issues")
    
    return {
        'status': security_status,
        'high_severity': len(high_severity),
        'medium_severity': len(medium_severity),
        'total_issues': len(security_issues)
    }

if __name__ == '__main__':
    analyze_error_handling()